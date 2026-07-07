# Workbench MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the workbench HTTP
API as tools, so any MCP client (Claude Desktop, Claude Code, …) can drive the
bench directly — SDR, signal generator, flashing, **OTA**, serial, WiFi /
provisioning, MQTT, BLE, GPIO, GDB debug.

It is a thin stdio proxy: each tool maps 1:1 to an endpoint (`workbench_mcp.py`
holds the whole mapping in one `SPECS` table). 60 tools, matching the API. The
server is **pure Python standard library — no `pip install`** — so it runs
anywhere Python 3 does, and ships as a one-click Desktop extension.

The server runs on the machine running the MCP client (your laptop), **not** on
the Pi — it just needs network reach to the workbench, pointed by `WORKBENCH_URL`.

---

## Easiest: Claude Desktop one-click (`.mcpb`)

For most people. No terminal, no config files.

1. Make sure **Python 3** is installed (macOS has it; on Windows install from
   [python.org](https://www.python.org/downloads/) and tick **“Add Python to PATH”**).
2. Download **[`universal-embedded-workbench.mcpb`](universal-embedded-workbench.mcpb)**
   from this folder.
3. In Claude Desktop: **Settings → Extensions**, then **drag the `.mcpb` file
   onto the window** (or click **Install extension** and pick it).
4. When prompted, enter your **Workbench URL** — e.g. `http://192.168.0.87:8080`
   (find it in the workbench portal; `http://workbench.local:8080` also works on
   many networks). Click **Install**.

Done. The workbench tools appear under the tools (hammer) icon. To point at a
different bench later, open the extension’s settings and change the URL — no
reinstall needed. To update, install a newer `.mcpb` over the old one.

> The bundle is unsigned, so Desktop shows a “not verified” note on install —
> expected for a self-hosted extension; continue.

---

## Alternative: Claude Code (CLI)

```bash
claude mcp add workbench \
  --env WORKBENCH_URL=http://192.168.0.87:8080 \
  -- python3 /abs/path/to/Universal-Embedded-Workbench/mcp/workbench_mcp.py
```

Use an **absolute** path. Verify with `claude mcp list` (look for ✔ Connected).

## Alternative: Claude Desktop manual config

If you prefer editing config by hand instead of the `.mcpb`: **Settings →
Developer → Edit Config** opens `claude_desktop_config.json`
(macOS `~/Library/Application Support/Claude/`, Windows `%APPDATA%\Claude\`,
Linux `~/.config/Claude/`). Merge in:

```json
{
  "mcpServers": {
    "workbench": {
      "command": "python3",
      "args": ["/abs/path/to/Universal-Embedded-Workbench/mcp/workbench_mcp.py"],
      "env": { "WORKBENCH_URL": "http://192.168.0.87:8080" }
    }
  }
}
```

Then **fully restart** Claude Desktop (quit, not just close the window).

---

## Building the `.mcpb` yourself

The committed bundle is built from `manifest.json` + `workbench_mcp.py`:

```bash
cd mcp
npx @anthropic-ai/mcpb pack .              # or: pack <dir> <output.mcpb>
```

`manifest.json` declares the `python` server type, wires
`WORKBENCH_URL` to the `workbench_url` user-config field (what Desktop prompts
for), and validates with `npx @anthropic-ai/mcpb validate manifest.json`.

## Tools (by group)

- **discovery**: `workbench_devices`, `workbench_info`, `workbench_log`
- **flashing**: `flash` (USB, `{offset: path}` bins), `ota` (network, `firmware_path`), `firmware_list`
- **serial**: `serial_reset`, `serial_monitor`, `serial_output`, `serial_recover`, `serial_release`
- **sdr**: `sdr_status/capture/analyze/power/acquire`, `sdr_live_start/stop/status/poll`, `sdr_reset/stop`, `sdr_log_start/stop/get`
- **siggen**: `siggen_status/start/stop/freq/atten/frequencies`
- **wifi / provisioning**: `wifi_mode(_set)/scan/ap_start/ap_stop/ap_status/sta_join/sta_leave/http/ping`, `enter_portal`
- **mqtt**: `mqtt_status/start/stop`
- **ble**: `ble_status/scan/connect/disconnect/write`
- **gpio**: `gpio_status/set`
- **debug**: `debug_status/probes/start/stop`
- **misc**: `test_progress`, `human_status`, `proxy_start/stop`

`flash` and `ota` read local firmware files (paths you pass) and upload them, so
the client machine must be able to see those files.

Notes:
- One dongle / one user: SDR one-shots and the live console are mutually
  exclusive (the API returns "SDR busy").
- `ota` targets a **deployed, on-LAN** board; the Pi relays the espota push (see
  the FSD, `POST /api/ota`).
- Full endpoint/tool reference: **FSD Appendix D**.
