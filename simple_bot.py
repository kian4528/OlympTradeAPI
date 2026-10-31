import asyncio
import logging
import os
from getpass import getpass

from olymptrade_ws import OlympTradeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("nightshift")
PAIR = os.getenv("NIGHTSHIFT_PAIR", "LATAM_X")
CANDLE_SECONDS = int(os.getenv("NIGHTSHIFT_CANDLE_SECONDS", "60"))
CANDLE_COUNT = int(os.getenv("NIGHTSHIFT_CANDLE_COUNT", "10"))


async def main():
    token = os.getenv("OLYMPTRADE_ACCESS_TOKEN") or getpass("OlympTrade access token (input hidden): ").strip()
    if not token:
        raise SystemExit("No access token supplied.")
    client = OlympTradeClient(access_token=token)
    try:
        await client.start()
        await client.initialize_session()
        balance = await client.balance.get_balance()
        if not balance:
            logger.warning("No balance update arrived. Check the session and API compatibility.")
        else:
            accounts = balance.get("d", [])
            demo = next((item for item in accounts if isinstance(item, dict) and item.get("group") == "demo"), None)
            if demo:
                logger.info("Demo account balance received. Account id is available in local session state.")
            else:
                logger.info("Balance received; no demo account was found in this response.")
        candles = await client.market.get_candles(PAIR, size=CANDLE_SECONDS, count=CANDLE_COUNT)
        if not candles:
            logger.warning("No candle data received for %s.", PAIR)
            return
        latest = candles[-1]
        open_price = latest.get("open")
        close_price = latest.get("close")
        if open_price is None or close_price is None:
            logger.warning("Latest candle does not contain open and close values.")
            return
        direction = "up" if close_price > open_price else "down" if close_price < open_price else "flat"
        logger.info("Pair: %s | open: %s | close: %s | candle bias: %s", PAIR, open_price, close_price, direction)
        logger.info("Read-only mode: no orders are placed by this script.")
    finally:
        await client.stop()


if __name__ == "__main__":
    asyncio.run(main())
