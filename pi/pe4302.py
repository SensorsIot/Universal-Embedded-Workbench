"""PE4302 digital step attenuator — 3-wire serial mode.

6-bit word: D5=16 dB, D4=8, D3=4, D2=2, D1=1, D0=0.5  (0..31.5 dB).
Shift MSB-first on the rising edge of CLK while LE is low, then pulse LE
high to latch the new attenuation into the RF path.

Pins are bit-banged through :mod:`bcm_gpio` so this driver shares the same
/dev/mem primitives as :mod:`gpclk` — no libgpiod dependency.

This driver is optional at the :mod:`signal_generator` level: if the board
does not include a PE4302, simply omit it from the config and attenuator
calls will be rejected with a clear error.
"""

from __future__ import annotations

import threading
import time

from bcm_gpio import BcmGpio

STEP_DB = 0.5
MAX_CODE = 0x3F                 # 6 bits → 0..31.5 dB
MAX_DB = MAX_CODE * STEP_DB     # 31.5


class PE4302Error(Exception):
    pass


class PE4302:
    """3-wire PE4302 attenuator."""

    def __init__(self, data_pin: int, clk_pin: int, le_pin: int) -> None:
        self._data = data_pin
        self._clk = clk_pin
        self._le = le_pin
        self._gpio = BcmGpio.get()
        self._lock = threading.Lock()
        self._current_db: float = 0.0
        self._initialized = False

    def init(self) -> None:
        """Configure the three pins as outputs and latch 0 dB."""
        self._gpio.set_output(self._data)
        self._gpio.set_output(self._clk)
        self._gpio.set_output(self._le)
        self._gpio.write(self._data, 0)
        self._gpio.write(self._clk, 0)
        self._gpio.write(self._le, 0)
        self._initialized = True
        self.set_db(0.0)

    def close(self) -> None:
        """Release pins back to input (high-Z)."""
        if not self._initialized:
            return
        for p in (self._data, self._clk, self._le):
            self._gpio.set_input(p)
        self._initialized = False

    # ── control ──────────────────────────────────────────────────────

    def set_db(self, db: float) -> float:
        """Set attenuation in dB (quantized to 0.5 dB).  Returns actual value."""
        if not self._initialized:
            raise PE4302Error("PE4302 not initialized — call init() first")
        if not (0.0 <= db <= MAX_DB):
            raise PE4302Error(f"Attenuation {db} dB out of range (0..{MAX_DB})")
        code = round(db / STEP_DB) & MAX_CODE
        with self._lock:
            self._shift_out(code)
        self._current_db = code * STEP_DB
        return self._current_db

    @property
    def db(self) -> float:
        return self._current_db

    # ── bit-bang ─────────────────────────────────────────────────────

    def _shift_out(self, code: int) -> None:
        """Shift 6 bits MSB-first, then pulse LE to latch."""
        self._gpio.write(self._le, 0)
        for i in range(5, -1, -1):
            bit = (code >> i) & 1
            self._gpio.write(self._clk, 0)
            self._gpio.write(self._data, bit)
            time.sleep(1e-6)       # ≥20 ns setup; sleep is coarse but safe
            self._gpio.write(self._clk, 1)
            time.sleep(1e-6)
        self._gpio.write(self._clk, 0)
        # Latch pulse
        self._gpio.write(self._le, 1)
        time.sleep(1e-6)
        self._gpio.write(self._le, 0)
