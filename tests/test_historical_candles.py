import asyncio
import pytest

from olymptrade_ws.api.market import MarketAPI


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.callbacks = {}
        self.sent = []

    def register_callback(self, event, callback):
        self.callbacks.setdefault(event, []).append(callback)

    def unregister_callback(self, event, callback):
        self.callbacks[event].remove(callback)

    async def send_request(self, event, data, requires_response=True):
        self.sent.append((event, data, requires_response))
        for callback in tuple(self.callbacks.get(event, [])):
            await callback(self.response)


def candle(timestamp, opening, high, low, close):
    return {
        "t": timestamp,
        "open": opening,
        "high": high,
        "low": low,
        "close": close,
    }


def test_get_candles_sorts_oldest_first_and_uses_observed_request():
    async def run():
        response = {
            "e": 10,
            "d": [{
                "p": "EURUSD_OTC",
                "tf": 300,
                "candles": [
                    candle(300, 1.2, 1.3, 1.1, 1.25),
                    candle(100, 1.0, 1.1, 0.9, 1.05),
                    candle(200, 1.1, 1.2, 1.0, 1.15),
                ],
            }],
        }
        client = FakeClient(response)
        api = MarketAPI(client)

        result = await api.get_candles(
            "EURUSD_OTC", size=300, count=600, end_time=999
        )

        assert [item["t"] for item in result] == [100, 200, 300]
        assert client.sent == [
            (
                10,
                [{
                    "pair": "EURUSD_OTC",
                    "size": 300,
                    "to": 999,
                    "limit": 600,
                }],
                False,
            )
        ]
        assert client.callbacks[10] == []

    asyncio.run(run())


def test_get_candles_discards_invalid_and_duplicate_records():
    async def run():
        response = {
            "e": 10,
            "d": [{
                "p": "EURUSD_OTC",
                "tf": 60,
                "candles": [
                    candle(100, 1.0, 1.2, 0.9, 1.1),
                    candle(100, 1.0, 1.2, 0.9, 1.1),
                    candle(200, 1.0, 0.8, 0.9, 1.1),
                    {"t": 300, "open": "bad"},
                ],
            }],
        }
        api = MarketAPI(FakeClient(response))

        result = await api.get_candles("EURUSD_OTC", 60, 10)

        assert len(result) == 1
        assert result[0]["t"] == 100

    asyncio.run(run())


def test_get_candles_rejects_wrong_pair_or_timeframe():
    async def run():
        response = {
            "e": 10,
            "d": [{
                "p": "GBPUSD_OTC",
                "tf": 300,
                "candles": [candle(100, 1.0, 1.2, 0.9, 1.1)],
            }],
        }
        api = MarketAPI(FakeClient(response))

        with pytest.raises(ValueError, match="requested pair and timeframe"):
            await api.get_candles("EURUSD_OTC", 300, 10)

    asyncio.run(run())


def test_get_candles_validates_arguments():
    async def run():
        api = MarketAPI(FakeClient({"e": 10, "d": []}))

        with pytest.raises(ValueError):
            await api.get_candles("", 300, 10)

        with pytest.raises(ValueError):
            await api.get_candles("EURUSD_OTC", 0, 10)

        with pytest.raises(ValueError):
            await api.get_candles("EURUSD_OTC", 300, 0)

    asyncio.run(run())
