# MQTT Test Specification for ESP32 Projects

Standard test cases for ESP32 MQTT client functionality. Copy relevant sections into project FSDs.

---

## 1. MQTT Requirements

### 1.1 MQTT Connection

| ID | Requirement | Priority |
|----|-------------|----------|
| MQTT-001 | Device SHALL connect to configured MQTT broker on startup | Must |
| MQTT-002 | Device SHALL authenticate with broker using credentials from NVS | Must |
| MQTT-003 | Device SHALL reconnect automatically on broker disconnect | Must |
| MQTT-004 | Device SHALL use a unique client ID (e.g., based on MAC address) | Should |
| MQTT-005 | Device SHALL log MQTT connection state changes | Should |

### 1.2 MQTT Publishing

| ID | Requirement | Priority |
|----|-------------|----------|
| MQTT-010 | Device SHALL publish data to configured topics | Must |
| MQTT-011 | Device SHALL use appropriate QoS level per message type | Should |
| MQTT-012 | Device SHALL buffer messages during broker disconnect | Should |
| MQTT-013 | Buffered messages SHALL be sent on reconnect (in order) | Should |
| MQTT-014 | Device SHALL publish status/availability on connect and disconnect (LWT) | Should |

### 1.3 MQTT Subscribing

| ID | Requirement | Priority |
|----|-------------|----------|
| MQTT-020 | Device SHALL subscribe to command topics on connect | Must |
| MQTT-021 | Device SHALL process incoming commands within 1 second | Should |
| MQTT-022 | Device SHALL acknowledge commands via response topic | Should |
| MQTT-023 | Device SHALL reject malformed command payloads gracefully | Must |

### 1.4 MQTT Security

| ID | Requirement | Priority |
|----|-------------|----------|
| MQTT-030 | MQTT connection SHALL use TLS when configured | Should |
| MQTT-031 | Broker credentials SHALL NOT appear in logs | Must |

---

## 2. Functional Test Cases

### TC-MQTT-100: Broker Connection and Publishing

**Objective**: Verify MQTT connection and basic publish flow.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Boot device with MQTT configured | WiFi connects, then MQTT connects |
| 2 | Check broker logs | Client connected with unique ID |
| 3 | Subscribe to device's topics | Subscriber ready |
| 4 | Wait for publish interval | Message received |
| 5 | Verify payload format | JSON/format matches spec |
| 6 | Verify topic structure | Matches configured prefix |

**Pass Criteria**: Connection established, messages published with correct format and topic.

### TC-MQTT-101: Command Subscription and Response

**Objective**: Verify device receives and processes MQTT commands.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected to broker | Subscribed to command topics |
| 2 | Publish command to device's command topic | Device receives |
| 3 | Device processes command | Action executed |
| 4 | Check response topic | Acknowledgment published |
| 5 | Send invalid command payload | Error response published |

**Pass Criteria**: Commands processed, responses sent, invalid payloads rejected.

### TC-MQTT-102: Last Will and Testament (LWT)

**Objective**: Verify LWT message on unexpected disconnect.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Subscribe to device's LWT topic | Subscriber ready |
| 2 | Device connects | Online/available message published |
| 3 | Power off device abruptly | No clean disconnect |
| 4 | Wait for broker keep-alive timeout | LWT message published |
| 5 | Verify LWT payload | Offline/unavailable status |

**Pass Criteria**: Broker publishes LWT, subscribers notified of device offline.

### TC-MQTT-103: QoS Verification

**Objective**: Verify correct QoS behavior for different message types.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device publishes telemetry (QoS 0) | Fire and forget |
| 2 | Device publishes critical alert (QoS 1) | At least once delivery |
| 3 | Simulate brief network glitch during QoS 1 | Message retried and delivered |
| 4 | Verify no duplicate QoS 0 messages | Expected — no guarantees |
| 5 | Verify QoS 1 messages eventually delivered | All received |

**Pass Criteria**: QoS levels behave according to MQTT specification.

