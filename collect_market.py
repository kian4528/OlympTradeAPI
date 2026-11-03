import asyncio
import csv
import getpass
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logging.disable(logging.CRITICAL)

from olymptrade_ws.core.client import OlympTradeClient

EVENTS = (1054, 1076, 1301, 1097, 2301)
OUTPUT = Path("data")
WAIT_SECONDS = 6

async def main():
    token = getpass.getpass("Access token (hidden): ").strip()
    if not token:
        print("No token supplied.")
        return

    captured = {event: [] for event in EVENTS}
    callbacks = {}
    client = OlympTradeClient(access_token=token)

    for event in EVENTS:
        async def callback(message, event=event):
            captured[event].append(message.get("d"))
        callbacks[event] = callback
        client.register_callback(event, callback)

    try:
        print("Connecting once...")
        await client.start()
        await client.initialize_session()
        await asyncio.sleep(WAIT_SECONDS)

        inventory = {
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "events": {
                str(event): captured[event]
                for event in EVENTS
            },
        }

        json_path = OUTPUT / "market_inventory.json"
        json_path.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        instruments = []
        for message in captured[1054]:
            if isinstance(message, list):
                instruments.extend(
                    item for item in message if isinstance(item, dict)
                )

        csv_path = OUTPUT / "instruments.csv"
        columns = [
            "id", "title", "group", "aliases", "precision",
            "locked", "locked_trading", "locked_buy",
            "locked_sell", "time_open", "time_close",
        ]

        with csv_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            for item in instruments:
                row = {
                    key: item.get(key, "")
                    for key in columns
                }
                row["aliases"] = json.dumps(
                    row["aliases"], ensure_ascii=False
                ) if row["aliases"] else ""
                writer.writerow(row)

        print("\nCollection complete.")
        print("Instrument records:", len(instruments))
        for event in EVENTS:
            print(f"Event {event}: {len(captured[event])} message(s)")

        print("\nBNB / OTC matches:")
        matches = []
        for item in instruments:
            searchable = " ".join(
                str(item.get(key, ""))
                for key in ("title", "group", "aliases", "id")
            ).lower()
            if "bnb" in searchable or "otc" in searchable:
                matches.append(item)

        if matches:
            for item in matches:
                print({
                    key: item.get(key)
                    for key in ("id", "title", "group", "aliases")
                    if key in item
                })
        else:
            print("No explicit BNB or OTC labels in the instrument catalogue.")

        print("\nCurrency instruments:")
        for item in instruments:
            if item.get("group") == "currency":
                print(
                    item.get("id"),
                    item.get("title"),
                    "aliases=",
                    item.get("aliases"),
                )

        print("\nSaved:")
        print(json_path)
        print(csv_path)

    except Exception as exc:
        print("Collection failed:", type(exc).__name__)
    finally:
        for event, callback in callbacks.items():
            try:
                client.unregister_callback(event, callback)
            except Exception:
                pass
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
