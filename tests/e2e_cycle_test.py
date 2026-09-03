"""E2E: trigger a live orchestrator cycle via the web API while listening on /ws."""
import asyncio
import json

import requests
import websockets

WS_URL = "ws://127.0.0.1:8000/ws"
API_URL = "http://127.0.0.1:8000/api/run-cycle"

received = []


async def listen_and_trigger():
    async with websockets.connect(WS_URL) as ws:
        # Consume welcome frame
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        print(f"[ws] connected: {first.get('type')}", flush=True)

        # Fire the cycle (in a thread so we keep listening)
        loop = asyncio.get_running_loop()
        api_task = loop.run_in_executor(None, _trigger_cycle)

        # Listen for streamed cycle events
        try:
            deadline = asyncio.get_event_loop().time() + 560  # cycles can take a while
            while asyncio.get_event_loop().time() < deadline:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    d = json.loads(msg)
                    received.append(d)
                    agent = (d.get("agent") or "SYSTEM").upper()
                    print(f"[ws] {agent}: {str(d.get('message'))[:100]}", flush=True)
                    if len(received) > 80:
                        break
                except asyncio.TimeoutError:
                    if api_task.done():
                        break
                    continue
        finally:
            result = api_task.result()
            print("\n[api] run-cycle response:", flush=True)
            print(json.dumps(result, indent=2, default=str)[:1500], flush=True)

    print(f"\nRESULT: ws_events={len(received)}", flush=True)


def _trigger_cycle():
    try:
        r = requests.post(API_URL, timeout=570)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    asyncio.run(listen_and_trigger())