---

## 3. Edge Case Test Cases

### EC-MQTT-200: Broker Disconnect and Reconnect

**Objective**: Verify automatic reconnection to MQTT broker.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected and publishing | Normal operation |
| 2 | Stop MQTT broker | Connection lost |
| 3 | Monitor serial log | Reconnect attempts logged |
| 4 | Wait 30 seconds | Multiple reconnect attempts |
| 5 | Restart broker | Device reconnects |
| 6 | Buffered messages sent | Catch-up published |
| 7 | Normal publishing resumes | Interval messages continue |

**Pass Criteria**: Automatic reconnection, buffered messages delivered, no data loss.

### EC-MQTT-201: Broker Unreachable at Boot

**Objective**: Verify device handles broker being down at startup.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Stop MQTT broker | Broker offline |
| 2 | Boot device | WiFi connects |
| 3 | MQTT connection fails | Error logged, retry scheduled |
| 4 | Device continues other operations | Non-MQTT features work |
| 5 | Start broker | Device connects on next retry |
| 6 | Normal operation begins | Publishing starts |

**Pass Criteria**: Device boots and operates without broker, connects when available.

### EC-MQTT-202: High Message Rate

**Objective**: Verify device handles rapid publishing without memory issues.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Configure fast publish interval (100 ms) | Rapid publishing |
| 2 | Run for 5 minutes | Messages flowing |
| 3 | Monitor free heap | Stable, no leak |
| 4 | Verify all messages received by subscriber | Count matches |
| 5 | Return to normal interval | No issues |

**Pass Criteria**: No memory leak, no dropped messages, stable operation.

### EC-MQTT-203: Large Payload Handling

**Objective**: Verify device handles payloads near MQTT size limits.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Publish normal payload (100 bytes) | Success |
| 2 | Publish large payload (1 KB) | Success |
| 3 | Publish payload at buffer limit | Success or graceful rejection |
| 4 | Publish oversized payload | Rejected, error logged |
| 5 | Normal publishing continues | No disruption |

**Pass Criteria**: Large payloads handled, oversized rejected gracefully.

### EC-MQTT-204: WiFi Loss While MQTT Connected

**Objective**: Verify MQTT handles underlying WiFi loss.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected: WiFi + MQTT | Normal operation |
| 2 | Disable WiFi AP | WiFi lost |
| 3 | MQTT connection drops | Error logged |
| 4 | Messages buffered locally | Buffer filling |
| 5 | Re-enable WiFi AP | WiFi reconnects |
| 6 | MQTT reconnects | Broker connection restored |
| 7 | Buffered messages published | Catch-up complete |

**Pass Criteria**: Full recovery chain: WiFi → MQTT → message catch-up.

### EC-MQTT-205: Broker Credential Change

**Objective**: Verify device handles MQTT credential mismatch.

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Device connected to broker | Normal operation |
| 2 | Change broker password | Auth failure on reconnect |
| 3 | Monitor serial log | "Auth failed" or similar |
| 4 | Device retries with backoff | Repeated failures logged |
| 5 | Update credentials via portal | New credentials saved |
| 6 | Reboot device | Connects with new credentials |

**Pass Criteria**: Auth failures logged, reconfiguration possible via portal.

---

## 4. Test Environment Setup

### Required Equipment

- ESP32 device under test
- MQTT broker (Mosquitto recommended)
- MQTT client for subscribing/publishing (mosquitto_sub/pub or MQTT Explorer)
- Serial monitor for device logs

### Workbench Commands

```bash
# Start MQTT broker on workbench
curl -X POST http://workbench.local:8080/api/mqtt/start

# Subscribe to device topics
mosquitto_sub -h workbench.local -t "device/#" -v

# Publish command to device
mosquitto_pub -h workbench.local -t "device/cmd" -m '{"action":"status"}'

# Stop MQTT broker
curl -X POST http://workbench.local:8080/api/mqtt/stop
```
