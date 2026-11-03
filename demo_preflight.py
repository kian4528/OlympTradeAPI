import asyncio
import logging
import os
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient

logging.disable(logging.CRITICAL)

EVENTS = (21, 22, 26, 55, 110)
received = set()


async def inspect(event, message):
    received.add(event)
    data = message.get("d")
    records = [data] if isinstance(data, dict) else (
        [item for item in data if isinstance(item, dict)]
        if isinstance(data, list) else []
    )

    print(f"Event {event}: received")

    if event == 110 and records:
        print("  Event 110 fields:", {
            key: type(value).__name__
            for key, value in records[0].items()
        })

    if event == 55:
        for record in records:
            group = record.get("group")
            account_id = record.get("account_id")
            if group in ("demo", "real") and isinstance(account_id, int):
                print(f"  Account group: {group}")
                print(f"  Account ID: {account_id}")


async def main():
    token = os.environ.get("OLYMPTRADE_ACCESS_TOKEN")
    if not token:
        token = getpass("Access token: ").strip()
    if not token:
        raise SystemExit("An access token is required.")

    client = OlympTradeClient(access_token=token)
    started = False

    try:
        await client.start()
        started = True

        for event in EVENTS:
            async def callback(message, code=event):
                await inspect(code, message)
            client.register_callback(event, callback)

        await client.initialize_session()

        print("\nAccount selection:")
        print("Group:", client.account_group or "unverified")
        print("Account ID:", client.account_id or "unverified")

        await client.balance.subscribe_balance_updates()
        await asyncio.sleep(8)

        print("\nSummary:")
        print("Observed events:", ", ".join(map(str, sorted(received))) or "none")
        print("Selected group:", client.account_group or "unverified")
        print("Selected account:", client.account_id or "unverified")
        print("Order submission: DISABLED")

    finally:
        if started:
            await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
