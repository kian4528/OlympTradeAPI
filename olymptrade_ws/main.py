import asyncio
import logging
from getpass import getpass
import os

from olymptrade_ws.core.client import OlympTradeClient
from olymptrade_ws.olympconfig import parameters

logging.basicConfig(level=os.getenv("NIGHTSHIFT_LOG_LEVEL", parameters.LOG_LEVEL), format=parameters.LOG_FORMAT)
logger = logging.getLogger("nightshift.console")


async def run_client():
    token = os.getenv("OLYMPTRADE_ACCESS_TOKEN") or getpass("OlympTrade access token (input hidden): ").strip()
    if not token:
        raise SystemExit("An access token is required.")
    client = OlympTradeClient(access_token=token)
    try:
        await client.start()
        await client.initialize_session()
        balance = await client.balance.get_balance()
        if balance:
            accounts = balance.get("d", [])
            logger.info("Received a balance update containing %d account record(s).", len(accounts) if isinstance(accounts, list) else 0)
        else:
            logger.warning("No balance update was received before timeout.")
        logger.info("Connected in read-only mode. Press Ctrl+C to stop; no trades will be placed.")
        await asyncio.Event().wait()
    finally:
        await client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_client())
    except KeyboardInterrupt:
        pass
