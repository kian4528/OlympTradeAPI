import logging
from typing import TYPE_CHECKING, Dict, Any, Optional

if TYPE_CHECKING:
    from olymptrade_ws.core.client import OlympTradeClient

logger = logging.getLogger(__name__)


class BalanceAPI:
    def __init__(self, client: "OlympTradeClient"):
        self._client = client
        self._subscribed = False

    async def subscribe_balance_updates(self) -> None:
        """Subscribe once to unsolicited balance updates (event 55)."""
        if self._subscribed:
            logger.debug("Balance subscription is already active.")
            return

        await self._client.send_request(
            98,
            [55],
            requires_response=False,
        )
        self._subscribed = True
        logger.info("Balance update subscription request sent.")

    def get_last_balance(self) -> Dict[str, Any]:
        """Return the latest balance update received from the server."""
        balance_data = self._client.current_balance
        if not balance_data:
            logger.debug("No balance update has been received yet.")
        return balance_data

    async def request_balance(
        self,
        account_id: int,
        group: str = "real",
    ) -> Optional[Dict[str, Any]]:
        """Explicit balance requests are not implemented until verified."""
        raise NotImplementedError(
            "Explicit balance requests are not verified. "
            "Use the event 55 balance update subscription instead."
        )

    async def get_balance(
        self,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        """Initialize the session if needed and wait for a balance update."""
        if not getattr(self._client, "_session_initialized", False):
            await self._client.initialize_session()

        return await self._client.wait_for_balance(
            timeout=timeout,
            poll_interval=poll_interval,
        )
