"""RTL-SDR receiver for the Embedded Workbench.

Receive-side counterpart to :mod:`signal_generator` (transmit-only).  Wraps
an RTL2832U dongle and the ``rtl_433`` toolchain behind one HTTP-friendly
API so callers never SSH into the Pi to sniff RF.

Two capture modes share one dongle (single-instance service):

  * **decode**   — run ``rtl_433 -F json`` for a bounded window and return
                   the decoded records (433/315/868 MHz remotes, weather
                   sensors, TPMS, …) as a list of dicts.
  * **analyze**  — run ``rtl_433 -A`` (pulse analyzer) and return its raw
                   pulse/gap text plus any guessed codeword.  This is the
                   recapture workflow: read a remote's OOK timing so it can
                   be replayed by an ESP32 or the signal generator.

Hardware detection:
    * ``rtl_433`` / ``rtl_test`` are located on ``PATH`` at start-up.
    * The dongle is probed once via ``rtl_test`` (bounded); the result is
      cached in :meth:`hardware_status`.  Every capture also surfaces a
      clean error if the tool or device is missing, so the portal degrades
      gracefully on a Pi with no dongle plugged in.

Configuration file: ``pi/config/sdr.json`` (see ``_DEFAULT_CONFIG``).
"""

from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import threading
from typing import Any, Callable

_LIVE_RSSI = re.compile(
    r"RSSI:\s*(?P<rssi>[-\d.]+)\s*dB\s*SNR:\s*(?P<snr>[-\d.]+)\s*dB"
    r"\s*Noise:\s*(?P<noise>[-\d.]+)")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_DEFAULT_CONFIG: dict[str, Any] = {
    "default_freq_hz": 433_920_000,
    "default_sample_rate": 250_000,
    "default_duration_s": 10,
    "max_duration_s": 120,
    "snr_gate_db": 8.0,
    "rtl_433_bin": "rtl_433",
    "rtl_test_bin": "rtl_test",
    "rtl_power_bin": "rtl_power",
}

CONFIG_PATHS = (
    "/etc/rfc2217/sdr.json",
    os.path.join(os.path.dirname(__file__), "config", "sdr.json"),
)


def _load_config() -> dict[str, Any]:
    for path in CONFIG_PATHS:
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            merged = json.loads(json.dumps(_DEFAULT_CONFIG))
            merged.update({k: v for k, v in cfg.items()})
            return merged
        except (OSError, ValueError):
            continue
    return json.loads(json.dumps(_DEFAULT_CONFIG))


class SdrError(RuntimeError):
    """Raised for missing hardware / tools or a bad request."""


