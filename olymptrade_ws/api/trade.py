from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Dict, Literal, Optional, Union

from olymptrade_ws.core.protocol import get_current_timestamp_ms

if TYPE_CHECKING:
    from olymptrade_ws.core.client import OlympTradeClient


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
            raise RuntimeError(
                "Order account does not match the configured demo account."
            )
        if (
            not isinstance(pair, str)
            or not pair.strip()
            or pair != pair.strip()
            or len(pair) > 64
            or not pair.isascii()
            or any(not (character.isalnum() or character in "_.-") for character in pair)
        ):
            raise ValueError("Invalid instrument.")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("Invalid stake.")
        try:
            stake = Decimal(str(amount))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("Invalid stake.") from None
        if not stake.is_finite() or stake <= 0:
            raise ValueError("Invalid stake.")
        if direction not in ("up", "down"):
            raise ValueError("Invalid direction.")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
        ):
            raise ValueError("Invalid expiry.")
        if (
            not isinstance(account_id, int)
            or isinstance(account_id, bool)
            or account_id <= 0
        ):
            raise ValueError("Invalid account ID.")
        if (
            not isinstance(category, str)
            or not category.strip()
            or category != category.strip()
            or len(category) > 32
            or not category.isascii()
            or any(not (character.isalnum() or character in "_-.") for character in category)
        ):
            raise ValueError("Invalid category.")
        if (
            not isinstance(pos, int)
            or isinstance(pos, bool)
            or pos < 0
        ):
            raise ValueError("Invalid position.")
        if (
            not isinstance(source, str)
            or not source.strip()
            or source != source.strip()
            or len(source) > 64
            or not source.isascii()
            or any(not (character.isalnum() or character in "_-.") for character in source)
        ):
            raise ValueError("Invalid order source.")
        if timestamp is None:
            timestamp = get_current_timestamp_ms()
        elif (
            not isinstance(timestamp, int)
            or isinstance(timestamp, bool)
            or timestamp <= 0
        ):
            raise ValueError("Invalid order timestamp.")
        if risk_free_id is not None and (
            not isinstance(risk_free_id, int)
            or isinstance(risk_free_id, bool)
            or risk_free_id < 0
        ):
            raise ValueError("Invalid risk-free ID.")
        if not isinstance(is_flex, bool):
            raise ValueError("is_flex must be a boolean.")

        demo_account = self._client.balance.get_demo_account()
        balance_account_id = (
            demo_account.get("account_id") if isinstance(demo_account, dict) else None
        )
        if (
            not isinstance(balance_account_id, int)
            or isinstance(balance_account_id, bool)
            or balance_account_id != account_id
        ):
            raise RuntimeError("A verified demo balance is required before ordering.")
        try:
            available = Decimal(str(demo_account["amount_free"]))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            raise RuntimeError("The available demo balance could not be verified.") from None
        if not available.is_finite() or available < stake:
            raise ValueError("Stake exceeds the available demo balance.")

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

        if not isinstance(response, dict):
            raise RuntimeError(
                "Unexpected event-23 response type: "
                f"{type(response).__name__}"
            )

        event_code = response.get("e")
        details = response.get("d")

        if event_code != 23:
            raise RuntimeError(
                f"Unexpected response event code: {event_code!r}"
            )

        if not isinstance(details, list) or not details:
            detail_type = type(details).__name__
            detail_keys = (
                sorted(str(key) for key in details.keys())
                if isinstance(details, dict)
                else []
            )
            raise RuntimeError(
                f"Event-23 response has unexpected data: "
                f"type={detail_type}, keys={detail_keys}"
            )

        first = details[0]
        if not isinstance(first, dict):
            raise RuntimeError(
                "Event-23 order detail is not a dictionary: "
                f"{type(first).__name__}"
            )

        return first

    place_trade = place_order

    async def get_open_trades(
        self, account_id: int, group: str = "demo"
    ) -> Optional[list[Dict[str, Any]]]:
        return None
