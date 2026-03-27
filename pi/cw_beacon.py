"""CW beacon using GPCLK hardware clock generator on Raspberry Pi.

Generates RF carrier on GPIO 5 (GPCLK1) or GPIO 6 (GPCLK2) by configuring
the BCM2835 clock manager via /dev/mem.  Morse keying switches the pin
between ALT0 (clock output) and INPUT (high-Z) so the oscillator runs
continuously and the output is glitch-free.

Frequency source: PLLD (500 MHz) with integer divider.
"""

import mmap
import os
import struct
import threading
import time

def _detect_peri_base():
    """Auto-detect BCM peripheral base from device tree."""
    try:
        with open("/proc/device-tree/soc/ranges", "rb") as f:
            data = f.read(12)
            return struct.unpack(">I", data[4:8])[0]
    except (OSError, struct.error):
        return 0x20000000  # fallback: BCM2835 (Pi Zero W v1)


PERI_BASE = _detect_peri_base()
GPIO_BASE = PERI_BASE + 0x200000
CLK_BASE = PERI_BASE + 0x101000

# Clock manager register offsets from CLK_BASE
#   GPCLK1 (GPIO 5): CTL = 0x78, DIV = 0x7C
#   GPCLK2 (GPIO 6): CTL = 0x80, DIV = 0x84
CLK_OFFSETS = {
    5: (0x78, 0x7C),   # GPIO 5 = GPCLK1
    6: (0x80, 0x84),   # GPIO 6 = GPCLK2
}

CLK_PASSWD = 0x5A000000
CLK_SRC_PLLD = 6         # PLLD = 500 MHz
CLK_ENAB = 1 << 4
CLK_BUSY = 1 << 7
CLK_KILL = 1 << 5

FSEL_INPUT = 0b000
FSEL_ALT0 = 0b100

PLLD_FREQ = 500_000_000

# Morse code table (ITU standard)
MORSE_TABLE = {
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",
    "E": ".",     "F": "..-.",  "G": "--.",   "H": "....",
    "I": "..",    "J": ".---",  "K": "-.-",   "L": ".-..",
    "M": "--",    "N": "-.",    "O": "---",   "P": ".--.",
    "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",
    "Y": "-.--",  "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--",
    "4": "....-", "5": ".....", "6": "-....", "7": "--...",
    "8": "---..", "9": "----.",
    "/": "-..-.", "=": "-...-", "?": "..--..", ".": ".-.-.-",
    ",": "--..--",
}


