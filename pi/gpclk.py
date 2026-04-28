"""BCM2835/2837 GPCLK hardware clock driver.

Drives a clean PLLD-sourced square wave on GPIO 5 (GPCLK1) or GPIO 6 (GPCLK2)
with an integer divider.  Keying is done at the GPIO function-select level:
ALT0 connects the clock to the pin, INPUT disconnects it (high-Z, glitch-free).
Used as the GPCLK fallback backend of the unified signal generator
(see ``signal_generator.py``); the Morse keyer (``morse.py``) gates this
backend the same way it gates the Si5351 backend.
"""

import time

from bcm_gpio import BcmGpio

# Clock manager register offsets from CLK_BASE
#   GPCLK1 (GPIO 5): CTL = 0x78, DIV = 0x7C
#   GPCLK2 (GPIO 6): CTL = 0x80, DIV = 0x84
CLK_OFFSETS: dict[int, tuple[int, int]] = {
    5: (0x78, 0x7C),
    6: (0x80, 0x84),
}

CLK_PASSWD = 0x5A000000
CLK_SRC_PLLD = 6          # PLLD = 500 MHz
CLK_ENAB = 1 << 4
CLK_BUSY = 1 << 7
CLK_KILL = 1 << 5

PLLD_FREQ = 500_000_000
DIV_MIN = 2
DIV_MAX = 4095


class GpClk:
    """Single-channel GPCLK driver bound to a specific GPIO pin."""

    def __init__(self, pin: int) -> None:
        if pin not in CLK_OFFSETS:
            raise ValueError(f"Pin {pin} has no GPCLK — use 5 or 6")
        self._pin = pin
        self._ctl, self._div = CLK_OFFSETS[pin]
        self._gpio = BcmGpio.get()
        self._running = False
        self._divider = 0

    @property
    def pin(self) -> int:
        return self._pin

    @property
    def divider(self) -> int:
        return self._divider

    @property
    def freq_hz(self) -> float:
        return PLLD_FREQ / self._divider if self._divider else 0.0

    # ── carrier control ──────────────────────────────────────────────

    def start(self, freq_hz: float) -> float:
        """Start the clock at the closest integer-divider frequency."""
        divider = round(PLLD_FREQ / freq_hz)
        if not (DIV_MIN <= divider <= DIV_MAX):
            raise ValueError(f"Frequency {freq_hz} Hz out of GPCLK range "
                             f"({PLLD_FREQ / DIV_MAX:.0f}..{PLLD_FREQ / DIV_MIN:.0f} Hz)")
        self._stop_clock_hw()
        # Integer divider (no MASH = clean square wave)
        self._gpio.clk_write(self._div, CLK_PASSWD | (divider << 12))
        self._gpio.clk_write(self._ctl, CLK_PASSWD | CLK_ENAB | CLK_SRC_PLLD)
        time.sleep(0.01)
        self._divider = divider
        self._running = True
        # Start silent — caller chooses when to gate the pin
        self.key_off()
        return self.freq_hz

    def stop(self) -> None:
        self.key_off()
        self._stop_clock_hw()
        self._running = False
        self._divider = 0

    def _stop_clock_hw(self) -> None:
        self._gpio.clk_write(self._ctl, CLK_PASSWD | CLK_KILL)
        time.sleep(0.01)
        # Wait until not busy
        for _ in range(100):
            if not (self._gpio.clk_read(self._ctl) & CLK_BUSY):
                return
            time.sleep(0.001)

    # ── keying (Morse backend contract) ──────────────────────────────

    def key_on(self) -> None:
        """Connect clock output to pin (ALT0)."""
        self._gpio.set_alt(self._pin, 0)

    def key_off(self) -> None:
        """Disconnect clock from pin (INPUT = high-Z)."""
        self._gpio.set_input(self._pin)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def list_frequencies(low: float, high: float) -> list[dict]:
        """List achievable integer-divider frequencies in [low, high] Hz."""
        results = []
        div_high = max(DIV_MIN, int(PLLD_FREQ // high))
        div_low = min(DIV_MAX, int(PLLD_FREQ // low) + 1)
        for d in range(div_high, div_low + 1):
            f = PLLD_FREQ / d
            if low <= f <= high:
                results.append({"divider": d, "freq_hz": f})
        return results
