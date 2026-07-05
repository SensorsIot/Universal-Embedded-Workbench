#!/usr/bin/env python3
"""Interactive guided SDR acquisition for the Universal Embedded Workbench.

Runs the four-phase receive procedure — locate → level → decode → classify —
against the workbench SDR HTTP API, printing live instructions and results so
the *operator* drives the timing, not a chat round-trip:

  1. LOCATE   — waits (polling rtl_power) for the carrier to appear, then
                reports the true frequency.
  2. LEVEL    — sweeps tuner gain, picks the lowest gain that reads clean OOK,
                or reports the signal is TOO STRONG (saturating into FSK).
  3. DECODE   — decodes the repeating codeword with a custom flex decoder
                (not the built-ins).
  4. CLASSIFY — only then checks whether any built-in rtl_433 decoder matches.

Every phase has a bounded timeline and returns on its own; keep the
transmitter keyed while a phase says it is listening.

Usage:
    python3 tools/sdr_acquire.py                 # 433.92 MHz, default Pi
    python3 tools/sdr_acquire.py --freq 315.0
    python3 tools/sdr_acquire.py --url http://192.168.0.87:8080 --flex "n=r,m=OOK_PWM,s=416,l=2150,r=16000"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request

DEFAULT_URL = "http://192.168.0.87:8080"
DEFAULT_FLEX = "n=rmt,m=OOK_PWM,s=416,l=2150,r=16000"
GAIN_STEPS = [0.9, 16.6, 25.4, 33.8, 40.2, 49.6]


# ── tiny HTTP + console helpers ──────────────────────────────────────

class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def post(self, path: str, body: dict, timeout: float) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    def get(self, path: str, timeout: float) -> dict:
        with urllib.request.urlopen(self.base + path, timeout=timeout) as resp:
            return json.loads(resp.read().decode())


def c(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def phase_banner(n: int, name: str) -> None:
    print("\n" + c("1;36", f"PHASE {n} / {name}") + "  "
          + c("36", "─" * (44 - len(name))))


def prompt(text: str) -> None:
    print(c("1;33", "▶ " + text))


# ── codeword extraction (repeating unit, strongest packets only) ─────

def repeat_unit(s: str) -> str:
    best = s
    for start in range(0, min(16, len(s) // 2)):
        sub = s[start:]
        n = len(sub)
        for period in range(3, n // 2 + 1):
            if period >= len(best):
                break
            unit = sub[:period]
            rep = (unit * (n // period + 1))[:n]
            if sum(a == b for a, b in zip(rep, sub)) / n >= 0.90:
                best = unit
                break
    return best


def codewords(events: list) -> list:
    rssis = [e["rssi"] for e in events
             if isinstance(e.get("rssi"), (int, float))]
    floor = (max(rssis) - 6.0) if rssis else None
    counts: dict = {}
    for e in events:
        rssi = e.get("rssi")
        if floor is not None and isinstance(rssi, (int, float)) and rssi < floor:
            continue
        for row in e.get("rows") or []:
            data = row.get("data")
            if not isinstance(data, str) or len(data) < 4:
                continue
            unit = repeat_unit(data)
            if len(unit) < 3 or set(unit) <= {"0"} or set(unit) <= {"f"}:
                continue
            counts[unit] = counts.get(unit, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:6]


def analyze_class(text: str) -> tuple:
    ook = text.count("Detected OOK package")
    fsk = text.count("Detected FSK package")
    detected = (ook + fsk) > 0
    m = re.search(r"-X '([^']+)'", text)          # rtl_433's flex suggestion
    snr = re.findall(r"SNR:\s*([-\d.]+)\s*dB", text)
    max_snr = max(float(v) for v in snr) if snr else None
    return detected, (m.group(1) if m else None), (fsk > ook and fsk >= 3), max_snr


# ── phases ───────────────────────────────────────────────────────────

def locate(api: Api, freq_hz: int, span_hz: int, bin_hz: int,
           wait_s: int) -> int | None:
    phase_banner(1, "LOCATE")
    prompt("START THE SIGNAL NOW — press/hold your transmitter.")
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        r = api.post("/api/sdr/power", {
            "freq_hz": freq_hz, "span_hz": span_hz, "bin_hz": bin_hz,
            "duration_s": 2}, timeout=15)
        peak, mean = r.get("peak_db"), r.get("mean_db")
        if peak is None or mean is None:
            continue
        margin = peak - mean
        pk = r.get("peak_freq_hz")
        if margin >= 6.0 and pk is not None and abs(pk - freq_hz) > bin_hz:
            print(f"  peak {peak:+.1f} dB  margin {margin:4.1f} dB  "
                  + c("1;32", f"✓ CARRIER @ {pk/1e6:.4f} MHz"))
            return int(pk)
        print(f"  peak {peak:+.1f} dB  margin {margin:4.1f} dB  … listening")
    print(c("1;31", "✗ no carrier within timeout — is the transmitter keyed?"))
    return None


def level(api: Api, freq_hz: int, gains: list, dwell_s: int) -> tuple:
    phase_banner(2, "LEVEL")
    prompt("KEEP THE SIGNAL ON — finding the right gain / attenuation…")
    clean: list = []
    saturated_high = False
    for g in gains:
        r = api.post("/api/sdr/analyze", {
            "freq_hz": freq_hz, "duration_s": dwell_s, "gain": g}, timeout=dwell_s + 20)
        detected, sug, fsk_dom, snr = analyze_class(r.get("analyzer", ""))
        if not detected:
            print(f"  gain {g:5.1f} dB : {c('90', 'no pulses (press harder?)')}")
        elif sug:
            print(f"  gain {g:5.1f} dB : "
                  + c("32", f"clean OOK ✓  (SNR {snr:.0f} dB)"))
            clean.append((g, sug))
        elif fsk_dom:
            print(f"  gain {g:5.1f} dB : "
                  + c("31", "SATURATED — reads as FSK"))
            if clean:
                saturated_high = True
        else:
            print(f"  gain {g:5.1f} dB : detected, unresolved modulation")
    if not clean:
        print(c("1;31", "→ SIGNAL TOO STRONG (or unknown modulation): never reads "
                        "clean OOK. Increase distance / add attenuation, or pass "
                        "--flex for a known protocol."))
        return None, None
    g, flex = min(clean, key=lambda t: t[0])   # lowest clean gain = best
    warn = "  ⚠ higher gains saturate — keep distance/attenuation" if saturated_high else ""
    print(c("1;32", f"→ chosen gain {g} dB (lowest clean).") + c("33", warn))
    return g, flex


def decode(api: Api, freq_hz: int, gain: float, flex: str,
           decode_s: int, tries: int) -> list:
    phase_banner(3, "DECODE")
    prompt("KEEP PRESSING — decoding the codeword…")
    for attempt in range(1, tries + 1):
        r = api.post("/api/sdr/capture", {
            "freq_hz": freq_hz, "duration_s": decode_s, "gain": gain,
            "flex": flex}, timeout=decode_s + 20)
        words = codewords(r.get("events", []))
        if words:
            for code, n in words:
                print("  codeword " + c("1;32", code) + f"  (×{n})")
            return words
        print(f"  attempt {attempt}/{tries}: nothing yet…")
    print(c("1;31", "✗ no stable codeword decoded"))
    return []


def classify(api: Api, freq_hz: int, gain: float, decode_s: int) -> list:
    phase_banner(4, "CLASSIFY")
    prompt("Checking built-in rtl_433 decoders…")
    r = api.post("/api/sdr/capture", {
        "freq_hz": freq_hz, "duration_s": decode_s, "gain": gain}, timeout=decode_s + 20)
    models = sorted({e.get("model") for e in r.get("events", []) if e.get("model")})
    if models:
        print("  " + c("1;32", "built-in match: " + ", ".join(models)))
    else:
        print("  " + c("90", "no built-in decoder matches — custom signal"))
    return models


# ── main ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Guided SDR acquisition (workbench).")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--freq", type=float, default=433.92, help="MHz")
    ap.add_argument("--span", type=int, default=500_000, help="locate span, Hz")
    ap.add_argument("--bin", type=int, default=10_000, help="locate bin, Hz")
    ap.add_argument("--gains", type=str, default=None,
                    help="comma list of gains dB, e.g. 0.9,16.6,33.8,49.6")
    ap.add_argument("--dwell", type=int, default=3, help="per-gain seconds")
    ap.add_argument("--decode", type=int, default=8, help="decode seconds")
    ap.add_argument("--wait", type=int, default=30, help="locate timeout, s")
    ap.add_argument("--flex", default=None,
                    help="force an rtl_433 -X spec (skip auto)")
    args = ap.parse_args()

    try:                                           # live, unbuffered output
        sys.stdout.reconfigure(line_buffering=True)
    except AttributeError:
        pass
    api = Api(args.url)
    freq_hz = int(round(args.freq * 1e6))
    gains = ([float(x) for x in args.gains.split(",")] if args.gains
             else GAIN_STEPS)

    print(c("1;37", "Universal Embedded Workbench — SDR guided acquisition"))
    print(f"Target {args.freq:.3f} MHz   via {args.url}")
    try:
        st = api.get("/api/sdr/status", timeout=5)
        if not st.get("available"):
            print(c("1;31", "workbench reachable but SDR unavailable "
                            f"(hardware: {st.get('hardware')})"))
            return 2
    except Exception as exc:                       # noqa: BLE001
        print(c("1;31", f"cannot reach workbench: {exc}"))
        return 2

    try:
        carrier = locate(api, freq_hz, args.span, args.bin, args.wait)
        if carrier is None:
            return 1
        gain, flex = level(api, carrier, gains, args.dwell)
        if gain is None:
            return 1
        if args.flex:
            flex = args.flex
        words = decode(api, carrier, gain, flex, args.decode, tries=3)
        if not words:
            return 1
        models = classify(api, carrier, gain, args.decode)

        print("\n" + c("1;37", "DONE.") + f"  Carrier {carrier/1e6:.4f} MHz "
              f"@ gain {gain} dB")
        for code, n in words:
            print("   " + c("1;32", code) + f"  (×{n})")
        if not models:
            print("   " + c("90", "no built-in decoder — custom signal"))
    except KeyboardInterrupt:
        print("\ninterrupted")
        try:
            api.post("/api/sdr/stop", {}, timeout=10)
        except Exception:                          # noqa: BLE001
            pass
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
