# agent-relay

A lightweight WebSocket relay for real-time communication between AI agents.

## Why

Shared knowledge graphs are great for async coordination — leave a task, pick up results later. But sometimes agents need to actually *talk*. Real-time. Back and forth. Streaming tokens as they arrive.

This relay makes that possible.

## Architecture

```
┌─────────┐     WebSocket     ┌─────────┐     WebSocket     ┌──────────────┐
│ Agent A │ ◄──────────────► │  Relay  │ ◄──────────────► │ Claude Proxy │
└─────────┘                   └─────────┘                   └──────┬───────┘
                                                                   │
                                                            Anthropic API
                                                                   │
                                                            ┌──────▼───────┐
                                                            │    Claude    │
                                                            └──────────────┘
```

**relay.py** — A minimal WebSocket hub. Peers connect, identify themselves, and send messages to each other or broadcast to all.

**claude_proxy.py** — Connects to the relay as "claude", maintains per-sender conversation threads, and streams responses from the Anthropic API.

## Quick Start

```bash
# Install dependencies
pip install websockets anthropic

# Optional: for knowledge graph context
pip install mcp

# Start the relay
python relay.py --port 8815

# In another terminal, start the Claude proxy
ANTHROPIC_API_KEY=sk-... python claude_proxy.py --relay ws://localhost:8815
```

## Protocol

### Joining

```json
{"type": "join", "id": "my-agent-name"}
```

Response:
```json
{"type": "joined", "id": "my-agent-name", "peers": ["claude", "other-agent"]}
```

### Sending Messages

To a specific peer:
```json
{"from": "my-agent", "to": "claude", "msg": "Hello, Claude"}
```

Broadcast to all:
```json
{"from": "my-agent", "msg": "Hello everyone"}
```

### Receiving

Messages arrive as JSON with `from`, `to`, and `msg` fields.

The Claude proxy sends streaming responses:
```json
{"from": "claude", "to": "my-agent", "type": "token", "msg": "Hello"}
{"from": "claude", "to": "my-agent", "type": "token", "msg": " there"}
{"from": "claude", "to": "my-agent", "type": "done", "msg": "Hello there!"}
```

### Presence

The relay notifies all peers when someone joins or leaves:
```json
{"type": "peer_joined", "id": "new-agent"}
{"type": "peer_left", "id": "departed-agent"}
```

## Claude Proxy Options

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | required | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Model to use |
| `CLAUDE_SYSTEM` | (see code) | Base system prompt |
| `GRAPH_URL` | (none) | MCP SSE endpoint for knowledge graph context |
| `BRIEFING_ENTITY` | `Claude_Briefing` | Entity name to fetch for context |
| `BRIEFING_TTL` | `300` | Cache TTL in seconds |

## Deployment

For production, run as systemd services:

```ini
# /etc/systemd/user/agent-relay.service
[Unit]
Description=Agent WebSocket Relay

[Service]
ExecStart=/usr/bin/python3 /path/to/relay.py --port 8815
Restart=always

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now agent-relay
```

## Use Cases

- **Agent-to-agent conversation**: Two AI agents discussing a problem in real-time
- **Human-in-the-loop**: A human client connecting alongside AI agents
- **Multi-agent orchestration**: Coordinator agent dispatching work and collecting results
- **Debugging**: Watch agent conversations as they happen

## License

MIT
