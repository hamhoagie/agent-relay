#!/usr/bin/env python3
"""
WebSocket relay server for agent-to-agent communication.

Peers connect, identify themselves with a 'join' message, and can then
send messages to specific peers or broadcast to all.

Usage:
    python relay.py --port 8815
"""
import asyncio
import json
import argparse
import websockets
from datetime import datetime

peers: dict[str, websockets.WebSocketServerProtocol] = {}


def ts():
    return datetime.now().strftime('%H:%M:%S')


async def handler(ws: websockets.WebSocketServerProtocol):
    peer_id = None
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send(json.dumps({'type': 'error', 'msg': 'invalid JSON'}))
                continue

            # Peer registration
            if msg.get('type') == 'join':
                peer_id = msg.get('id', 'unknown')
                peers[peer_id] = ws
                print(f'[{ts()}] + {peer_id} connected (peers: {list(peers)})')
                await ws.send(json.dumps({
                    'type': 'joined',
                    'id': peer_id,
                    'peers': list(peers)
                }))
                # Notify other peers
                for pid, pws in peers.items():
                    if pid != peer_id:
                        await pws.send(json.dumps({
                            'type': 'peer_joined',
                            'id': peer_id
                        }))
                continue

            # List peers
            if msg.get('type') == 'peers':
                await ws.send(json.dumps({'type': 'peers', 'peers': list(peers)}))
                continue

            # Route message
            sender = msg.get('from', peer_id or 'unknown')
            target = msg.get('to')
            payload = json.dumps(msg)

            if target:
                # Directed message
                if target in peers:
                    await peers[target].send(payload)
                    print(f'[{ts()}] {sender} -> {target}: {msg.get("msg", "")[:80]}')
                else:
                    await ws.send(json.dumps({
                        'type': 'error',
                        'msg': f"peer '{target}' not connected"
                    }))
            else:
                # Broadcast
                for pid, pws in peers.items():
                    if pid != sender:
                        await pws.send(payload)
                print(f'[{ts()}] {sender} -> * broadcast')

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if peer_id and peer_id in peers:
            del peers[peer_id]
            print(f'[{ts()}] - {peer_id} disconnected (peers: {list(peers)})')
            for pws in peers.values():
                await pws.send(json.dumps({'type': 'peer_left', 'id': peer_id}))


async def main(port: int):
    print(f'relay listening on ws://0.0.0.0:{port}')
    async with websockets.serve(handler, '0.0.0.0', port):
        await asyncio.Future()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='WebSocket relay for agent communication')
    parser.add_argument('--port', type=int, default=8815, help='Port to listen on')
    args = parser.parse_args()
    asyncio.run(main(args.port))
