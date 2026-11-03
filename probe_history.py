import asyncio
import json
import os
import time
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient

PAIR = "EURUSD_OTC"
TIMEFRAME_SECONDS = 300
HISTORY_LIMIT = 600
WAIT_SECONDS = 12

SAFE_FIELDS = {
    "t", "time", "timestamp",
    "open", "high", "low", "close",
    "o", "h", "l", "c",
    "volume", "v", "tf",
}


def safe_sample(item):
    if not isinstance(item, dict):
        return {"record_type": type(item).__name__}

    return {
        key: value
        for key, value in item.items()
        if key in SAFE_FIELDS
        and isinstance(value, (int, float, str, bool, type(None)))
    }


def inspect_candles(data):
    if not isinstance(data, list):
        print("Unexpected response data type:", type(data).__name__)
        return

    print("Response items:", len(data))

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"Response item {index}: {type(item).__name__}")
            continue

        print(f"\nResponse item {index}")
        print("Fields:", sorted(item.keys()))
        print("Pair:", item.get("p"))
        print("Timeframe:", item.get("tf"))

        candles = item.get("candles")
        print("Candles type:", type(candles).__name__)

        if isinstance(candles, list):
            print("Candle count:", len(candles))

            if candles:
                first = candles[0]
                last = candles[-1]

                print("First candle fields:",
                      sorted(first.keys()) if isinstance(first, dict)
                      else type(first).__name__)
                print("First candle:", json.dumps(safe_sample(first)))
                print("Last candle:", json.dumps(safe_sample(last)))

        elif isinstance(candles, dict):
            print("Candle collection keys:", sorted(candles.keys()))

            for key, value in list(candles.items())[:3]:
                print(
                    f"Collection entry {key}:",
                    json.dumps(safe_sample(value))
                )


async def main():
    token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
    if not token:
        token = getpass("OlympTrade access token (input hidden): ").strip()

    if not token:
        print("No token supplied.")
        return

    client = OlympTradeClient(access_token=token)
    received = []
    event_received = asyncio.Event()

    async def callback(message):
        if message.get("e") != 10:
            return

        received.append(message)
        print("\nHistorical response received.")
        inspect_candles(message.get("d"))
        event_received.set()

    client.register_callback(10, callback)

    started = False
    try:
        print("Connecting for read-only candle inspection...")
        await client.start()
        started = True
        await client.initialize_session()

        request = [{
            "pair": PAIR,
            "size": TIMEFRAME_SECONDS,
            "to": int(time.time()),
            "limit": HISTORY_LIMIT,
        }]

        print(
            f"Requesting {HISTORY_LIMIT} candles for "
            f"{PAIR}, timeframe {TIMEFRAME_SECONDS}s."
        )

        await client.send_request(
            10,
            request,
            requires_response=False,
        )

        try:
            await asyncio.wait_for(
                event_received.wait(),
                timeout=WAIT_SECONDS,
            )
        except asyncio.TimeoutError:
            print("No historical response received before timeout.")

        print("\nDiagnostic summary")
        print("Historical responses:", len(received))
        print("No trades were submitted.")

    finally:
        client.unregister_callback(10, callback)
        if started:
            await client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped. No trades were submitted.")
