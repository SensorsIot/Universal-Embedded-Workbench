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

import json
import os
import re
import shutil
import subprocess
import threading
from typing import Any

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_DEFAULT_CONFIG: dict[str, Any] = {
    "default_freq_hz": 433_920_000,
    "default_sample_rate": 250_000,
    "default_duration_s": 10,
    "max_duration_s": 120,
    "snr_gate_db": 8.0,
    "rtl_433_bin": "rtl_433",
    "rtl_test_bin": "rtl_test",
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
            "mode": None,          # "decode" | "analyze"
            "freq_hz": 0,
        }
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

    def capture(self, freq_hz: int | None = None, duration_s: int | None = None,
                protocols: list[int] | None = None,
                sample_rate: int | None = None,
                flex: str | None = None) -> dict[str, Any]:
        """Decode RF for a bounded window; return decoded rtl_433 records.

        ``flex`` passes an rtl_433 ``-X`` flex-decoder spec (e.g.
        ``"n=awn,m=OOK_PWM,s=416,l=2150,r=16000"``) to decode a custom
        protocol — the recapture/verify use case — cutting through band noise
        that the generic analyzer can't resolve.
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
                duration_s: int | None = None) -> dict[str, Any]:
        """Pulse-analyzer capture (rtl_433 -A) for recapturing a remote."""
        freq_hz = int(freq_hz or self._config["default_freq_hz"])
        duration_s = self._clamp_duration(duration_s)
        cmd = [self._config["rtl_433_bin"], "-f", str(freq_hz),
               "-A", "-T", str(duration_s)]
        stdout, stderr = self._run(cmd, duration_s, mode="analyze",
                                   freq_hz=freq_hz)
        analyzer = _ANSI_RE.sub("", (stdout + stderr)).strip()
        return {"freq_hz": freq_hz, "duration_s": duration_s,
                "analyzer": analyzer}

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
