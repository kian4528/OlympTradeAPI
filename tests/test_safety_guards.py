import asyncio
import inspect

import pytest

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
                result = callback(message)
                if inspect.isawaitable(result):
                    await result
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
                result = callback(message)
                if inspect.isawaitable(result):
                    await result

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


@pytest.mark.parametrize(
    "token",
    ["bad;token", "bad,token", "bad\\token", "bad\r\ntoken", "bad token"],
)
def test_connection_rejects_tokens_that_cannot_be_safely_used_in_cookie(token):
    import asyncio

    from olymptrade_ws.core.connection import Connection

    with pytest.raises(ValueError, match="cookie"):
        Connection(
            "wss://ws.olymptrade.com/otp",
            token,
            asyncio.Queue(),
        )


def test_connection_rejects_uri_userinfo_and_nonstandard_official_port():
    import asyncio

    from olymptrade_ws.core.connection import Connection

    for uri in (
        "wss://user:password@ws.olymptrade.com/otp",
        "wss://ws.olymptrade.com:8443/otp",
        "wss://ws.olymptrade.com/otp#fragment",
    ):
        with pytest.raises(ValueError):
            Connection(uri, "test-token", asyncio.Queue())


def test_client_dispatches_synchronous_callbacks_without_creating_tasks():
    import asyncio

    from olymptrade_ws.core.client import OlympTradeClient

    async def run():
        client = OlympTradeClient("test-token")
        received = []
        client.register_callback(777, received.append)
        await client._dispatch_message({"e": 777, "d": [1]})
        assert received == [{"e": 777, "d": [1]}]
        assert client._callback_tasks == set()
        await client.stop()

    asyncio.run(run())


def test_message_loop_cancellation_does_not_call_task_done_without_a_message():
    import asyncio

    from olymptrade_ws.core.client import OlympTradeClient

    async def run():
        client = OlympTradeClient("test-token")
        client._is_running = True
        task = asyncio.create_task(client._process_messages())
        await asyncio.sleep(0)
        task.cancel()
        await task
        assert client.message_queue._unfinished_tasks == 0
        await client.stop()

    asyncio.run(run())


def test_nightshift_closed_trade_deduplication_uses_constant_time_set_membership():
    from run_nightshift import Runner

    class DashboardStub:
        def __init__(self):
            self.trades = []
            self.stats = None

        def add_trade(self, *args):
            self.trades.append(args)

        def set_stats(self, stats):
            self.stats = stats

        def update(self, row, value):
            return None

    runner = Runner.__new__(Runner)
    runner.stats = {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "net": 0.0,
        "closed_ids": set(),
        "last_close": "NONE",
    }
    runner.pair = "EURUSD"
    runner.dashboard = DashboardStub()
    runner.active_order = True
    runner.stop_event = asyncio.Event()
    message = {"d": [{"id": 123, "status": "win", "balance_change": 0.85, "dir": "up"}]}

    runner.on_closed(message)
    runner.on_closed(message)

    assert runner.stats["trades"] == 1
    assert runner.stats["wins"] == 1
    assert runner.stats["closed_ids"] == {"123"}
    assert len(runner.dashboard.trades) == 1


def test_balance_records_reject_boolean_and_nonpositive_account_ids():
    from olymptrade_ws.api.balance import BalanceAPI

    class BalanceClient:
        _latest_balance = {
            "d": [
                {"account_id": True, "group": "demo"},
                {"account_id": 0, "group": "demo"},
                {"account_id": -1, "group": "real"},
                {"account_id": 123, "group": "demo"},
            ]
        }

    records = BalanceAPI(BalanceClient()).get_account_records()
    assert records == [{"account_id": 123, "group": "demo"}]
