"""Si5351A clock generator driver.

Minimal, dependency-light implementation for the generic "Si5351A MS5351M"
breakout (Adafruit-compatible): 25 MHz XTAL, I2C address 0x60, three CLK
outputs (CLK0..CLK2).

Supports frequency synthesis from ~8 kHz up to ~160 MHz via integer
MultiSynth dividers with the PLL absorbing the fractional remainder.
Output-enable register is used for clean carrier keying (no glitches from
reconfiguring the PLL).

Registers per AN619.  This driver deliberately does not implement the full
chip feature set — only what the workbench signal generator needs.
"""

from __future__ import annotations

import time

try:
    import smbus2  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — not on dev host
    smbus2 = None  # allows import on non-Pi machines

# ── Si5351 registers ────────────────────────────────────────────────
REG_DEVICE_STATUS = 0
REG_OUTPUT_ENABLE = 3            # 0 = enabled, 1 = disabled (bit per CLKx)
REG_CLK_CONTROL_BASE = 16        # CLK0 = 16, CLK1 = 17, CLK2 = 18
REG_MSNA_BASE = 26               # PLLA parameters (8 bytes)
REG_MSNB_BASE = 34               # PLLB parameters (8 bytes)
REG_MS_BASE = 42                 # MS0 = 42, MS1 = 50, MS2 = 58 (8 bytes each)
REG_PLL_RESET = 177
REG_XTAL_LOAD = 183

XTAL_FREQ = 25_000_000           # Hz, standard breakout crystal
PLL_FREQ_MIN = 600_000_000
PLL_FREQ_MAX = 900_000_000
OUT_FREQ_MIN = 8_000
OUT_FREQ_MAX = 160_000_000       # above this needs divide-by-4 mode

# CLK_CONTROL bitfields
CLK_POWER_DOWN = 0x80
CLK_INTEGER_MODE = 0x40
CLK_SRC_PLLB = 0x20              # 0 = PLLA
CLK_INVERT = 0x10
CLK_SRC_MS = 0x0C                # MultiSynth as source
CLK_DRIVE_8MA = 0x03


class Si5351Error(Exception):
    pass


