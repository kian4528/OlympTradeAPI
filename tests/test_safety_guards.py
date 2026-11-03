import asyncio

from olymptrade_ws.api.market import MarketAPI
from olymptrade_ws.api.balance import BalanceAPI


class FakeClient:
    def __init__(self):
        self.callbacks = {}
        self.sent = []

    def register_callback(self, event, callback):
        self.callbacks.setdefault(event, []).append(callback)

    def unregister_callback(self, event, callback):
        self.callbacks[event].remove(callback)

    async def send_request(self, event, data, requires_response=True, timeout=None):
        self.sent.append((event, data, requires_response))

        if event == 95:
            assert 80 in self.callbacks
            message = {"e": 80, "d": [{"p": "EURUSD", "strike": 1.25}]}
            for callback in tuple(self.callbacks[80]):
                await callback(message)
            return {"e": 95, "d": []}

        if event == 10:
            message = {
                "e": 10,
                "d": [{
                    "p": "EURUSD",
                    "tf": 60,
                    "candles": [{
                        "t": 100,
                        "open": 1.1,
                        "high": 1.2,
                        "low": 1.0,
                        "close": 1.15,
                    }],
                }],
            }
            for callback in tuple(self.callbacks.get(10, [])):
                await callback(message)

        return {"e": event, "d": []}


def test_select_asset_registers_callback_before_request():
    async def run():
        client = FakeClient()
        result = await MarketAPI(client).select_asset("EURUSD")
        assert result == {"p": "EURUSD", "strike": 1.25}
        assert [item[0] for item in client.sent] == [95]
        assert client.callbacks[80] == []

    asyncio.run(run())


def test_verified_history_request_is_read_only_and_profitability_is_disabled():
    async def run():
        client = FakeClient()
        api = MarketAPI(client)

        candles = await api.get_candles("EURUSD", 60, 10)
        assert len(candles) == 1
        assert candles[0]["close"] == 1.15

        assert await api.get_profitability(123) is None
        assert [item[0] for item in client.sent] == [10]
        assert client.callbacks[10] == []

    asyncio.run(run())


def test_explicit_balance_request_is_safe_noop():
    async def run():
        client = FakeClient()
        api = BalanceAPI(client)
        assert await api.request_balance(123, "demo") is None
        assert client.sent == []

    asyncio.run(run())
