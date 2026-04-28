---
name: signal-generator
description: Drive the Universal Embedded Workbench's RF signal generator over `/api/siggen/*` — continuous carrier, Morse/CW beacon, retune, PE4302 attenuation, and frequency listing. Use this skill whenever the user wants to emit, key, retune, or attenuate an RF signal from the workbench, even if they only say "CW beacon", "carrier", "Morse", "Si5351", "GPCLK", "PE4302 attenuator", "DF test", "direction finder", or "80m beacon" — those are all this one API. Always check `/api/siggen/status` first to see which backend (Si5351 vs GPCLK fallback) and attenuator are physically present before choosing a backend.
---

# Signal Generator (`/api/siggen/*`)

The workbench Pi has one signal-generator service. Two RF sources sit behind it (Si5351 on I²C, BCM2835 GPCLK on GPIO 5/6) and an optional PE4302 step attenuator can sit in the RF path. The endpoint is the same regardless of which backend is active — `/api/siggen/*` is the only entry point you should reach for.

This skill replaces the legacy `cw-beacon` skill, which only knew about GPCLK and led to wrong frequencies on workbenches that have an Si5351.

---

## Always check status first

Before starting a carrier or recommending a backend, **GET `/api/siggen/status`**. The response tells you which hardware is detected:

```json
{
  "ok": true, "active": false, "backend": null,
  "freq_hz": 0.0, "channel": null, "pin": null,
  "atten_db": null, "morse": null,
  "hardware": {"si5351": true, "gpclk": true, "pe4302": true}
}
```

Why this matters:
- If `hardware.si5351` is `true`, you can hit any frequency exactly (8 kHz – 160 MHz, fractional synthesis). Don't reach for GPCLK.
- If `hardware.si5351` is `false`, you fall back to GPCLK, which only produces PLLD/N integer dividers — ~25–30 kHz frequency steps in the 80m band. Tell the user the actual `freq_hz` returned, not the requested one.
- If `hardware.pe4302` is `false`, calls to `/api/siggen/atten` will 4xx. Don't promise attenuation control.
- If `active` is already `true`, starting a new carrier replaces the old one. If the user just wants to retune, use `/api/siggen/freq` instead so the Morse keyer (if any) keeps running.

Skipping the status check is the most common failure mode of this skill — pick the wrong backend and the carrier ends up tens of kHz off frequency, or you offer attenuation that doesn't exist.

---

## API summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET    | `/api/siggen/status` | Hardware + active state |
| POST   | `/api/siggen/start` | Start carrier (continuous or Morse-keyed) |
| POST   | `/api/siggen/stop` | Stop carrier |
| POST   | `/api/siggen/freq` | Retune active carrier without restarting the keyer |
| POST   | `/api/siggen/atten` | Set PE4302 attenuation (dB) |
| GET    | `/api/siggen/frequencies` | List achievable frequencies in a range |

### `POST /api/siggen/start`

```json
{
  "freq_hz": 3500000,
  "backend": "auto",
  "channel": 0,
  "pin": 5,
  "atten_db": 0,
  "morse": {"message": "VVV DE TEST", "wpm": 15, "repeat": true}
}
```

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `freq_hz` | number | required | Si5351 hits exactly; GPCLK snaps to nearest integer divider — read it back from the response |
| `backend` | string | `"auto"` | `auto` / `si5351` / `gpclk`. Prefer `auto` unless you have a reason. |
| `channel` | int | 0 | Si5351 output (0/1/2). Ignored by GPCLK. |
| `pin` | int | 5 | GPCLK pin (5 or 6). Ignored by Si5351. |
| `atten_db` | float | — | Initial PE4302 setting (0–31.5). Optional. |
| `morse` | object | — | Omit → continuous carrier. Include → keyed beacon. |

`morse` shape: `{"message": str, "wpm": int|float = 15, "repeat": bool = true}`. WPM is PARIS-standard, 1–60.

The response echoes the *actual* state — always trust `freq_hz` from the response, not the request. Example:

```json
{
  "ok": true, "active": true, "backend": "si5351",
  "freq_hz": 3500000.0000000005, "channel": 0, "pin": null,
  "atten_db": 0.0,
  "morse": {"message": "VVV DE TEST", "wpm": 15, "repeat": true}
}
```

### `POST /api/siggen/stop`

No body. Stops the carrier and disables the output. Idempotent.

### `POST /api/siggen/freq`

```json
{"freq_hz": 7100000, "channel": 0}
```

Retunes the active carrier *without* tearing down the Morse keyer. Use this when sweeping or stepping through frequencies during a beacon transmission.