class Si5351:
    """Si5351A on I2C bus 1 at address 0x60 (default)."""

    def __init__(self, bus: int = 1, address: int = 0x60) -> None:
        if smbus2 is None:
            raise Si5351Error("smbus2 not installed — run `pip install smbus2`")
        self._bus = smbus2.SMBus(bus)
        self._addr = address
        self._ch_freqs: dict[int, float] = {}

    # ── probe / init ────────────────────────────────────────────────

    @classmethod
    def probe(cls, bus: int = 1, address: int = 0x60) -> bool:
        """Return True if a device ACKs at (bus, address)."""
        if smbus2 is None:
            return False
        try:
            with smbus2.SMBus(bus) as b:
                b.read_byte_data(address, REG_DEVICE_STATUS)
            return True
        except (OSError, IOError):
            return False

    def init(self) -> None:
        """Power down all outputs and set XTAL load to 10 pF."""
        # Disable all outputs
        self._write(REG_OUTPUT_ENABLE, 0xFF)
        # Power down CLK0..7
        for ch in range(8):
            self._write(REG_CLK_CONTROL_BASE + ch, CLK_POWER_DOWN)
        # XTAL load capacitance: 10 pF (bits 7:6 = 0b11, lower bits reserved = 0b010010)
        self._write(REG_XTAL_LOAD, 0xD2)

    def close(self) -> None:
        try:
            self._write(REG_OUTPUT_ENABLE, 0xFF)
            for ch in range(3):
                self._write(REG_CLK_CONTROL_BASE + ch, CLK_POWER_DOWN)
        finally:
            try:
                self._bus.close()
            except Exception:
                pass

    # ── carrier control ─────────────────────────────────────────────

    def set_frequency(self, channel: int, freq_hz: float) -> float:
        """Program CLK*channel* to *freq_hz*.  Returns actual frequency."""
        if channel not in (0, 1, 2):
            raise Si5351Error("channel must be 0, 1, or 2")
        if not (OUT_FREQ_MIN <= freq_hz <= OUT_FREQ_MAX):
            raise Si5351Error(
                f"Frequency {freq_hz} Hz out of range "
                f"({OUT_FREQ_MIN}..{OUT_FREQ_MAX})")

        # Pick an even integer MS divider that keeps VCO in [600, 900] MHz
        ms_div = max(8, round(PLL_FREQ_MAX / freq_hz))
        if ms_div % 2:
            ms_div += 1
        if ms_div > 1800:
            ms_div = 1800
        vco = freq_hz * ms_div
        while vco > PLL_FREQ_MAX and ms_div > 8:
            ms_div -= 2
            vco = freq_hz * ms_div
        while vco < PLL_FREQ_MIN and ms_div <= 1800:
            ms_div += 2
            vco = freq_hz * ms_div
        if not (PLL_FREQ_MIN <= vco <= PLL_FREQ_MAX):
            raise Si5351Error(
                f"No valid VCO for {freq_hz} Hz (tried div={ms_div})")

        # PLL multiplier (fractional)
        pll_mult = vco / XTAL_FREQ
        mult_int = int(pll_mult)
        frac = pll_mult - mult_int
        denom = 1_048_575           # max 20-bit denominator
        num = int(round(frac * denom))
        if num == denom:
            mult_int += 1
            num = 0

        # Use PLLA for ch 0+1, PLLB for ch 2 to keep routing flexible
        pll_is_b = (channel == 2)
        pll_base = REG_MSNB_BASE if pll_is_b else REG_MSNA_BASE

        self._write_msn(pll_base, mult_int, num, denom)
        self._write_msn(REG_MS_BASE + 8 * channel, ms_div, 0, 1)

        # Reset the PLL so the new multiplier takes effect
        self._write(REG_PLL_RESET, 0x80 if pll_is_b else 0x20)

        # CLK control: MS source, integer mode, 8 mA drive, PLLA/B select
        ctrl = CLK_INTEGER_MODE | CLK_SRC_MS | CLK_DRIVE_8MA
        if pll_is_b:
            ctrl |= CLK_SRC_PLLB
        self._write(REG_CLK_CONTROL_BASE + channel, ctrl)

        actual_vco = XTAL_FREQ * (mult_int + num / denom)
        actual_freq = actual_vco / ms_div
        self._ch_freqs[channel] = actual_freq
        return actual_freq

    def output_enable(self, channel: int, enabled: bool) -> None:
        """Gate CLK*channel* output via register 3 — clean keying."""
        cur = self._read(REG_OUTPUT_ENABLE)
        mask = 1 << channel
        if enabled:
            cur &= ~mask
        else:
            cur |= mask
        self._write(REG_OUTPUT_ENABLE, cur)

    def frequency(self, channel: int) -> float:
        return self._ch_freqs.get(channel, 0.0)

    # ── I²C primitives ──────────────────────────────────────────────

    def _write(self, reg: int, value: int) -> None:
        for attempt in range(3):
            try:
                self._bus.write_byte_data(self._addr, reg, value & 0xFF)
                return
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(0.005)

    def _read(self, reg: int) -> int:
        return self._bus.read_byte_data(self._addr, reg)

    def _write_msn(self, base: int, div: int, num: int, denom: int) -> None:
        """Pack MultiSynth parameters per AN619 and write the 8-byte block."""
        p1 = 128 * div + (128 * num // denom) - 512
        p2 = 128 * num - denom * (128 * num // denom)
        p3 = denom

        regs = [
            (p3 >> 8) & 0xFF,
            p3 & 0xFF,
            (p1 >> 16) & 0x03,
            (p1 >> 8) & 0xFF,
            p1 & 0xFF,
            ((p3 >> 12) & 0xF0) | ((p2 >> 16) & 0x0F),
            (p2 >> 8) & 0xFF,
            p2 & 0xFF,
        ]
        for i, val in enumerate(regs):
            self._write(base + i, val)
