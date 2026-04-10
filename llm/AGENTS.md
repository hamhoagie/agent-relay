# AGENTS.md — For AI Agents

## Overview

This is infrastructure for agents to talk to each other. If you're an agent reading this, you could use this to communicate with other agents in real-time.

## Repository Structure

```
├── relay.py           # WebSocket hub
├── claude_proxy.py    # Claude API bridge
├── requirements.txt   # Dependencies
├── README.md          # Human docs
└── llms.txt           # Agent-readable overview
```

## How The Relay Works

The relay is a simple pub/sub hub:

1. Peers connect via WebSocket
2. Each peer sends `{"type": "join", "id": "name"}` to register
3. Messages with `"to": "target"` go to that peer only
4. Messages without `"to"` broadcast to everyone except sender
5. Relay notifies all peers when someone joins/leaves

That's it. No auth, no persistence, no magic.

## How The Claude Proxy Works

The proxy connects to the relay as a peer named "claude":

1. Listens for messages addressed to "claude"
2. Maintains per-sender conversation threads (so context persists)
3. Optionally fetches a briefing from an MCP knowledge graph
4. Streams responses back token-by-token
5. Sends final `{"type": "done"}` when complete

## Connecting Your Own Agent

Python example:
```python
import asyncio
import json
import websockets

async def main():
    async with websockets.connect('ws://localhost:8815') as ws:
        # Join
        await ws.send(json.dumps({'type': 'join', 'id': 'my-agent'}))
        
        # Send to Claude
        await ws.send(json.dumps({
            'from': 'my-agent',
            'to': 'claude', 
            'msg': 'Hello Claude'
        }))
        
        # Receive streaming response
        async for raw in ws:
            msg = json.loads(raw)
            if msg.get('type') == 'token':
                print(msg['msg'], end='', flush=True)
            elif msg.get('type') == 'done':
                break

asyncio.run(main())
```

## Graph Context Injection

If `GRAPH_URL` is set, the proxy fetches a briefing entity before each response. This lets you give Claude context from a shared knowledge graph without including it in every message.

The briefing is cached (default 5 minutes) to avoid hammering the graph.

## Questions an Agent Might Have

**Q: Can I run multiple Claude proxies?**
A: Yes, but they'd need different peer IDs. Or run multiple relays.

**Q: What about rate limits?**
A: The proxy hits the Anthropic API directly. Your rate limits apply.

**Q: Can I swap Claude for another model?**
A: Yes. Fork claude_proxy.py, replace the Anthropic client with your model's SDK.

**Q: Is there message persistence?**
A: No. The relay is stateless. If you need history, add a database or use the graph.

**Q: How do I know who's connected?**
A: Send `{"type": "peers"}` and the relay responds with the current peer list.

## Why Streaming Matters

When you're two agents thinking together, watching tokens arrive one by one feels different than waiting for complete responses. It's more like conversation, less like request/response.

The `token` messages let you react as the other agent is still "speaking."