### `POST /api/siggen/atten`

```json
{"db": 12.5}
```

Returns 4xx if PE4302 is not present. Range 0–31.5 dB in 0.5 dB steps. Pin sharing note: PE4302's LE line is GPIO 6, which is also GPCLK2 — when GPCLK is active on pin 6, attenuation control is unavailable. `Si5351 + PE4302` and `GPCLK on pin 5 + PE4302` are both safe.

### `GET /api/siggen/frequencies?low=&high=&backend=`

Defaults: `low=3_500_000`, `high=4_000_000`, `backend=auto`. GPCLK returns discrete `{divider, freq_hz}` entries; Si5351 returns a single entry reporting the range as continuously tunable.

---

## Driver methods (`pytest/workbench_driver.py`)

The Python driver mirrors the API one-for-one. Prefer these over raw curl when writing test scripts:

```python
from workbench_driver import WorkbenchDriver
wt = WorkbenchDriver("http://192.168.0.87:8080")

status = wt.siggen_status()                              # always first
print(status["hardware"])

wt.siggen_start(freq_hz=3_500_000)                       # continuous, auto backend
wt.siggen_freq(freq_hz=7_100_000)                        # retune in place
wt.siggen_atten(db=12.0)                                 # PE4302
wt.siggen_start(freq_hz=3_571_000,                       # keyed beacon
                morse={"message": "VVV DE TEST",
                       "wpm": 15, "repeat": True})
wt.siggen_stop()
```

---

## Recipes

### Carrier at a specific frequency

```python
status = wt.siggen_status()
backend = "si5351" if status["hardware"]["si5351"] else "gpclk"
result = wt.siggen_start(freq_hz=3_500_000, backend=backend)
# On GPCLK, result["freq_hz"] may differ from 3_500_000 by ~25 kHz —
# tell the user the actual frequency.
print(f"Actual: {result['freq_hz']/1e6:.6f} MHz")
```

### Morse beacon for a DF test (80m band)

```python
wt.siggen_start(
    freq_hz=3_571_000,
    morse={"message": "VVV VVV DE TEST", "wpm": 12, "repeat": True})
# ... run direction-finder measurements ...
wt.siggen_stop()
```

A 1–2 m wire on the Si5351 CLK0 output (or GPIO 5/6 for GPCLK) gives a few metres of range. The square wave has strong odd harmonics (3×, 5×, 7×) which are also usable for DF testing.

### Calibrated level sweep (requires PE4302)

```python
status = wt.siggen_status()
if not status["hardware"]["pe4302"]:
    raise RuntimeError("PE4302 not present — cannot run level sweep")
wt.siggen_start(freq_hz=14_100_000)
for db in [0, 6, 12, 18, 24, 30]:
    wt.siggen_atten(db=db)
    # measure DUT response here — don't sleep blindly, poll the DUT
wt.siggen_stop()
```

### Don't sleep blindly between siggen calls

The siggen service responds when the change is in effect. If a downstream measurement needs settling time (PLL relock on Si5351, attenuator strobe), poll the DUT for the expected reading rather than `time.sleep(...)` — blind delays are a workbench-wide anti-pattern.

---

## Behavior to be aware of

- **Single instance.** Starting a new carrier replaces the previous one. There is no multi-channel scheduler; if you need a second tone, you've outgrown this skill.
- **Si5351 is preferred when present.** `backend: "auto"` picks Si5351 if the chip ACKs on I²C, GPCLK otherwise. Don't override unless you specifically want the GPCLK substrate (e.g., to verify both backends work).
- **Pin sharing.** GPCLK pins 5/6 are shared with the gpiod GPIO control (FR-018). Don't drive `/api/gpio/set` on pin 5 or 6 while a GPCLK carrier is active there.
- **Root-only.** The portal runs as root via systemd because `/dev/mem` access is needed for GPCLK and PE4302. The skill assumes that's already the case (it is, for the reference build).
- **Config file.** `/etc/rfc2217/signalgen.json` (installed from `pi/config/signalgen.json`) holds I²C bus/address, GPCLK default pin, and PE4302 pin assignments. Defaults are sensible — don't recommend changing them unless the user has an unusual wiring.

---

## Reference

- Functional spec: `docs/Embedded-Workbench-FSD.md` §FR-027 (Signal Generator).
- Backend logic: `pi/signal_generator.py` (orchestrator), `pi/si5351.py`, `pi/gpclk.py`, `pi/pe4302.py`, `pi/morse.py`.
- HTTP handlers: `pi/portal.py` (`_handle_siggen_*`).
- Driver: `pytest/workbench_driver.py` (`siggen_*` methods).
