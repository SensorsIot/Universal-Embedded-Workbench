# Workbench MCP server

An [MCP](https://modelcontextprotocol.io) server that exposes the workbench HTTP
API as tools, so any MCP client (Claude Code, Claude Desktop, …) can drive the
bench directly — SDR, signal generator, flashing, **OTA**, serial, WiFi /
provisioning, MQTT, BLE, GPIO, GDB debug.

It is a thin stdio proxy: each tool maps 1:1 to an endpoint (`workbench_mcp.py`
holds the whole mapping in one `SPECS` table). ~60 tools, matching the API.

## Install

```bash
pip install -r mcp/requirements.txt      # mcp, requests
```

The server runs on the **client** machine (the one running the MCP client), not
on the Pi — it just needs network reach to the workbench. Point it with
`WORKBENCH_URL` (default `http://192.168.0.87:8080`).

## Add to Claude Code

```bash
claude mcp add workbench \
  --env WORKBENCH_URL=http://192.168.0.87:8080 \
  -- python3 /abs/path/to/Universal-Embedded-Workbench/mcp/workbench_mcp.py
```

## Add to Claude Desktop

In `claude_desktop_config.json`:

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
