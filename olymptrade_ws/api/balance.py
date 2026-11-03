import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from olymptrade_ws.core.client import OlympTradeClient

logger = logging.getLogger(__name__)


class BalanceAPI:
    def __init__(self, client: "OlympTradeClient"):
        self._client = client
        self._subscribed = False

    async def subscribe_balance_updates(self) -> None:
        if self._subscribed:
            return
        await self._client.send_request(98, [55], requires_response=False)
        self._subscribed = True

    def get_last_balance(self) -> Dict[str, Any]:
        return self._client._latest_balance or {}

    def get_account_records(self) -> list[Dict[str, Any]]:
        message = self.get_last_balance()
        data = message.get("d", []) if isinstance(message, dict) else []
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        return [
            item for item in data
            if isinstance(item, dict)
            and isinstance(item.get("account_id"), int)
            and item.get("group") in ("demo", "real")
        ]

    def get_demo_account(self) -> Optional[Dict[str, Any]]:
        accounts = [
            item for item in self.get_account_records()
            if item.get("group") == "demo"
        ]
        if len(accounts) != 1:
            return None
        return accounts[0]

    async def request_balance(
        self, account_id: int, group: str = "demo"
    ) -> Optional[Dict[str, Any]]:
        return None

    async def get_balance(
        self,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> Optional[Dict[str, Any]]:
        if not getattr(self._client, "_session_initialized", False):
            await self._client.initialize_session()
        return await self._client.wait_for_balance(
            timeout=timeout,
            poll_interval=poll_interval,
        )