class CWBeacon:
    """Hardware GPCLK CW beacon with Morse keying."""

    def __init__(self):
        self._gpio_map = None
        self._clk_map = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._state = {
            "active": False,
            "pin": None,
            "freq_hz": 0,
            "divider": 0,
            "message": "",
            "wpm": 15,
            "repeat": False,
        }

    # ── register access ──────────────────────────────────────────────

    def _mmap_registers(self):
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

    def _read32(self, mm, offset):
        mm.seek(offset)
        return struct.unpack("<I", mm.read(4))[0]

    def _write32(self, mm, offset, value):
        mm.seek(offset)
        mm.write(struct.pack("<I", value))

    # ── GPIO function select ─────────────────────────────────────────

    def _set_gpio_fsel(self, pin, fsel):
        reg_offset = (pin // 10) * 4
        shift = (pin % 10) * 3
        val = self._read32(self._gpio_map, reg_offset)
        val &= ~(0b111 << shift)
        val |= (fsel << shift)
        self._write32(self._gpio_map, reg_offset, val)

    def _key_on(self, pin):
        """Connect clock output to pin (ALT0)."""
        self._set_gpio_fsel(pin, FSEL_ALT0)

    def _key_off(self, pin):
        """Disconnect clock from pin (INPUT = high-Z)."""
        self._set_gpio_fsel(pin, FSEL_INPUT)

    # ── clock generator ──────────────────────────────────────────────

    def _start_clock(self, pin, divider):
        ctl_off, div_off = CLK_OFFSETS[pin]
        # Stop clock
        self._write32(self._clk_map, ctl_off, CLK_PASSWD | CLK_KILL)
        time.sleep(0.01)
        while self._read32(self._clk_map, ctl_off) & CLK_BUSY:
            time.sleep(0.001)
        # Set integer divider (no MASH = clean square wave)
        self._write32(self._clk_map, div_off,
                      CLK_PASSWD | (divider << 12))
        # Start: source = PLLD, enable
        self._write32(self._clk_map, ctl_off,
                      CLK_PASSWD | CLK_ENAB | CLK_SRC_PLLD)
        time.sleep(0.01)

    def _stop_clock(self, pin):
        self._key_off(pin)
        ctl_off, _ = CLK_OFFSETS[pin]
        self._write32(self._clk_map, ctl_off, CLK_PASSWD | CLK_KILL)
        time.sleep(0.01)

    # ── morse engine ─────────────────────────────────────────────────

    def _play_morse(self, pin, message, wpm, repeat):
        """Key the clock output on/off according to Morse timing."""
        # PARIS standard: 50 dit-lengths per word
        dit = 1.2 / wpm

        while not self._stop_event.is_set():
            words = message.upper().split()
            for wi, word in enumerate(words):
                if self._stop_event.is_set():
                    return
                for ci, char in enumerate(word):
                    if self._stop_event.is_set():
                        return
                    code = MORSE_TABLE.get(char)
                    if not code:
                        continue
                    for ei, symbol in enumerate(code):
                        if self._stop_event.is_set():
                            return
                        duration = dit if symbol == "." else dit * 3
                        self._key_on(pin)
                        self._stop_event.wait(duration)
                        self._key_off(pin)
                        # inter-element gap (1 dit)
                        if ei < len(code) - 1:
                            self._stop_event.wait(dit)
                    # inter-character gap (3 dits)
                    if ci < len(word) - 1:
                        self._stop_event.wait(dit * 3)
                # inter-word gap (7 dits)
                if wi < len(words) - 1:
                    self._stop_event.wait(dit * 7)

            if not repeat:
                break
            # gap before repeat
            self._stop_event.wait(dit * 7)

    # ── beacon thread ────────────────────────────────────────────────

    def _beacon_thread(self, pin, divider, message, wpm, repeat):
        try:
            self._mmap_registers()
            self._start_clock(pin, divider)
            self._key_off(pin)  # start silent
            self._play_morse(pin, message, wpm, repeat)
        finally:
            self._stop_clock(pin)
            with self._lock:
                self._state["active"] = False

    # ── public API ───────────────────────────────────────────────────

    def start(self, pin, freq, message, wpm=15, repeat=True):
        """Start CW beacon.  Returns result dict."""
        if pin not in CLK_OFFSETS:
            return {"ok": False,
                    "error": f"Pin {pin} has no GPCLK — use 5 or 6"}
        if not message or not message.strip():
            return {"ok": False, "error": "Message is empty"}
        if not isinstance(wpm, (int, float)) or wpm < 1 or wpm > 60:
            return {"ok": False, "error": "WPM must be 1–60"}

        divider = round(PLLD_FREQ / freq)
        if divider < 2 or divider > 4095:
            return {"ok": False,
                    "error": f"Frequency {freq} Hz out of GPCLK range"}
        actual_freq = PLLD_FREQ / divider

        with self._lock:
            if self._state["active"]:
                self._stop_internal()

            self._stop_event.clear()
            self._state.update({
                "active": True,
                "pin": pin,
                "freq_hz": actual_freq,
                "divider": divider,
                "message": message.strip(),
                "wpm": wpm,
                "repeat": repeat,
            })

            self._thread = threading.Thread(
                target=self._beacon_thread,
                args=(pin, divider, message.strip(), wpm, repeat),
                daemon=True)
            self._thread.start()

        return {
            "ok": True,
            "pin": pin,
            "freq_hz": actual_freq,
            "divider": divider,
            "message": message.strip(),
            "wpm": wpm,
            "repeat": repeat,
        }

    def stop(self):
        """Stop CW beacon."""
        with self._lock:
            self._stop_internal()
        return {"ok": True}

    def _stop_internal(self):
        """Stop beacon (caller holds _lock)."""
        self._stop_event.set()
        t = self._thread
        if t and t.is_alive():
            # Release lock briefly so the thread can update state
            self._lock.release()
            try:
                t.join(timeout=5)
            finally:
                self._lock.acquire()
        self._state["active"] = False

    def status(self):
        """Return current beacon state."""
        with self._lock:
            return dict(self._state)

    def list_frequencies(self, low=3_500_000, high=4_000_000):
        """List achievable integer-divider frequencies in a range."""
        results = []
        div_high = max(2, PLLD_FREQ // high)
        div_low = min(4095, PLLD_FREQ // low + 1)
        for d in range(div_high, div_low + 1):
            f = PLLD_FREQ / d
            if low <= f <= high:
                results.append({"divider": d, "freq_hz": f})
        return results

    def shutdown(self):
        """Clean shutdown — stop beacon if running."""
        self.stop()
