---
name: sdr-receiver
description: Drive the Universal Embedded Workbench's RTL-SDR receiver over `/api/sdr/*` — decode/analyze/power captures, the phased `acquire`, the interactive live rtl_433 console, "AI Sherlock" record→reverse-engineer, USB recovery, and the rtl_433 device database. Use this whenever the user wants to receive, sniff, decode, analyze, or reverse-engineer an RF signal (433/315/868 MHz remotes, sensors, TPMS), read RSSI/pulse timing, recover a wedged dongle, or add a device to rtl_433 — even if they only say "rtl_433", "rtl-sdr", "sniff a remote", "what frequency is this", "signal too strong", "no signal", "AI Sherlock", or "add this remote". This is the receive-side counterpart to the transmit-only `signal-generator` skill. Always GET `/api/sdr/status` first to confirm the dongle is detected.
---

# SDR Receiver (`/api/sdr/*`)

The workbench Pi has one RTL2832U dongle behind the `rtl_433` toolchain. Every
receive operation goes through `/api/sdr/*`. It is the receive-side counterpart
to the transmit-only `signal-generator` skill — never SSH in to run `rtl_433`
yourself, drive the API.

**One dongle, one user.** Every capture (and the whole live console) holds a
single-instance lock. While one is running, the others return
`"SDR busy — a capture is already running"`. Stop the live console before a
one-shot, and vice-versa.

---

## Always check status first

**GET `/api/sdr/status`** before anything:

```json
{"ok": true, "active": false, "mode": null, "freq_hz": 0,
 "hardware": {"rtl_433": true, "rtl_test": true, "device": true},
 "available": true}
```

- `hardware.device: false` / `available: false` → the dongle isn't detected. Try
  `POST /api/sdr/reset` (USB reset); if still absent, it's unplugged or the USB
  controller is wedged (see **Dongle recovery**).
- `active: true` → something is already using the dongle; stop it first.

---

## API summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET  | `/api/sdr/status` | Dongle/tool detection + active state |
| POST | `/api/sdr/capture` | Bounded decode window → decoded records + signal levels |
| POST | `/api/sdr/analyze` | Bounded pulse-analyzer window (`-A`) → raw pulse timing text |
| POST | `/api/sdr/power` | Narrowband `rtl_power` → `{peak_db, peak_freq_hz, mean_db}` |
| POST | `/api/sdr/acquire` | Phased guided receive: locate→level→decode→classify |
| POST | `/api/sdr/live/start` | Start the persistent live `rtl_433` console |
| POST | `/api/sdr/live/stop` | Stop the live console, release the dongle |
| GET  | `/api/sdr/live/status` | Live console running state + config |
| GET  | `/api/sdr/live?since=<seq>` | Poll the ring buffer since a sequence number |
| POST | `/api/sdr/log/start` | Begin recording the live stream (AI Sherlock) |
| POST | `/api/sdr/log/stop` | Stop recording; returns line count |
| GET  | `/api/sdr/log` | Retrieve the recorded session lines |
| POST | `/api/sdr/reset` | USB-reset a wedged dongle (operator recovery) |
| POST | `/api/sdr/stop` | Terminate an in-progress one-shot capture |

Common body fields: `freq_hz` (default 433.92 MHz), `duration_s`, `gain`
(number dB, or omit for AGC), `sample_rate` (default 250 kHz — keep low, it's a
Pi Zero 2 W), `flex` (an `-X` spec).

---

## The two big signal traps (learned the hard way)

1. **AGC saturates a too-close source.** With the tuner's default auto-gain, a
   strong near-field transmitter rails the input to full scale and fills an OOK
   signal's off-gaps — so a crisp remote reads as a continuous / misdetected
   **FSK** carrier and slices to all-zero codewords. Fix: **more distance** or a
   **fixed `gain`** (e.g. 33–40 dB). The tell is RSSI pegged near 0 dB
   regardless of distance, and `rtl_433` reporting FSK for a known-OOK remote.

2. **Decode mode is empty for unknown remotes.** Plain `decode` only emits for a
   *known* protocol. An unrecognised remote produces nothing — and no RSSI. Use
   `analyze` (or the live console, which runs `-A` in every mode) to see the
   signal regardless of decode. **Signal presence ≠ decodability.**

---

## Live console (`/api/sdr/live/*`)

A persistent `rtl_433` whose merged output a reader thread fans into a
sequence-numbered ring buffer the browser fast-polls (~500 ms; nothing dropped).
`-A` runs in **every** mode, so the RSSI meter shows every burst's strength even
when it doesn't decode.

`POST /api/sdr/live/start` body:

```json
{"freqs": [433920000], "mode": "decode",
 "gain": 33.8, "sample_rate": 250000, "squelch": false,
 "hop_interval": 5, "flex": "n=r,m=OOK_PWM,s=340,l=2068,r=13936", "isolate": false}
```

- `freqs`: one = locked, several = **hop** (`-H hop_interval`). Bands: 433.92 /
  315 / 868. Hop to *find*, then lock to a single freq to *work* (hopping listens
  to each band ~1/3 of the time and misses momentary presses).
- `mode`: `decode` (all built-ins) · `flex` (`-X`, `isolate:true` adds `-R 0`) ·
  `analyze` (`-A` only).
- `gain`: omit for AGC; a number sets a fixed tuner gain.
- Poll `GET /api/sdr/live?since=<seq>`; each entry is `{seq, line, event}` where
  `event` is the parsed JSON (or a synthetic `{rssi,snr,noise,analyzer:true}`
  from an analyzer `RSSI:` line). RSSI is **burst-driven** — it updates on a
  press, not continuously.

