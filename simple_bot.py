import asyncio
import logging
import os
from decimal import Decimal, InvalidOperation
from getpass import getpass

from olymptrade_ws import OlympTradeClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("nightshift")

PAIR = os.getenv("NIGHTSHIFT_PAIR", "LATAM_X")
CANDLE_SECONDS = int(os.getenv("NIGHTSHIFT_CANDLE_SECONDS", "60"))
CANDLE_COUNT = int(os.getenv("NIGHTSHIFT_CANDLE_COUNT", "10"))


def format_amount(value):
    """Format a numeric balance field without assuming a currency."""
    if value is None:
        return "Not provided"
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            return "Unavailable"
        return f"{amount:,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return "Unavailable"


def display_demo_balance(account):
    """Display selected demo balance fields without exposing account IDs."""
    print("\n" + "=" * 42)
    print("       NIGHTSHIFT • DEMO ACCOUNT")
    print("=" * 42)
    print(f"{'Total amount':<24} {format_amount(account.get('amount'))}")
    print(f"{'Available amount':<24} {format_amount(account.get('amount_free'))}")
    print(f"{'Real funds component':<24} {format_amount(account.get('amount_real'))}")
    print(f"{'Bonus amount':<24} {format_amount(account.get('amount_bonus'))}")
    print(f"{'Free bonus amount':<24} {format_amount(account.get('amount_bonus_free'))}")

    holds = account.get("holds")
    if isinstance(holds, dict):
        print("\nFunds on hold:")
        if not holds:
            print("  None reported")
        else:
            for key, value in holds.items():
                # Only show hold names and numeric amounts, never arbitrary objects.
                print(f"  {str(key):<22} {format_amount(value)}")
    elif holds is not None:
        print(f"\nFunds on hold: {format_amount(holds)}")
    else:
        print("\nFunds on hold: Not provided")

    print("=" * 42)
    print("READ-ONLY MODE • No orders are placed\n")


async def main():
    token = (
        os.getenv("OLYMPTRADE_ACCESS_TOKEN")
        or getpass("OlympTrade access token (input hidden): ").strip()
    )
    if not token:
        raise SystemExit("No access token supplied.")

    client = OlympTradeClient(access_token=token)

    try:
        await client.start()
        await client.initialize_session()

        balance = await client.balance.get_balance(timeout=12)
        if not isinstance(balance, dict):
            logger.warning("No balance update arrived.")
            return

        accounts = balance.get("d", [])
        if not isinstance(accounts, list):
            logger.warning("Balance response did not contain an account list.")
            return

        demo_accounts = [
            item for item in accounts
            if isinstance(item, dict) and item.get("group") == "demo"
        ]

        if not demo_accounts:
            logger.warning("No demo account was found. No orders will be placed.")
            return

        if len(demo_accounts) > 1:
            logger.warning(
                "Multiple demo accounts found; displaying the first only."
            )

        demo = demo_accounts[0]
        display_demo_balance(demo)

        candles = await client.market.get_candles(
            PAIR,
            size=CANDLE_SECONDS,
            count=CANDLE_COUNT,
        )
        if not candles:
            logger.warning("No candle data received for %s.", PAIR)
            return

        latest = candles[-1]
        open_price = latest.get("open")
        close_price = latest.get("close")

        if open_price is None or close_price is None:
            logger.warning("Latest candle does not contain open and close values.")
            return

        direction = (
            "up" if close_price > open_price
            else "down" if close_price < open_price
            else "flat"
        )

        logger.info(
            "Pair: %s | open: %s | close: %s | candle bias: %s",
            PAIR,
            open_price,
            close_price,
            direction,
        )
        logger.info("Read-only mode: no orders are placed.")

    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
