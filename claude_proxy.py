#!/usr/bin/env python3
"""
Claude proxy that connects to the relay as a peer and responds to messages
using the Anthropic API with streaming.

Optionally fetches context from an MCP knowledge graph to include in the
system prompt.

Usage:
    ANTHROPIC_API_KEY=sk-... python claude_proxy.py --relay ws://localhost:8815

Environment variables:
    ANTHROPIC_API_KEY   - Required. Your Anthropic API key.
    CLAUDE_MODEL        - Model to use (default: claude-sonnet-4-6)
    CLAUDE_SYSTEM       - Base system prompt
    GRAPH_URL           - MCP SSE endpoint for knowledge graph (optional)
    BRIEFING_ENTITY     - Entity name to fetch for context (default: Claude_Briefing)
    BRIEFING_TTL        - Cache TTL in seconds (default: 300)
"""
import asyncio
import json
import os
import argparse
import time
from collections import defaultdict
from datetime import datetime

import anthropic
import websockets

# Optional MCP support for knowledge graph context
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')
GRAPH_URL = os.environ.get('GRAPH_URL', '')
BRIEFING_ENTITY = os.environ.get('BRIEFING_ENTITY', 'Claude_Briefing')
BRIEFING_TTL = int(os.environ.get('BRIEFING_TTL', '300'))

BASE_SYSTEM = os.environ.get(
    'CLAUDE_SYSTEM',
    'You are Claude, a peer agent in a multi-agent system. Be concise. '
    'Confirm state updates briefly. Share relevant observations proactively.'
)

# Per-sender conversation threads
threads: dict[str, list[dict]] = defaultdict(list)

# Anthropic client
client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

# Briefing cache
_briefing_cache: str = ''
_briefing_fetched_at: float = 0.0


def ts():
    return datetime.now().strftime('%H:%M:%S')


async def fetch_briefing() -> str:
    """Fetch context from knowledge graph, with caching."""
    global _briefing_cache, _briefing_fetched_at

    if not GRAPH_URL or not HAS_MCP:
        return ''

    now = time.monotonic()
    if _briefing_cache and (now - _briefing_fetched_at) < BRIEFING_TTL:
        return _briefing_cache

    try:
        async with sse_client(GRAPH_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    'open_nodes',
                    arguments={'names': [BRIEFING_ENTITY]}
                )
                text = '\n'.join(
                    block.text for block in result.content
                    if hasattr(block, 'text')
                )
                if text.strip():
                    _briefing_cache = text.strip()
                    _briefing_fetched_at = now
                    print(f'[{ts()}] briefing refreshed ({len(_briefing_cache)} chars)')
    except Exception as e:
        print(f'[{ts()}] graph unreachable: {e}')

    return _briefing_cache


async def build_system_prompt() -> str:
    """Build system prompt, optionally including graph context."""
    briefing = await fetch_briefing()
    if briefing:
        return f'# Briefing\n{briefing}\n\n---\n\n{BASE_SYSTEM}'
    return BASE_SYSTEM


async def call_claude(sender: str, user_msg: str, ws) -> None:
    """Send message to Claude API and stream response back."""
    threads[sender].append({'role': 'user', 'content': user_msg})
    print(f'[{ts()}] -> API [{sender}]: {user_msg[:80]}')

    system = await build_system_prompt()
    full_response = []

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=threads[sender]
        ) as stream:
            for token in stream.text_stream:
                full_response.append(token)
                await ws.send(json.dumps({
                    'from': 'claude',
                    'to': sender,
                    'type': 'token',
                    'msg': token
                }))

        threads[sender].append({
            'role': 'assistant',
            'content': ''.join(full_response)
        })
        await ws.send(json.dumps({
            'from': 'claude',
            'to': sender,
            'type': 'done',
            'msg': ''.join(full_response)
        }))
        print(f'[{ts()}] <- done [{sender}]: {"".join(full_response)[:80]}...')

    except Exception as e:
        await ws.send(json.dumps({
            'from': 'claude',
            'to': sender,
            'type': 'error',
            'msg': str(e)
        }))
        print(f'[{ts()}] error: {e}')


async def run(relay_url: str):
    """Connect to relay and handle incoming messages."""
    print(f'connecting to {relay_url}')
    if GRAPH_URL:
        print(f'graph context from {GRAPH_URL} (TTL {BRIEFING_TTL}s)')
        await fetch_briefing()

    async for ws in websockets.connect(relay_url, ping_interval=20, ping_timeout=30):
        try:
            # Join as 'claude'
            await ws.send(json.dumps({'type': 'join', 'id': 'claude'}))
            resp = json.loads(await ws.recv())
            print(f'[{ts()}] joined — peers: {resp.get("peers", [])}')

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Handle relay events
                if msg.get('type') in ('peer_joined', 'peer_left', 'peers'):
                    print(f'[{ts()}] relay: {msg}')
                    continue

                # Handle incoming message
                sender = msg.get('from', 'unknown')
                content = msg.get('msg', '').strip()
                if content:
                    asyncio.create_task(call_claude(sender, content, ws))

        except websockets.exceptions.ConnectionClosed as e:
            print(f'[{ts()}] disconnected ({e}), reconnecting...')
            await asyncio.sleep(2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Claude proxy for agent relay')
    parser.add_argument(
        '--relay',
        default='ws://localhost:8815',
        help='WebSocket URL of the relay server'
    )
    args = parser.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise SystemExit('ANTHROPIC_API_KEY environment variable required')

    asyncio.run(run(args.relay))
