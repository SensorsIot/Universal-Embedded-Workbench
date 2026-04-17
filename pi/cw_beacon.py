"""CW beacon — compatibility shim over the unified signal generator.

The original beacon bit-banged GPCLK directly.  That logic now lives in
:mod:`gpclk` (carrier) and :mod:`morse` (keyer), orchestrated by
:mod:`signal_generator`.  This module preserves the historical public API
so ``portal.py`` and the ``cw-beacon`` skill keep working unchanged.
"""

from __future__ import annotations

import threading
from typing import Any

from gpclk import CLK_OFFSETS, GpClk, PLLD_FREQ
from morse import MORSE_TABLE, MorseKeyer

__all__ = ["CWBeacon", "MORSE_TABLE", "PLLD_FREQ", "CLK_OFFSETS"]


class CWBeacon:
    """Hardware GPCLK CW beacon with Morse keying.

    Public API (``start``/``stop``/``status``/``list_frequencies``/``shutdown``)
    matches the pre-consolidation implementation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clk: GpClk | None = None
        self._keyer: MorseKeyer | None = None
        self._state: dict[str, Any] = {
            "active": False,
            "pin": None,
            "freq_hz": 0,
            "divider": 0,
            "message": "",
            "wpm": 15,
            "repeat": False,
        }

    # ── public API ───────────────────────────────────────────────

    def start(self, pin: int, freq: float, message: str,
              wpm: float = 15, repeat: bool = True) -> dict[str, Any]:
        if pin not in CLK_OFFSETS:
            return {"ok": False,
                    "error": f"Pin {pin} has no GPCLK — use 5 or 6"}
        if not message or not message.strip():
            return {"ok": False, "error": "Message is empty"}
        if not isinstance(wpm, (int, float)) or wpm < 1 or wpm > 60:
            return {"ok": False, "error": "WPM must be 1–60"}

        with self._lock:
            self._stop_internal()

            try:
                clk = GpClk(pin)
                actual_freq = clk.start(freq)
            except ValueError as exc:
                return {"ok": False, "error": str(exc)}

            keyer = MorseKeyer(clk)
            try:
                keyer.start(message, wpm=wpm, repeat=repeat)
            except ValueError as exc:
                clk.stop()
                return {"ok": False, "error": str(exc)}

            self._clk = clk
            self._keyer = keyer
            self._state = {
                "active": True,
                "pin": pin,
                "freq_hz": actual_freq,
                "divider": clk.divider,
                "message": message.strip(),
                "wpm": wpm,
                "repeat": repeat,
            }

        return {"ok": True, **self._state}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_internal()
        return {"ok": True}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def list_frequencies(self, low: float = 3_500_000,
                         high: float = 4_000_000) -> list[dict[str, Any]]:
        return GpClk.list_frequencies(low, high)

    def shutdown(self) -> None:
        self.stop()

    # ── private ──────────────────────────────────────────────────

    def _stop_internal(self) -> None:
        if self._keyer:
            try:
                self._keyer.stop()
            except Exception:
                pass
            self._keyer = None
        if self._clk:
            try:
                self._clk.stop()
            except Exception:
                pass
            self._clk = None
        self._state = {
            "active": False,
            "pin": None,
            "freq_hz": 0,
            "divider": 0,
            "message": "",
            "wpm": 15,
            "repeat": False,
        }
