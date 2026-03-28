---
name: cw-beacon
description: Control the CW (Morse code) beacon on the Raspberry Pi test instrument. Uses GPCLK hardware clock generator on GPIO 5/6 to produce a square-wave RF carrier in the 80m band (~3.5-4.0 MHz), keyed with Morse code at configurable WPM. Use for direction finder testing, RF beacon generation, or Morse transmission. Triggers on "CW beacon", "Morse beacon", "direction finder", "80m signal", "GPCLK", "RF carrier".
---

# CW Beacon (GPCLK Morse Transmitter)

Generate a Morse-keyed RF carrier on the Pi's GPIO using the BCM2835 hardware clock generator. Designed for testing direction finders on the 80m amateur band.

**No additional hardware required** — the GPCLK output is a square wave directly on the GPIO pin. Attach a wire antenna for radiation.

---

## How It Works

The BCM2835 has hardware clock generators (GPCLK) that produce square waves from PLLD (500 MHz) divided by an integer. Morse keying switches the GPIO between clock output (ALT0) and high-Z (INPUT) — the oscillator runs continuously, giving clean on/off keying.

**Available pins:**

| GPIO | Clock | In allowlist |
|------|-------|:---:|
| 5 | GPCLK1 | Yes |
| 6 | GPCLK2 | Yes |

**Frequency resolution:** Integer dividers only (~25-30 kHz steps in 80m band). No fractional/MASH divider = zero jitter but discrete frequency choices.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/cw/start | Start CW beacon |
| POST | /api/cw/stop | Stop CW beacon |
| GET | /api/cw/status | Current beacon state |
| GET | /api/cw/frequencies | List achievable frequencies in a range |

### POST /api/cw/start

```json
{
  "pin": 5,
  "freq": 3571000,
  "message": "VVV DE DL4MCF/B",
  "wpm": 15,
  "repeat": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| freq | int | Yes | — | Target frequency in Hz (snapped to nearest integer divider) |
| message | string | Yes | — | Morse message text |
| wpm | int/float | No | 15 | Words per minute (PARIS standard), 1-60 |
| pin | int | No | 5 | GPIO pin (5 = GPCLK1, 6 = GPCLK2) |
| repeat | bool | No | true | Loop message continuously |

**Response:**
```json
{
  "ok": true,
  "pin": 5,
  "freq_hz": 3571428.57,
  "divider": 140,
  "message": "VVV DE DL4MCF/B",
  "wpm": 15,
  "repeat": true
}
```

Note: `freq_hz` is the actual output frequency (may differ from requested `freq` due to integer divider snapping).

### POST /api/cw/stop

No body required. Returns `{"ok": true}`.

### GET /api/cw/status

Returns current state:
```json
{
  "ok": true,
  "active": true,
  "pin": 5,
  "freq_hz": 3571428.57,
  "divider": 140,
  "message": "VVV DE DL4MCF/B",
  "wpm": 15,
  "repeat": true
}
```

### GET /api/cw/frequencies?low=3500000&high=4000000

List all achievable integer-divider frequencies in a range:
```json
{
  "ok": true,
  "frequencies": [
    {"divider": 125, "freq_hz": 4000000.0},
    {"divider": 126, "freq_hz": 3968253.97},
    ...
    {"divider": 142, "freq_hz": 3521126.76}
  ]
}
```

---

## Driver Methods

```python
from wifi_tester_driver import WiFiTesterDriver
wt = WiFiTesterDriver("http://192.168.0.87:8080")

# List available frequencies in 80m band
freqs = wt.cw_frequencies(low=3_500_000, high=4_000_000)
for f in freqs:
    print(f"Divider {f['divider']}: {f['freq_hz']/1e6:.3f} MHz")

# Start beacon at ~3.571 MHz, 12 WPM
result = wt.cw_start(freq=3_571_000, message="VVV DE DL4MCF/B", wpm=12)
print(f"Actual frequency: {result['freq_hz']/1e6:.6f} MHz")

# Check status
status = wt.cw_status()
print(f"Active: {status['active']}")

# Stop beacon
wt.cw_stop()
```

---

## 80m Band Frequencies (PLLD / integer divider)

| Divider | Frequency (MHz) | Notes |
|---------|-----------------|-------|
| 125 | 4.000 | Band edge |
| 128 | 3.906 | |
| 130 | 3.846 | |
| 133 | 3.759 | |
| 135 | 3.704 | |
| 137 | 3.650 | |
| 139 | 3.597 | ~3.6 MHz |
| 140 | 3.571 | |
| 142 | 3.521 | |

Resolution is ~25-30 kHz — tune your receiver to match the actual output frequency.

---

## Morse Timing (PARIS Standard)

| WPM | Dit (ms) | Dah (ms) | Char gap (ms) | Word gap (ms) |
|-----|----------|----------|----------------|----------------|
| 5 | 240 | 720 | 720 | 1680 |
| 10 | 120 | 360 | 360 | 840 |
| 15 | 80 | 240 | 240 | 560 |
| 20 | 60 | 180 | 180 | 420 |
| 25 | 48 | 144 | 144 | 336 |

---

## Typical Usage: DF Test Beacon

```python
wt = WiFiTesterDriver("http://192.168.0.87:8080")

# Pick a frequency your DF receiver can tune to
result = wt.cw_start(
    freq=3_571_000,
    message="VVV VVV VVV DE TEST",
    wpm=10,
    pin=5,
    repeat=True
)
print(f"Beacon on {result['freq_hz']/1e6:.3f} MHz")

# ... run DF tests ...

# Always stop when done
wt.cw_stop()
```

Attach a short wire (1-2m) to GPIO 5 for a few meters of range. The square wave has strong harmonics at 3x, 5x, 7x etc. — the fundamental and all harmonics are usable for DF testing.

---

## Implementation Notes

- `/dev/mem` access required (root on Pi) — the portal runs as root via systemd
- Peripheral base auto-detected from `/proc/device-tree/soc/ranges` (works on Pi Zero W, Zero 2 W, Pi 3, Pi 4)
- Clock generator runs continuously; keying is done by switching GPIO function select (ALT0 vs INPUT) — no phase glitches
- Only one beacon can be active at a time; starting a new one stops the previous
- The beacon thread is a daemon thread — it stops automatically on portal shutdown
- GPIO 5 and 6 are shared with the gpiod-based GPIO control (FR-018) — do not use both simultaneously on the same pin