---

## AI Sherlock — reverse-engineer an unknown remote

The record→analyze flow the console exposes as one toggle button:

1. **Start** (`/api/sdr/log/start`) — record the live stream (analyze+AGC).
2. Operator presses each key a few times.
3. **Stop** (`/api/sdr/log/stop`) — freeze the log.
4. `GET /api/sdr/log` → an assistant reads the bursts and derives:
   modulation/timing, the **constant preamble/device-ID**, and the **per-key
   varying field**, plus a decoder spec and button→code map.

`start_log` **clears** the previous recording (single in-memory buffer, lost on
restart) — it's a record-analyze-now loop, not persistent storage.

---

## Device database (make a decode permanent)

Turn a reverse-engineered remote into a named `rtl_433` device with **one
`decoder` line per distinct code** in `pi/config/rtl_433.conf` (installed to
`/etc/rtl_433/rtl_433.conf`, which `rtl_433` auto-loads):

```
decoder n=Euromot-Awning-auto,m=OOK_PWM,s=340,l=2068,r=13936,g=2000,t=691,match={18}7f480
```

The flex decoder has **no per-value name mapping** — use one `match={<bits>}<hex>`
decoder per button, distinctly named. Verify **offline** (no signal needed):

```
rtl_433 -y '{18}7f480'   →   model : Euromot-Awning-auto
```

After that, plain `decode` mode reports the device by name. The reference build
ships the **Euromot Awning** remote (up=`7f454` down=`7f45c` auto=`7f480`
manual=`7f484`).

---

## Dongle recovery

Heavy use wedges the RTL-SDR: it still enumerates (`lsusb` shows `0bda:2838`) and
`rtl_433` opens it ("Allocating 15 zero-copy buffers") but **exits 3 at the
streaming step**, or streams with ~99% sample loss (`rtl_test` reports huge
"lost bytes"). Ladder:

1. **`POST /api/sdr/reset`** (or the console's **Reset dongle** button) — issues
   `USBDEVFS_RESET`. `start_live` also auto-resets+retries once on a fast exit.
2. If sample loss persists (`rtl_test` still loses ~everything), **reboot the
   Pi** — it clears the `dwc_otg` USB controller. This is the fix a soft reset
   can't do. (Verified: 99% loss → 12 ppm after reboot.)
3. Still bad after reboot + reseat → the dongle is failing; swap it.

Power is rarely the cause on a Zero 2 W (`vcgencmd get_throttled` = `0x0`), and
`rtl_433` at 250 kHz uses only ~5–6 % CPU — so exhaustion/undervoltage are
usually red herrings; suspect the USB link.

---

## Driver methods (`pytest/workbench_driver.py`)

```python
wt.sdr_status()
wt.sdr_capture(freq_hz=433_920_000, duration_s=10, flex="n=r,m=OOK_PWM,s=340,l=2068,r=13936", gain=33.8)
wt.sdr_analyze(freq_hz=433_920_000, duration_s=12, gain=33.8)
wt.sdr_power(freq_hz=433_920_000, duration_s=5, span_hz=500_000, bin_hz=10_000)
wt.sdr_acquire(freq_hz=433_920_000)      # phased locate→level→decode→classify
```

The `tools/sdr_acquire.py` CLI drives the phased acquire interactively with live
operator prompts (run it in a *real terminal* — the prompts don't stream through
Claude Code's `!` prefix, which buffers until exit).

---

## Recipes

### "What is this remote / what frequency?"

Start the live console at 433.92 in **analyze** mode with AGC, press the remote:
the reported `freq` field is the true carrier, and the analyzer prints pulse
timing + a suggested `-X`. If nothing appears, it's likely 315 or 868 — hop, or
`POST /api/sdr/power` a wide span and read `peak_freq_hz`.

### "It won't decode / signal too strong"

RSSI pegged near 0 dB + FSK on a known-OOK remote = **overload**. Turn AGC off,
set a fixed `gain` ~33 dB, back the transmitter off, retry. Then decode with the
right `flex`.

### "Add this remote to rtl_433"

AI Sherlock → analyze the log → append `decoder` line(s) to `pi/config/rtl_433.conf`
→ `rtl_433 -y` to verify → deploy → it's recognised by name.

---

## Behavior to be aware of

- **Single dongle.** Live console vs one-shots are mutually exclusive ("SDR busy").
- **`-A` in every live mode** → the RSSI/signal meter is decode-independent.
- **Burst-driven RSSI** — a continuous level bar (to tune against the noise
  floor with no transmission) would need a separate `rtl_power` meter; not built.
- **Pi Zero 2 W** — keep `sample_rate` at 250 kHz; wideband overloads it. Use
  `-Y squelch` to cut CPU.
- **Session log is ephemeral** — cleared on Start, lost on portal restart.

---

## Reference

- Functional spec: `docs/Embedded-Workbench-FSD.md` §FR-028 (SDR Receiver).
- Controller: `pi/sdr_controller.py`. HTTP handlers: `pi/portal.py` (`_handle_sdr_*`, the SDR Console panel).
- Driver: `pytest/workbench_driver.py` (`sdr_*`). CLI: `tools/sdr_acquire.py`.
- Device database: `pi/config/rtl_433.conf` → `/etc/rtl_433/rtl_433.conf`.
