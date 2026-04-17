"""Morse keyer — backend-agnostic.

Takes any object with ``key_on()`` / ``key_off()`` and plays a message at the
requested words-per-minute.  GPCLK gates the pin via ALT0/INPUT; the Si5351
backend gates its output-enable register.  Same timing engine for both.
"""

import threading

# ITU Morse code table
MORSE_TABLE: dict[str, str] = {
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


class MorseKeyer:
    """Plays a Morse message by calling ``keyer.key_on()``/``key_off()``.

    The keyer object is anything with ``key_on()`` and ``key_off()`` methods.
    Timing follows PARIS standard (50 dit-lengths per word).
    """

    def __init__(self, keyer) -> None:
        self._keyer = keyer
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, message: str, wpm: float = 15, repeat: bool = True) -> None:
        if not message or not message.strip():
            raise ValueError("Message is empty")
        if not (1 <= wpm <= 60):
            raise ValueError("WPM must be 1–60")
        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, args=(message.strip(), wpm, repeat),
            daemon=True, name="morse-keyer")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=5)
        # Ensure carrier is gated off on exit
        try:
            self._keyer.key_off()
        except Exception:
            pass
        self._thread = None

    def is_active(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    # ── private ──────────────────────────────────────────────────────

    def _run(self, message: str, wpm: float, repeat: bool) -> None:
        dit = 1.2 / wpm
        try:
            while not self._stop_event.is_set():
                if self._play_once(message, dit):
                    return
                if not repeat:
                    break
                self._stop_event.wait(dit * 7)
        finally:
            try:
                self._keyer.key_off()
            except Exception:
                pass

    def _play_once(self, message: str, dit: float) -> bool:
        """Play one pass of *message*.  Returns True if stopped mid-way."""
        words = message.upper().split()
        for wi, word in enumerate(words):
            if self._stop_event.is_set():
                return True
            for ci, char in enumerate(word):
                if self._stop_event.is_set():
                    return True
                code = MORSE_TABLE.get(char)
                if not code:
                    continue
                for ei, symbol in enumerate(code):
                    if self._stop_event.is_set():
                        return True
                    duration = dit if symbol == "." else dit * 3
                    self._keyer.key_on()
                    self._stop_event.wait(duration)
                    self._keyer.key_off()
                    if ei < len(code) - 1:
                        self._stop_event.wait(dit)
                if ci < len(word) - 1:
                    self._stop_event.wait(dit * 3)
            if wi < len(words) - 1:
                self._stop_event.wait(dit * 7)
        return False
