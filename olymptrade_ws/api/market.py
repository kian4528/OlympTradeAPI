import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from olymptrade_ws.olympconfig import parameters

if TYPE_CHECKING:
    from olymptrade_ws.core.client import OlympTradeClient

logger = logging.getLogger(__name__)


class MarketAPI:
    def __init__(self, client: "OlympTradeClient"):
        self._client = client

    async def subscribe_ticks(self, pair: str) -> None:
        """Subscribe to the observed tick streams for an instrument."""
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError("pair must be a non-empty string")

        await self._client.send_request(
            parameters.E_SUBSCRIBE_TICKS,
            [{"pair": pair}],
            requires_response=True,
        )
        await self._client.send_request(
            parameters.E_SUBSCRIBE_TICKS_RELATED,
            [{"pair": pair}],
            requires_response=True,
        )

    async def unsubscribe_ticks(self, pair: str) -> None:
        """Unsubscribe from the observed tick streams for an instrument."""
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError("pair must be a non-empty string")

        await self._client.send_request(
            parameters.E_UNSUBSCRIBE_TICKS,
            [{"pair": pair}],
            requires_response=True,
        )
        await self._client.send_request(
            parameters.E_UNSUBSCRIBE_TICKS_RELATED,
            [{"pair": pair}],
            requires_response=True,
        )

    @staticmethod
    def _normalize_end_time(
        end_time: Optional[Union[datetime, int]]
    ) -> int:
        if end_time is None:
            return int(time.time())

        if isinstance(end_time, bool):
            raise ValueError("end_time must be a datetime or Unix timestamp")

        if isinstance(end_time, datetime):
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            return int(end_time.timestamp())

        if isinstance(end_time, int):
            return end_time

        raise ValueError("end_time must be a datetime or Unix timestamp")

    @staticmethod
    def _parse_candles(
        response: Dict[str, Any],
        expected_pair: str,
        expected_size: int,
    ) -> List[Dict[str, Any]]:
        data = response.get("d")

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            raise ValueError("Historical response has no candle data list")

        matching = [
            item for item in data
            if isinstance(item, dict)
            and item.get("p") == expected_pair
            and item.get("tf") == expected_size
        ]

        if not matching:
            raise ValueError(
                "Historical response did not contain the requested "
                "pair and timeframe"
            )

        raw_candles = matching[0].get("candles")
        if not isinstance(raw_candles, list):
            raise ValueError("Historical response candles field is invalid")

        parsed = []
        seen_timestamps = set()

        for item in raw_candles:
            if not isinstance(item, dict):
                continue

            try:
                timestamp_value = item["t"]
                timestamp = int(timestamp_value)
                open_price = float(item["open"])
                high_price = float(item["high"])
                low_price = float(item["low"])
                close_price = float(item["close"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue

            values = (
                open_price,
                high_price,
                low_price,
                close_price,
            )

            if not all(math.isfinite(value) for value in values):
                continue

            if timestamp <= 0 or timestamp in seen_timestamps:
                continue

            if low_price <= 0 or min(values) <= 0:
                continue

            if high_price < max(open_price, close_price, low_price):
                continue

            if low_price > min(open_price, close_price, high_price):
                continue

            seen_timestamps.add(timestamp)
            parsed.append({
                "t": timestamp,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            })

        parsed.sort(key=lambda candle: candle["t"])
        return parsed

    async def get_candles(
        self,
        pair: str,
        size: int,
        count: int,
        end_time: Optional[Union[datetime, int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve historical candles using the observed event-10 protocol.

        The server response is an event-10 message whose data contains:
        [{"p": pair, "tf": timeframe, "candles": [...]}].

        Returned candles are validated, deduplicated, and sorted oldest-first.
        """
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError("pair must be a non-empty string")

        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
        ):
            raise ValueError("size must be a positive integer")

        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= 10000
        ):
            raise ValueError("count must be between 1 and 10000")

        end_timestamp = self._normalize_end_time(end_time)
        loop = asyncio.get_running_loop()
        response_future = loop.create_future()

        def history_callback(message: Dict[str, Any]) -> None:
            if message.get("e") != parameters.E_GET_CANDLES_REQUEST:
                return

            try:
                candles = self._parse_candles(message, pair, size)
            except ValueError as exc:
                if not response_future.done():
                    response_future.set_exception(exc)
                return

            if not response_future.done():
                response_future.set_result(candles)

        event_code = parameters.E_GET_CANDLES_REQUEST
        self._client.register_callback(event_code, history_callback)

        request = [{
            "pair": pair,
            "size": size,
            "to": end_timestamp,
            "limit": count,
        }]

        try:
            # The observed server response is an event-10 message without
            # a demonstrated UUID correlation. Receive it via callback.
            await self._client.send_request(
                event_code,
                request,
                requires_response=False,
            )

            timeout = parameters.DEFAULT_RESPONSE_TIMEOUT
            candles = await asyncio.wait_for(
                response_future,
                timeout=timeout,
            )

            if not candles:
                logger.warning(
                    "No valid historical candles returned for %s (%ss).",
                    pair,
                    size,
                )
                return []

            logger.info(
                "Loaded %d historical candles for %s (%ss).",
                len(candles),
                pair,
                size,
            )
            return candles

        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for historical candles for %s.",
                pair,
            )
            raise

        finally:
            self._client.unregister_callback(
                event_code,
                history_callback,
            )
            if not response_future.done():
                response_future.cancel()

    async def get_profitability(
        self, account_id: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Disabled until the event-182 request/response mapping is verified."""
        logger.warning(
            "Profitability lookup is disabled: event 182 is not verified."
        )
        return None

    async def select_asset(
        self, pair: str, category: str = "digital"
    ) -> Optional[Dict[str, Any]]:
        """Select an asset and wait for its event-80 strike information."""
        if not isinstance(pair, str) or not pair.strip():
            raise ValueError("pair must be a non-empty string")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category must be a non-empty string")

        strike_event = parameters.E_ASSET_STRIKES
        select_event = parameters.E_SELECT_ASSET
        loop = asyncio.get_running_loop()
        strike_future = loop.create_future()

        def strike_callback(message: Dict[str, Any]) -> None:
            data = message.get("d", [])
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                return

            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("p") == pair and not strike_future.done():
                    strike_future.set_result(item)
                    return

        self._client.register_callback(strike_event, strike_callback)
        try:
            await self._client.send_request(
                select_event,
                [{"cat": category, "pair": pair}],
                requires_response=True,
            )
            return await asyncio.wait_for(
                strike_future,
                timeout=parameters.DEFAULT_RESPONSE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for strike information for %s.", pair
            )
            return None
        except Exception as exc:
            logger.warning(
                "Asset selection failed (%s).", type(exc).__name__
            )
            return None
        finally:
            self._client.unregister_callback(
                strike_event, strike_callback
            )
            if not strike_future.done():
                strike_future.cancel()
