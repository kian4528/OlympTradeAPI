import asyncio
import os
from decimal import Decimal, InvalidOperation
from getpass import getpass

from olymptrade_ws.core.client import OlympTradeClient


def format_amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            return None
        return f"{number:,.2f}" if number % 1 else f"{number:,.0f}"
    except (InvalidOperation, ValueError, TypeError):
        return None


def display_dashboard(balance):
    accounts = balance.get("d", []) if isinstance(balance, dict) else []
    if isinstance(accounts, dict):
        accounts = [accounts]
    if not isinstance(accounts, list):
        accounts = []

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║              N I G H T S H I F T                 ║")
    print("║                ACCOUNT OVERVIEW                  ║")
    print("╚══════════════════════════════════════════════════╝")
    print("  ● CONNECTED                         READ-ONLY")
    print("  " + "─" * 48)

    shown = 0
    for index, account in enumerate(accounts, 1):
        if not isinstance(account, dict):
            continue

        shown += 1
        group = account.get("group")
        label = str(group).upper() if group else f"ACCOUNT {index}"

        print(f"\n  {index:02d}  {label}")
        print("  " + "─" * 48)

        fields = (
            ("BALANCE", "amount"),
            ("REAL BALANCE", "amount_real"),
            ("AVAILABLE", "amount_free"),
            ("BONUS", "amount_bonus"),
            ("BONUS AVAILABLE", "amount_bonus_free"),
        )

        for title, key in fields:
            value = format_amount(account.get(key))
            if value is not None:
                print(f"      {title:<20} {value}")

        holds = account.get("holds")
        if isinstance(holds, dict):
            payout = format_amount(holds.get("payout"))
            if payout is not None:
                print(f"      {'PAYOUT ON HOLD':<20} {payout}")

    if not shown:
        print("\n  No account records received.")

    print("\n  " + "─" * 48)
    print("  Account IDs hidden  •  No trades are placed")
    print("  Press Ctrl+C to disconnect.\n")


async def run_client():
    token = os.getenv("OLYMPTRADE_ACCESS_TOKEN")
    if not token:
        token = getpass("OlympTrade access token (input hidden): ").strip()
    if not token:
        raise SystemExit("An access token is required.")

    client = OlympTradeClient(access_token=token)
    started = False

    try:
        print("\n  NIGHTSHIFT • Starting secure read-only session...")
        await client.start()
        started = True
        await client.initialize_session()

        balance = await client.balance.get_balance()
        if not balance:
            print("\n  No balance update received. Check your session.")
            return

        display_dashboard(balance)
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"\n  Session error: {type(exc).__name__}")
    finally:
        if started:
            await client.stop()
        print("\n  NIGHTSHIFT disconnected. Goodbye.\n")


if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        print("\n  NIGHTSHIFT closed.\n")
