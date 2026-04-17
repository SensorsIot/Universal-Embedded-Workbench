"""Minimal Broadcom GPIO helper via /dev/mem.

Shared by gpclk.py and pe4302.py so both drivers use the same primitives.
No external dependencies — raw mmap of the BCM2835/2837 GPIO block.
"""

import mmap
import os
import struct
import threading


def _detect_peri_base() -> int:
    """Auto-detect BCM peripheral base from the device tree."""
    try:
        with open("/proc/device-tree/soc/ranges", "rb") as f:
            data = f.read(12)
            return struct.unpack(">I", data[4:8])[0]
    except (OSError, struct.error):
        return 0x20000000  # fallback: BCM2835 (Pi Zero W v1)


PERI_BASE = _detect_peri_base()
GPIO_BASE = PERI_BASE + 0x200000
CLK_BASE = PERI_BASE + 0x101000

# GPIO register offsets
GPFSEL0 = 0x00   # +0x04 * (pin // 10)
GPSET0 = 0x1C
GPCLR0 = 0x28
GPLEV0 = 0x34

FSEL_INPUT = 0b000
FSEL_OUTPUT = 0b001
FSEL_ALT0 = 0b100
FSEL_ALT5 = 0b010


class BcmGpio:
    """Process-wide singleton for /dev/mem-backed GPIO/CLK access.

    One mmap per block is enough; use get() to share the instance across
    drivers (gpclk, pe4302, signal_generator).
    """

    _instance: "BcmGpio | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._gpio_map: mmap.mmap | None = None
        self._clk_map: mmap.mmap | None = None
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "BcmGpio":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_mapped(self) -> None:
        if self._gpio_map is not None:
            return
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        try:
            self._gpio_map = mmap.mmap(
                fd, 4096, mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE, offset=GPIO_BASE)
            self._clk_map = mmap.mmap(
                fd, 4096, mmap.MAP_SHARED,
                mmap.PROT_READ | mmap.PROT_WRITE, offset=CLK_BASE)
        finally:
            os.close(fd)

    # ── low-level register I/O ────────────────────────────────────────

    @staticmethod
    def _read32(mm: mmap.mmap, offset: int) -> int:
        mm.seek(offset)
        return struct.unpack("<I", mm.read(4))[0]

    @staticmethod
    def _write32(mm: mmap.mmap, offset: int, value: int) -> None:
        mm.seek(offset)
        mm.write(struct.pack("<I", value))

    # ── GPIO block ────────────────────────────────────────────────────

    def set_fsel(self, pin: int, fsel: int) -> None:
        """Set the function-select field for a GPIO pin."""
        self._ensure_mapped()
        assert self._gpio_map is not None
        reg_offset = GPFSEL0 + (pin // 10) * 4
        shift = (pin % 10) * 3
        with self._lock:
            val = self._read32(self._gpio_map, reg_offset)
            val &= ~(0b111 << shift)
            val |= (fsel & 0b111) << shift
            self._write32(self._gpio_map, reg_offset, val)

    def set_output(self, pin: int) -> None:
        self.set_fsel(pin, FSEL_OUTPUT)

    def set_input(self, pin: int) -> None:
        self.set_fsel(pin, FSEL_INPUT)

    def set_alt(self, pin: int, alt: int) -> None:
        """alt: 0..5 (ALT0..ALT5)."""
        fsel = {0: 0b100, 1: 0b101, 2: 0b110, 3: 0b111, 4: 0b011, 5: 0b010}[alt]
        self.set_fsel(pin, fsel)

    def write(self, pin: int, value: int) -> None:
        """Drive an output pin high (1) or low (0)."""
        self._ensure_mapped()
        assert self._gpio_map is not None
        reg = GPSET0 if value else GPCLR0
        self._write32(self._gpio_map, reg, 1 << pin)

    def read(self, pin: int) -> int:
        self._ensure_mapped()
        assert self._gpio_map is not None
        return (self._read32(self._gpio_map, GPLEV0) >> pin) & 1

    # ── clock block ───────────────────────────────────────────────────

    def clk_read(self, offset: int) -> int:
        self._ensure_mapped()
        assert self._clk_map is not None
        return self._read32(self._clk_map, offset)

    def clk_write(self, offset: int, value: int) -> None:
        self._ensure_mapped()
        assert self._clk_map is not None
        self._write32(self._clk_map, offset, value)
