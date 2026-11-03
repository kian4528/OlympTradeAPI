import asyncio
import os
from decimal import Decimal, InvalidOperation
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient

STAKE = Decimal("1.00")
EXPIRY_SECONDS = 10
ACCOUNT_GROUP = "demo"


def get_demo_account(balance):
    if not isinstance(balance, dict):
        raise RuntimeError("Invalid balance response.")

    records = balance.get("d")
    if isinstance(records, dict):
        records = [records]

    if not isinstance(records, list):
        raise RuntimeError("No account records received.")

    accounts = [
        item for item in records
        if isinstance(item, dict) and item.get("group") == ACCOUNT_GROUP
    ]

    if len(accounts) != 1:
        raise RuntimeError("Exactly one demo account is required.")

    account = accounts[0]

    try:
        account_id = account["account_id"]
        available = Decimal(str(account["amount_free"]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise RuntimeError("Demo account details could not be verified.")

    if isinstance(account_id, bool) or not isinstance(account_id, int) or account_id <= 0:
        raise RuntimeError("Invalid demo account ID.")

    if not available.is_finite() or available < STAKE:
        raise RuntimeError("Insufficient demo funds.")

    return account, available


async def run():
    token = os.getenv("OLYMPTRADE_ACCESS_TOKEN")
    if not token:
        token = getpass("Access token: ").strip()

    if not token:
        raise RuntimeError("An access token is required.")

    client = OlympTradeClient(access_token=token)
    started = False

    try:
        await client.start()
        started = True

        balance = await client.balance.get_balance(timeout=15)
        account, available = get_demo_account(balance)

        pair = input("Instrument: ").strip()
        if not pair:
            raise RuntimeError("An instrument is required.")

        direction = input("Direction (up/down): ").strip().lower()
        if direction not in ("up", "down"):
            raise RuntimeError("Invalid direction.")

        print()
        print("NIGHTSHIFT | DEMO PREFLIGHT")
        print("===========================")
        print("Account group: DEMO")
        print(f"Available funds: ${available:,.2f}")
        print(f"Instrument: {pair}")
        print(f"Direction: {direction.upper()}")
        print(f"Proposed stake: ${STAKE:.2f}")
        print(f"Proposed expiry: {EXPIRY_SECONDS} seconds")
        print()
        print("Account selection: NOT VERIFIED")
        print("Order placement: DISABLED")
        print("No order has been submitted.")

    except Exception as exc:
        print(f"Preflight failed: {type(exc).__name__}")
    finally:
        if started:
            await client.stop()


if __name__ == "__main__":
    asyncio.run(run())
