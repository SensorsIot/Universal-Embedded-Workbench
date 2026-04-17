"""Unified signal generator for the Embedded Workbench.

Consolidates three carrier sources behind one API:

  * **gpclk**   — BCM2835 GPCLK on GPIO 5/6 (always available on the Pi).
                  ~122 kHz to 250 MHz, integer divider from PLLD/500 MHz.
                  The original CW-beacon implementation.
  * **si5351**  — Si5351A clock generator on I²C1 @ 0x60.  ~8 kHz to
                  160 MHz, precise fractional synthesis, 3 channels.

Both backends expose the same ``key_on()`` / ``key_off()`` contract so a
shared :class:`morse.MorseKeyer` can gate either carrier for CW keying.

An optional **PE4302** digital step attenuator (0–31.5 dB, 0.5 dB steps,
3-wire serial) can sit in the RF path.  It is fully optional — the
generator works without it.

Hardware detection:
    * Si5351 is probed via I²C at start-up.  If the device does not ACK,
      the generator falls back to the GPCLK backend.
    * PE4302 is treated as present only if its ``enabled`` flag is set in
      the config; attenuator calls return a clean error when missing.

Configuration file: ``pi/config/signalgen.json`` (see ``_DEFAULT_CONFIG``).
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from gpclk import GpClk
from morse import MorseKeyer
from pe4302 import PE4302, PE4302Error
from si5351 import Si5351, Si5351Error

_DEFAULT_CONFIG: dict[str, Any] = {
    "si5351": {"bus": 1, "address": 0x60, "default_channel": 0},
    "gpclk": {"default_pin": 5},
    "pe4302": {
        "enabled": False,
        "data_pin": 16,
        "clk_pin": 20,
        "le_pin": 21,
    },
}

CONFIG_PATHS = (
    "/etc/rfc2217/signalgen.json",
    os.path.join(os.path.dirname(__file__), "config", "signalgen.json"),
)


def _load_config() -> dict[str, Any]:
    for path in CONFIG_PATHS:
        try:
            with open(path, "r") as f:
                cfg = json.load(f)
            merged = json.loads(json.dumps(_DEFAULT_CONFIG))
            for section, vals in cfg.items():
                if isinstance(vals, dict):
                    merged.setdefault(section, {}).update(vals)
                else:
                    merged[section] = vals
            return merged
        except (OSError, ValueError):
            continue
    return json.loads(json.dumps(_DEFAULT_CONFIG))


# ── backend adapters implementing the MorseKeyer contract ──────────


class _GpClkBackend:
    name = "gpclk"

    def __init__(self, pin: int) -> None:
        self._clk = GpClk(pin)
        self._freq: float = 0.0

    def start(self, freq_hz: float, channel: int = 0) -> float:
        self._freq = self._clk.start(freq_hz)
        return self._freq

    def stop(self) -> None:
        self._clk.stop()
        self._freq = 0.0

    def key_on(self) -> None:
        self._clk.key_on()

    def key_off(self) -> None:
        self._clk.key_off()

    @property
    def freq_hz(self) -> float:
        return self._freq

    def info(self) -> dict[str, Any]:
        return {"pin": self._clk.pin, "divider": self._clk.divider}


class _Si5351Backend:
    name = "si5351"

    def __init__(self, bus: int, address: int, default_channel: int) -> None:
        self._dev = Si5351(bus=bus, address=address)
        self._dev.init()
        self._channel = default_channel
        self._freq: float = 0.0

    def start(self, freq_hz: float, channel: int | None = None) -> float:
        if channel is not None:
            self._channel = channel
        self._freq = self._dev.set_frequency(self._channel, freq_hz)
        # start silent — keyer decides when to enable output
        self._dev.output_enable(self._channel, False)
        return self._freq

    def stop(self) -> None:
        try:
            self._dev.output_enable(self._channel, False)
        finally:
            self._freq = 0.0

    def key_on(self) -> None:
        self._dev.output_enable(self._channel, True)

    def key_off(self) -> None:
        self._dev.output_enable(self._channel, False)

    @property
    def freq_hz(self) -> float:
        return self._freq

    def info(self) -> dict[str, Any]:
        return {"channel": self._channel}

    def close(self) -> None:
        self._dev.close()


# ── orchestrator ───────────────────────────────────────────────────


class SignalGenerator:
    """Facade with auto-detecting backend selection and optional attenuator."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or _load_config()
        self._lock = threading.Lock()
        self._backend: _GpClkBackend | _Si5351Backend | None = None
        self._keyer: MorseKeyer | None = None
        self._attenuator: PE4302 | None = None
        self._state: dict[str, Any] = {
            "active": False,
            "backend": None,
            "freq_hz": 0.0,
            "channel": None,
            "pin": None,
            "atten_db": None,
            "morse": None,
        }
        self._hardware = self._detect_hardware()
        self._init_attenuator()

    # ── detection ────────────────────────────────────────────────

    def _detect_hardware(self) -> dict[str, bool]:
        si_cfg = self._config.get("si5351", {})
        si_present = Si5351.probe(si_cfg.get("bus", 1),
                                  si_cfg.get("address", 0x60))
        return {"si5351": si_present, "gpclk": True}

    def _init_attenuator(self) -> None:
        cfg = self._config.get("pe4302", {})
        if not cfg.get("enabled"):
            return
        try:
            self._attenuator = PE4302(
                cfg["data_pin"], cfg["clk_pin"], cfg["le_pin"])
            self._attenuator.init()
        except Exception as exc:  # pragma: no cover — pin errors etc.
            self._attenuator = None
            print(f"[siggen] PE4302 init failed: {exc}", flush=True)

    # ── public API ───────────────────────────────────────────────

    def available_backends(self) -> list[str]:
        return [name for name, ok in self._hardware.items() if ok]

    def hardware_status(self) -> dict[str, bool]:
        return {
            **self._hardware,
            "pe4302": self._attenuator is not None,
        }

    def start(self,
              freq_hz: float,
              backend: str = "auto",
              channel: int | None = None,
              pin: int | None = None,
              atten_db: float | None = None,
              morse: dict[str, Any] | None = None) -> dict[str, Any]:
        """Start a carrier.  ``backend='auto'`` prefers Si5351 when present.

        Optional ``morse = {"message": str, "wpm": int, "repeat": bool}``
        keys the carrier with the requested Morse message; without it the
        carrier runs continuous.
        """
        with self._lock:
            self._stop_locked()

            chosen = self._choose_backend(backend)
            backend_obj = self._make_backend(chosen, pin=pin, channel=channel)
            try:
                actual_freq = backend_obj.start(freq_hz, channel=channel or 0) \
                    if chosen == "si5351" else backend_obj.start(freq_hz)
            except Exception:
                self._close_backend(backend_obj)
                raise

            self._backend = backend_obj

            if atten_db is not None:
                self._set_atten_locked(atten_db)

            if morse:
                keyer = MorseKeyer(backend_obj)
                keyer.start(morse["message"],
                            wpm=morse.get("wpm", 15),
                            repeat=morse.get("repeat", True))
                self._keyer = keyer
                self._state["morse"] = {
                    "message": morse["message"].strip(),
                    "wpm": morse.get("wpm", 15),
                    "repeat": morse.get("repeat", True),
                }
            else:
                backend_obj.key_on()
                self._state["morse"] = None

            info = backend_obj.info()
            self._state.update({
                "active": True,
                "backend": chosen,
                "freq_hz": actual_freq,
                "channel": info.get("channel"),
                "pin": info.get("pin"),
                "atten_db": self._attenuator.db if self._attenuator else None,
            })
            return dict(self._state)

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_locked()
            return dict(self._state)

    def set_frequency(self, freq_hz: float,
                      channel: int | None = None) -> dict[str, Any]:
        """Retune the active carrier without restarting the keyer."""
        with self._lock:
            if not self._backend:
                raise RuntimeError("No carrier active")
            if isinstance(self._backend, _Si5351Backend):
                actual = self._backend.start(
                    freq_hz, channel=channel if channel is not None
                    else self._backend._channel)
            else:
                actual = self._backend.start(freq_hz)
                # re-engage key if no keyer is running
                if not (self._keyer and self._keyer.is_active()):
                    self._backend.key_on()
            self._state["freq_hz"] = actual
            return dict(self._state)

    def set_attenuation(self, db: float) -> dict[str, Any]:
        with self._lock:
            self._set_atten_locked(db)
            self._state["atten_db"] = self._attenuator.db \
                if self._attenuator else None
            return dict(self._state)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._state,
                "hardware": self.hardware_status(),
            }

    def shutdown(self) -> None:
        with self._lock:
            self._stop_locked()
            if self._attenuator:
                try:
                    self._attenuator.close()
                except Exception:
                    pass
                self._attenuator = None

    # ── helpers for frequency introspection ─────────────────────

    def list_frequencies(self, low: float, high: float,
                         backend: str = "auto") -> list[dict[str, Any]]:
        chosen = self._choose_backend(backend)
        if chosen == "gpclk":
            return GpClk.list_frequencies(low, high)
        # Si5351 is continuously tunable within its range
        from si5351 import OUT_FREQ_MAX, OUT_FREQ_MIN
        clamped_low = max(low, OUT_FREQ_MIN)
        clamped_high = min(high, OUT_FREQ_MAX)
        return [{"freq_hz": clamped_low, "tunable": True,
                 "range_hz": [clamped_low, clamped_high]}]

    # ── internals ───────────────────────────────────────────────

    def _choose_backend(self, requested: str) -> str:
        if requested == "auto":
            return "si5351" if self._hardware.get("si5351") else "gpclk"
        if requested == "si5351" and not self._hardware.get("si5351"):
            raise RuntimeError("Si5351 not detected on I²C bus")
        if requested not in ("gpclk", "si5351"):
            raise ValueError(f"Unknown backend: {requested}")
        return requested

    def _make_backend(self, name: str, *,
                      pin: int | None,
                      channel: int | None) -> _GpClkBackend | _Si5351Backend:
        if name == "gpclk":
            pin = pin if pin is not None \
                else self._config["gpclk"]["default_pin"]
            return _GpClkBackend(pin)
        si_cfg = self._config["si5351"]
        ch = channel if channel is not None else si_cfg["default_channel"]
        return _Si5351Backend(si_cfg["bus"], si_cfg["address"], ch)

    def _close_backend(self,
                       backend: _GpClkBackend | _Si5351Backend) -> None:
        try:
            backend.stop()
        except Exception:
            pass
        if isinstance(backend, _Si5351Backend):
            try:
                backend.close()
            except Exception:
                pass

    def _stop_locked(self) -> None:
        if self._keyer:
            try:
                self._keyer.stop()
            except Exception:
                pass
            self._keyer = None
        if self._backend:
            self._close_backend(self._backend)
            self._backend = None
        self._state.update({
            "active": False,
            "backend": None,
            "freq_hz": 0.0,
            "channel": None,
            "pin": None,
            "morse": None,
        })

    def _set_atten_locked(self, db: float) -> None:
        if not self._attenuator:
            raise PE4302Error(
                "PE4302 attenuator not available — "
                "enable in config/signalgen.json")
        self._attenuator.set_db(db)