class SdrReceiver:
    """RTL-SDR + rtl_433 receiver, single-instance (one dongle)."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or _load_config()
        self._lock = threading.Lock()      # serializes captures (one dongle)
        self._proc: subprocess.Popen | None = None
        self._state: dict[str, Any] = {
            "active": False,
            "mode": None,          # "decode" | "analyze" | "live"
            "freq_hz": 0,
        }
        # Live console: a persistent rtl_433 whose output a reader thread fans
        # into a sequence-numbered ring buffer the browser fast-polls. The live
        # session holds the dongle lock for its whole lifetime, so one-shot
        # captures report "SDR busy" until it is stopped.
        self._live_proc: subprocess.Popen | None = None
        self._live_thread: threading.Thread | None = None
        self._live_buf: collections.deque[dict[str, Any]] = \
            collections.deque(maxlen=600)
        self._live_seq = 0
        self._live_cfg: dict[str, Any] = {}
        self._live_running = False
        self._live_owns_lock = False
        self._live_guard = threading.Lock()    # guards buffer + seq
        self._live_admin = threading.Lock()    # serialises start/cleanup
        self._hardware = self._detect_hardware()

    # ── detection ────────────────────────────────────────────────────

    def _detect_hardware(self) -> dict[str, bool]:
        rtl_433 = shutil.which(self._config["rtl_433_bin"]) is not None
        rtl_test_bin = shutil.which(self._config["rtl_test_bin"])
        device = False
        if rtl_test_bin:
            try:
                # rtl_test -t opens the dongle and reports "Found N device(s)".
                out = subprocess.run(
                    [rtl_test_bin, "-t"], capture_output=True, text=True,
                    timeout=6)
                blob = (out.stdout or "") + (out.stderr or "")
                device = "Found" in blob and "No supported devices" not in blob
            except (OSError, subprocess.SubprocessError):
                device = False
        return {"rtl_433": rtl_433, "rtl_test": rtl_test_bin is not None,
                "device": device}

    def hardware_status(self) -> dict[str, bool]:
        return dict(self._hardware)

    def available(self) -> bool:
        return self._hardware["rtl_433"] and self._hardware["device"]

    def _require_ready(self) -> None:
        if not self._hardware["rtl_433"]:
            raise SdrError("rtl_433 not installed on the Pi")
        if not self._hardware["device"]:
            # Re-probe once — a dongle may have been hot-plugged since boot.
            self._hardware = self._detect_hardware()
            if not self._hardware["device"]:
                raise SdrError("no RTL-SDR dongle detected")

    # ── public API ───────────────────────────────────────────────────

    def _gain_args(self, gain: float | str | None) -> list[str]:
        """rtl_433 ``-g`` args. A fixed tuner gain (dB) disables the tuner's
        auto-AGC, which otherwise rails a strong near-field transmitter to
        full scale and mangles the modulation. Pass ``"auto"`` (or ``None``)
        to leave the driver default; a number sets a fixed gain in dB."""
        if gain is None:
            return []
        if isinstance(gain, str) and gain.strip().lower() == "auto":
            return ["-g", "auto"]
        return ["-g", str(gain)]

    def capture(self, freq_hz: int | None = None, duration_s: int | None = None,
                protocols: list[int] | None = None,
                sample_rate: int | None = None,
                flex: str | None = None,
                gain: float | str | None = None) -> dict[str, Any]:
        """Decode RF for a bounded window; return decoded rtl_433 records.

        ``flex`` passes an rtl_433 ``-X`` flex-decoder spec (e.g.
        ``"n=awn,m=OOK_PWM,s=416,l=2150,r=16000"``) to decode a custom
        protocol — the recapture/verify use case — cutting through band noise
        that the generic analyzer can't resolve.  ``gain`` sets a fixed tuner
        gain in dB to avoid front-end saturation on a near-field source.
        """
        freq_hz = int(freq_hz or self._config["default_freq_hz"])
        duration_s = self._clamp_duration(duration_s)
        # "-M level" attaches rssi/snr/noise (dB) to every package so callers
        # can threshold on signal strength instead of trusting decoder hits,
        # which fire on band noise too.
        cmd = [self._config["rtl_433_bin"], "-f", str(freq_hz),
               "-s", str(int(sample_rate or self._config["default_sample_rate"])),
               "-F", "json", "-M", "time:iso", "-M", "level",
               "-T", str(duration_s)]
        cmd += self._gain_args(gain)
        for proto in protocols or []:
            cmd += ["-R", str(int(proto))]
        if flex:
            cmd += ["-X", str(flex)]

        stdout, _ = self._run(cmd, duration_s, mode="decode", freq_hz=freq_hz)
        events: list[dict[str, Any]] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
        # Signal-vs-noise summary: strongest package's level, and how many
        # cleared an SNR gate. A real close-range burst reads high SNR; ambient
        # noise sits near 0. Threshold on `strong` / `max_snr`, not `count`.
        snrs = [e["snr"] for e in events if isinstance(e.get("snr"), (int, float))]
        rssis = [e["rssi"] for e in events if isinstance(e.get("rssi"), (int, float))]
        snr_gate = float(self._config.get("snr_gate_db", 8.0))
        strong = sum(1 for s in snrs if s >= snr_gate)
        return {"freq_hz": freq_hz, "duration_s": duration_s,
                "count": len(events), "events": events,
                "max_snr": max(snrs) if snrs else None,
                "max_rssi": max(rssis) if rssis else None,
                "snr_gate_db": snr_gate, "strong": strong}

    def analyze(self, freq_hz: int | None = None,
                duration_s: int | None = None,
                gain: float | str | None = None) -> dict[str, Any]:
        """Pulse-analyzer capture (rtl_433 -A) for recapturing a remote.

        ``gain`` sets a fixed tuner gain in dB; drop it to keep a strong
        near-field source from saturating the front end (which the analyzer
        reads as garbled multi-hundred-ms pulses / misdetected FSK).
        """
        freq_hz = int(freq_hz or self._config["default_freq_hz"])
        duration_s = self._clamp_duration(duration_s)
        cmd = [self._config["rtl_433_bin"], "-f", str(freq_hz),
               "-A", "-T", str(duration_s)]
        cmd += self._gain_args(gain)
        stdout, stderr = self._run(cmd, duration_s, mode="analyze",
                                   freq_hz=freq_hz)
        analyzer = _ANSI_RE.sub("", (stdout + stderr)).strip()
        return {"freq_hz": freq_hz, "duration_s": duration_s,
                "analyzer": analyzer}

    def power(self, freq_hz: int | None = None, duration_s: int | None = None,
              span_hz: int = 40000, bin_hz: int = 2000,
              notch_hz: int = 0) -> dict[str, Any]:
        """Measure narrowband RF power around ``freq_hz`` with rtl_power.

        Returns `{peak_db, mean_db}` over a small span centred on the target —
        a carrier (e.g. an OOK transmitter keying at 433.92) lifts `peak_db`
        clear of the broadband noise that decode-based detection drowns in.
        ``notch_hz`` excludes bins within that distance of the tuner centre from
        the peak/mean — the dongle's DC spike always sits there and would
        otherwise masquerade as the carrier when locating an unknown frequency.
        """
        freq_hz = int(freq_hz or self._config["default_freq_hz"])
        duration_s = self._clamp_duration(duration_s)
        lo = freq_hz - span_hz // 2
        hi = freq_hz + span_hz // 2
        cmd = [self._config["rtl_power_bin"], "-f", f"{lo}:{hi}:{bin_hz}",
               "-i", str(duration_s), "-1", "-"]
        stdout, _ = self._run(cmd, duration_s, mode="power", freq_hz=freq_hz)
        dbs: list[float] = []
        peak_db: float | None = None
        peak_freq: int | None = None
        for line in stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 7:
                continue
            # Each row covers one hop tile: cols 2/4 are its low edge and bin
            # step, cols 6+ are the per-bin dB. Recover each bin's centre freq
            # so the strongest bin can be reported — that's what locates a
            # carrier of unknown frequency across a wide sweep.
            try:
                f_low = float(parts[2])
                f_step = float(parts[4])
            except ValueError:
                continue
            for i, v in enumerate(parts[6:]):   # cols 0-5 metadata, rest are dB
                try:
                    db = float(v)
                except ValueError:
                    continue
                bin_freq = f_low + i * f_step
                if notch_hz and abs(bin_freq - freq_hz) <= notch_hz:
                    continue          # skip the DC spike at the tuner centre
                dbs.append(db)
                if peak_db is None or db > peak_db:
                    peak_db = db
                    peak_freq = int(bin_freq)
        return {"freq_hz": freq_hz, "duration_s": duration_s,
                "peak_db": peak_db, "peak_freq_hz": peak_freq,
                "mean_db": (sum(dbs) / len(dbs)) if dbs else None,
                "bins": len(dbs)}

    # ── live console (persistent rtl_433 + ring buffer) ──────────────

    def _build_live_cmd(self, freqs: list[int], gain: float | str | None,
                        sample_rate: int, mode: str, flex: str | None,
                        isolate: bool, squelch: bool, hop_interval: int,
                        ppm: int | None, y_opts: list[str] | None,
                        sdr_settings: str | None) -> list[str]:
        cmd = [self._config["rtl_433_bin"]]
        for f in freqs:
            cmd += ["-f", str(int(f))]
        if len(freqs) > 1:
            cmd += ["-H", str(int(hop_interval))]
        cmd += self._gain_args(gain)
        cmd += ["-s", str(int(sample_rate))]
        if ppm:
            cmd += ["-p", str(int(ppm))]
        if sdr_settings:
            cmd += ["-t", str(sdr_settings)]
        if squelch:
            cmd += ["-Y", "squelch"]
        for y in y_opts or []:
            cmd += ["-Y", str(y)]
        if mode == "analyze":
            cmd += ["-A"]              # analyzer text carries its own RSSI line
        else:
            if mode == "flex":
                if isolate:
                    cmd += ["-R", "0"]
                if flex:
                    cmd += ["-X", str(flex)]
            cmd += ["-F", "json", "-M", "level", "-M", "time:iso"]
        return cmd

    def start_live(self, freqs: list[int] | None = None,
                   gain: float | str | None = None,
                   sample_rate: int | None = None, mode: str = "decode",
                   flex: str | None = None, isolate: bool = False,
                   squelch: bool = False, hop_interval: int = 5,
                   ppm: int | None = None, y_opts: list[str] | None = None,
                   sdr_settings: str | None = None) -> dict[str, Any]:
        """Launch a persistent rtl_433 whose output streams into a ring buffer.

        Holds the dongle lock until :meth:`stop_live`. ``freqs`` is a list of Hz
        (one = locked, several = hop). ``mode`` is ``decode`` | ``flex`` |
        ``analyze``.
        """
        self._require_ready()
        with self._live_admin:
            if not self._lock.acquire(blocking=False):
                raise SdrError("SDR busy — a capture is already running")
            self._live_owns_lock = True
            try:
                fl = [int(f) for f in (freqs or [self._config["default_freq_hz"]])]
                rate = int(sample_rate or self._config["default_sample_rate"])
                cmd = self._build_live_cmd(
                    fl, gain, rate, mode, flex, isolate, squelch, hop_interval,
                    ppm, y_opts, sdr_settings)
                with self._live_guard:
                    self._live_buf.clear()
                    self._live_seq = 0
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                    env={**os.environ, "NO_COLOR": "1"})
                self._live_proc = proc
                self._live_running = True
                self._live_cfg = {
                    "freqs": fl, "hop": len(fl) > 1, "hop_interval": hop_interval,
                    "gain": gain, "sample_rate": rate, "mode": mode, "flex": flex,
                    "isolate": isolate, "squelch": squelch, "ppm": ppm,
                    "cmd": " ".join(cmd)}
                self._state.update({"active": True, "mode": "live",
                                    "freq_hz": fl[0]})
                t = threading.Thread(target=self._live_reader, args=(proc,),
                                     daemon=True)
                self._live_thread = t
                t.start()
            except Exception:
                self._live_cleanup()
                raise
        return self.live_status()

    def _live_reader(self, proc: subprocess.Popen) -> None:
        """Fan rtl_433's merged stdout/stderr into the sequence-numbered buffer.

        JSON lines become decoded events; ``RSSI:`` analyzer lines become a
        level-only event so the meter still moves in analyze mode; everything is
        kept as raw text for the analyzer/raw views."""
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = _ANSI_RE.sub("", raw).rstrip("\n").strip()
                if not line:
                    continue
                event: dict[str, Any] | None = None
                if line.startswith("{"):
                    try:
                        event = json.loads(line)
                    except ValueError:
                        event = None
                elif "RSSI:" in line:
                    m = _LIVE_RSSI.search(line)
                    if m:
                        event = {"rssi": float(m.group("rssi")),
                                 "snr": float(m.group("snr")),
                                 "noise": float(m.group("noise")),
                                 "analyzer": True}
                with self._live_guard:
                    self._live_seq += 1
                    self._live_buf.append(
                        {"seq": self._live_seq, "line": line, "event": event})
        finally:
            self._live_running = False

    def _live_cleanup(self) -> None:
        proc = self._live_proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._live_proc = None
        self._live_running = False
        self._state.update({"active": False, "mode": None, "freq_hz": 0})
        if self._live_owns_lock:
            self._live_owns_lock = False
            self._lock.release()

    def _reap_if_dead(self) -> None:
        """Reclaim the lock if rtl_433 exited on its own (crash / bad args)."""
        proc = self._live_proc
        if self._live_owns_lock and proc is not None and proc.poll() is not None:
            with self._live_admin:
                self._live_cleanup()

    def stop_live(self) -> dict[str, Any]:
        with self._live_admin:
            self._live_cleanup()
        return self.live_status()

    def live_status(self) -> dict[str, Any]:
        self._reap_if_dead()
        live = self._live_owns_lock and self._live_running
        return {"live": live, "seq": self._live_seq,
                "config": self._live_cfg if self._live_owns_lock else None,
                "hardware": self.hardware_status(),
                "available": self.available()}

    def live_events(self, since: int = 0) -> dict[str, Any]:
        self._reap_if_dead()
        since = int(since or 0)
        with self._live_guard:
            items = [e for e in self._live_buf if e["seq"] > since]
            last = self._live_seq
        return {"live": self._live_owns_lock and self._live_running,
                "since": since, "seq": last, "events": items,
                "config": self._live_cfg if self._live_owns_lock else None}

    # ── staged acquisition ───────────────────────────────────────────

    #: R820T tuner gain steps (dB), low→high, used for the level sweep.
    _GAIN_STEPS = (0.9, 8.7, 16.6, 25.4, 33.8, 40.2, 49.6)

    def acquire(self, freq_hz: int | None = None, span_hz: int = 500_000,
                bin_hz: int = 10_000, gains: list[float] | None = None,
                dwell_s: int = 3, decode_s: int = 12,
                flex: str | None = None, wait_s: int = 30,
                progress: Callable[[str, str], None] | None = None
                ) -> dict[str, Any]:
        """Phased receive: locate → level → decode → classify.

        A single guided acquisition that keeps a strong near-field source from
        being mis-read.  Each phase gates the next and the report says exactly
        where it stopped:

          1. **locate**   — poll ``rtl_power`` (up to ``wait_s``) until a carrier
                             appears across ``span_hz`` around ``freq_hz`` →
                             the true carrier (strongest bin). Waiting instead of
                             one fixed window means a momentary keyfob press is
                             caught whenever the operator sends it.
          2. **level**    — sweep tuner gain at the carrier; flag saturation;
                             pick the best clean gain, or report *too strong*
                             if it saturates even at minimum gain.
          3. **decode**   — derive/confirm a custom flex decoder (``-X``) and
                             extract the repeating codeword — not the built-ins.
          4. **classify** — only once decoded, check whether any built-in
                             ``rtl_433`` decoder also recognises the signal.

        Keep the transmitter keyed while it runs; ``locate`` waits for the first
        press, then the level/decode phases need it kept active.

        ``progress(msg, cat)`` is called at each phase boundary so a caller can
        surface live operator prompts (e.g. into the portal activity log) while
        the run is still in flight — the operator watches the workbench UI
        instead of a buffered terminal.
        """
        freq_hz = int(freq_hz or self._config["default_freq_hz"])
        emit = progress or (lambda _msg, _cat: None)
        report: dict[str, Any] = {"requested_freq_hz": freq_hz, "phases": {}}

        # Phase 1 — locate (poll until the carrier appears) ---------------
        emit(f"SDR acquire ▶ START THE SIGNAL — press/hold the transmitter "
             f"(~{freq_hz / 1e6:.2f} MHz)", "step")
        margin = None
        located = False
        carrier = None
        polls = 0
        loc: dict[str, Any] = {}
        for polls in range(1, max(1, wait_s // 2) + 1):
            loc = self.power(freq_hz, duration_s=2, span_hz=span_hz,
                             bin_hz=bin_hz, notch_hz=2 * bin_hz)
            if loc.get("peak_db") is not None and loc.get("mean_db") is not None:
                margin = loc["peak_db"] - loc["mean_db"]
                if margin >= 6.0:
                    located = True
                    carrier = int(loc.get("peak_freq_hz") or freq_hz)
                    break
        report["phases"]["locate"] = {
            **loc, "peak_margin_db": margin, "located": located,
            "carrier_freq_hz": carrier, "polls": polls}
        if not located:
            report["ok_phase"] = "locate-failed"
            report["summary"] = (
                "No carrier found — the strongest bin is not clear of the "
                "noise floor. Is the transmitter keyed and in range?")
            emit("SDR ✗ no carrier — is the transmitter keyed?", "error")
            return report
        emit(f"SDR ✓ carrier @ {carrier / 1e6:.4f} MHz "
             f"({margin:.0f} dB over noise) — keep the signal ON", "ok")

        # Phase 2 — level -------------------------------------------------
        emit("SDR ▶ finding the right gain — keep pressing…", "step")
        steps = gains if gains is not None else list(self._GAIN_STEPS)
        sweep: list[dict[str, Any]] = []
        suggested: dict[float, str] = {}
        for g in steps:
            text = self.analyze(carrier, duration_s=dwell_s, gain=g)["analyzer"]
            stats = self._pulse_stats(text)
            sug = self._suggested_flex(text)
            if sug:
                suggested[g] = sug
            sweep.append({
                "gain": g, "detected": stats["pulse_bins"] > 0,
                # rtl_433 -A only emits a flex spec once it reads the waveform
                # as clean OOK/PWM; a saturated OOK signal reads as FSK and it
                # gives up ("No clue"). So a flex suggestion == properly leveled.
                "clean_ook": sug is not None,
                "fsk_dominated": stats["fsk_dominated"],
                "max_snr": self._max_snr(text)})
        detected = [s for s in sweep if s["detected"]]
        clean = [s for s in detected
                 if s["clean_ook"] or (flex and not s["fsk_dominated"])]
        if not detected:
            report["phases"]["level"] = {"sweep": sweep, "chosen_gain": None}
            report["ok_phase"] = "level-nosignal"
            report["summary"] = (
                "Power scan saw a carrier but no pulses demodulated at any "
                "gain — likely a continuous/unmodulated carrier or interference.")
            emit("SDR ✗ carrier seen but no pulses — unmodulated / interference",
                 "error")
            return report
        if not clean:
            report["phases"]["level"] = {
                "sweep": sweep, "chosen_gain": None, "too_strong": True}
            report["ok_phase"] = "too-strong"
            report["summary"] = (
                "SIGNAL TOO STRONG — detected at every gain but never reads as "
                "a clean OOK codeword (the saturated front end reads it as FSK). "
                "Increase distance from the antenna or add an attenuator; if the "
                "source is genuinely FSK, pass an explicit flex spec.")
            emit("SDR ✗ TOO STRONG — move the transmitter back or attenuate",
                 "error")
            return report
        # Proper attenuation = the LOWEST gain that still reads clean: it clears
        # the noise floor without pushing the front end toward saturation.
        chosen = min(clean, key=lambda s: s["gain"])
        chosen_gain = chosen["gain"]
        used_flex = flex or suggested.get(chosen_gain)
        edge = any(s["fsk_dominated"] for s in sweep if s["gain"] > chosen_gain)
        report["phases"]["level"] = {
            "sweep": sweep, "chosen_gain": chosen_gain, "flex": used_flex,
            "too_strong": False,
            "warning": ("higher gains saturate into FSK — keep the source at "
                        "distance / attenuated") if edge else None}
        emit(f"SDR ✓ gain {chosen_gain} dB (clean OOK) — decoding, keep pressing…",
             "ok")

        # Phase 3 — decode (custom, not built-in) -------------------------
        # Retry: a bounded capture can land between presses, so try a few
        # windows before declaring failure — same "wait for the signal" idea.
        dec: dict[str, Any] = {}
        words: list[dict[str, Any]] = []
        for _ in range(3):
            dec = self.capture(carrier, duration_s=decode_s, flex=used_flex,
                               gain=chosen_gain)
            words = self._dominant_codewords(dec.get("events", []))
            if words:
                break
        report["phases"]["decode"] = {
            "flex": used_flex, "codewords": words, "packets": dec.get("count"),
            "max_snr": dec.get("max_snr"), "decoded": bool(words)}
        if not words:
            report["ok_phase"] = "decode-failed"
            report["summary"] = (
                f"Carrier {carrier} Hz, leveled at gain {chosen_gain} dB, but no "
                f"stable codeword decoded with flex '{used_flex}'.")
            emit("SDR ✗ no stable codeword decoded", "error")
            return report
        top = ", ".join(w["code"] for w in words[:4])
        emit(f"SDR ✓ decoded: {top}", "ok")

        # Phase 4 — classify against built-in decoders --------------------
        builtin = self.capture(carrier, duration_s=decode_s, gain=chosen_gain)
        models = sorted({e.get("model") for e in builtin.get("events", [])
                         if e.get("model")})
        report["phases"]["classify"] = {
            "builtin_models": models, "matched": bool(models),
            "packets": builtin.get("count")}
        report["ok_phase"] = "complete"
        report["summary"] = (
            f"Carrier {carrier} Hz @ gain {chosen_gain} dB; decoded "
            f"{len(words)} codeword(s): {top}. "
            + (f"Built-in decoder match: {', '.join(models)}." if models
               else "No built-in decoder matches — custom signal."))
        emit("SDR ✓ DONE — " + report["summary"], "ok")
        return report

    # ── acquisition helpers ──────────────────────────────────────────

    _DIST_ROW = re.compile(r"count:\s*(\d+),\s*width:\s*(\d+)\s*us")

    def _pulse_stats(self, analyzer_text: str) -> dict[str, Any]:
        """Summarise an rtl_433 -A capture: pulse-bin count (did it see pulses)
        and ``fsk_dominated`` — more FSK than OOK packages, the tell of a
        saturated OOK source (a railed front end reads on/off keying as a
        constant-amplitude carrier, which rtl_433 classifies as FSK)."""
        pulse_widths: set[int] = set()
        section: str | None = None
        for line in analyzer_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Pulse width distribution"):
                section = "pulse"
                continue
            if stripped.endswith("distribution:") or stripped.startswith(
                    ("Detected", "RSSI", "Level", "Frequency", "Gap")):
                section = None
            if section != "pulse":
                continue
            m = self._DIST_ROW.search(line)
            if m:
                pulse_widths.add(int(m.group(2)))
        ook = analyzer_text.count("Detected OOK package")
        fsk = analyzer_text.count("Detected FSK package")
        return {"pulse_bins": len(pulse_widths), "ook_pkgs": ook,
                "fsk_pkgs": fsk, "fsk_dominated": fsk > ook and fsk >= 3}

    @staticmethod
    def _max_snr(analyzer_text: str) -> float | None:
        vals = [float(v) for v in re.findall(
            r"SNR:\s*([-\d.]+)\s*dB", analyzer_text)]
        return max(vals) if vals else None

    @staticmethod
    def _suggested_flex(analyzer_text: str) -> str | None:
        """rtl_433 -A prints ``Use a flex decoder with -X '...'`` once it reads
        a signal as clean OOK/FSK — reuse that spec verbatim when present."""
        m = re.search(r"-X '([^']+)'", analyzer_text)
        return m.group(1) if m else None

    def _dominant_codewords(self, events: list[dict[str, Any]]
                            ) -> list[dict[str, Any]]:
        """Extract the repeating codeword(s) from decoded flex rows.

        Restricts to the strongest packets (within 6 dB of the peak RSSI) so the
        weak noise rows the slicer scrapes up don't drown out the real code —
        RSSI separates a keyed button (near full scale) from scraped noise far
        better than SNR here — and reduces each row to its repeating unit
        (rtl_433 concatenates repeats when it can't see a reset gap)."""
        rssis = [e["rssi"] for e in events
                 if isinstance(e.get("rssi"), (int, float))]
        floor = (max(rssis) - 6.0) if rssis else None
        counts: dict[str, int] = {}
        for e in events:
            rssi = e.get("rssi")
            if floor is not None and isinstance(rssi, (int, float)) \
                    and rssi < floor:
                continue
            for row in e.get("rows") or []:
                data = row.get("data")
                if not isinstance(data, str) or len(data) < 4:
                    continue
                unit = self._repeat_unit(data)
                if len(unit) < 3 or set(unit) <= {"0"} or set(unit) <= {"f"}:
                    continue          # all-low / all-high / tiny = noise
                counts[unit] = counts.get(unit, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        return [{"code": w, "count": n} for w, n in ranked[:6]]

    @staticmethod
    def _repeat_unit(hexstr: str) -> str:
        """Shortest repeating unit, tolerating a short leading preamble.

        rtl_433 concatenates repeated codewords into one long row when no reset
        gap separates them (e.g. ``800009000`` preamble + ``7f45dfd17`` ×N);
        recover the ``7f45dfd17`` unit by scanning small start offsets and
        periods, accepting the shortest that reconstructs ≥90% of its tail."""
        best = hexstr
        for start in range(0, min(16, len(hexstr) // 2)):
            sub = hexstr[start:]
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

    def stop(self) -> dict[str, Any]:
        """Terminate an in-progress capture (from another request thread)."""
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        # Barrier: the capture thread holds the lock for the whole run and
        # resets state in its finally block. Acquiring it here blocks until
        # that cleanup has run, so the returned status is never stale.
        with self._lock:
            pass
        return self.status()

    def status(self) -> dict[str, Any]:
        return {**self._state, "hardware": self.hardware_status(),
                "available": self.available()}

    def shutdown(self) -> None:
        self.stop_live()
        self.stop()

    # ── internals ────────────────────────────────────────────────────

    def _clamp_duration(self, duration_s: int | None) -> int:
        d = int(duration_s or self._config["default_duration_s"])
        if d < 1:
            raise SdrError("duration_s must be >= 1")
        return min(d, int(self._config["max_duration_s"]))

    def _run(self, cmd: list[str], duration_s: int, *, mode: str,
             freq_hz: int) -> tuple[str, str]:
        """Run a bounded rtl_433 capture while holding the dongle lock."""
        self._require_ready()
        if not self._lock.acquire(blocking=False):
            raise SdrError("SDR busy — a capture is already running")
        try:
            self._state.update({"active": True, "mode": mode,
                                 "freq_hz": freq_hz})
            # NO_COLOR keeps rtl_433 from wrapping output in ANSI escapes,
            # which it otherwise emits even when stdout is a pipe.
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                env={**os.environ, "NO_COLOR": "1"})
            self._proc = proc
            try:
                # rtl_433 self-exits after -T seconds; margin covers startup.
                stdout, stderr = proc.communicate(timeout=duration_s + 10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
            return stdout or "", stderr or ""
        except FileNotFoundError as exc:
            raise SdrError(f"rtl_433 not found: {exc}") from exc
        finally:
            self._proc = None
            self._state.update({"active": False, "mode": None, "freq_hz": 0})
            self._lock.release()
