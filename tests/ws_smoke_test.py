"""Quick WebSocket smoke test for the AEGIS live hub."""
import asyncio
import json
import sys

import websockets


async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws") as ws:
        # First message should be the welcome/status payload
        msg = await asyncio.wait_for(ws.recv(), timeout=15)
        d = json.loads(msg)
        print("WS CONNECTED — first message:")
        print("  type:", d.get("type"))
        keys = sorted(d.keys())
        print("  keys:", keys)
        # Receive up to 3 more messages (ticker/heartbeat stream)
        for _ in range(3):
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                d = json.loads(msg)
                print("  streamed:", d.get("type"), "-", str(d)[:120])
            except asyncio.TimeoutError:
                print("  (no further messages within 10s — idle hub, expected)")
                break
        print("WEBSOCKET SMOKE TEST OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"WS TEST FAILED: {e}")
        sys.exit(1)
