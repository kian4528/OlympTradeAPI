import logging
import math
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Union

from olymptrade_ws.core.protocol import get_current_timestamp_ms

if TYPE_CHECKING:
    from olymptrade_ws.core.client import OlympTradeClient

logger = logging.getLogger(__name__)


class TradeAPI:
    def __init__(self, client: "OlympTradeClient"):
        self._client = client

    async def place_order(
        self,
        pair: str,
        amount: Union[int, float],
        direction: Literal["up", "down"],
        duration: int,
        account_id: int,
        group: Literal["real", "demo"] = "demo",
        category: str = "digital",
        pos: int = 0,
        source: str = "platform",
        timestamp: Optional[int] = None,
        risk_free_id: Optional[int] = None,
        is_flex: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if group != "demo":
            raise ValueError("Only demo-account orders are permitted.")
        if getattr(self._client, "account_group", None) != "demo":
            raise RuntimeError("Verified demo account context is required.")
        if getattr(self._client, "account_id", None) != account_id:
            raise RuntimeError("Order account does not match the configured demo account.")
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError("Invalid instrument.")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("Invalid stake.")
        if not math.isfinite(float(amount)) or amount <= 0:
            raise ValueError("Invalid stake.")
        if direction not in ("up", "down"):
            raise ValueError("Invalid direction.")
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise ValueError("Invalid expiry.")
        if not isinstance(account_id, int) or isinstance(account_id, bool) or account_id <= 0:
            raise ValueError("Invalid account ID.")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("Invalid category.")

        if timestamp is None:
            timestamp = get_current_timestamp_ms()

        payload = [{
            "amount": amount,
            "dir": direction,
            "pair": pair,
            "cat": category,
            "pos": pos,
            "source": source,
            "account_id": account_id,
            "group": "demo",
            "timestamp": timestamp,
            "risk_free_id": risk_free_id,
            "is_flex": is_flex,
            "duration": duration,
        }]

        response = await self._client.send_request(
            23,
            payload,
            requires_response=True,
            timeout=5.0,
        )

        if not isinstance(response, dict) or response.get("e") != 23:
            return None

        details = response.get("d")
        if not isinstance(details, list) or not details:
            return None

        first = details[0]
        if not isinstance(first, dict):
            return None

        return first

    place_trade = place_order

    async def get_open_trades(
        self, account_id: int, group: str = "demo"
    ) -> Optional[list[Dict[str, Any]]]:
        return None
