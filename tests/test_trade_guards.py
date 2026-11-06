import asyncio

import pytest

from olymptrade_ws.api.trade import TradeAPI


class DemoBalance:
    def __init__(self, account):
        self.account = account

    def get_demo_account(self):
        return self.account


class FakeTradeClient:
    def __init__(self, account=None):
        self.account_group = "demo"
        self.account_id = 12345
        self.balance = DemoBalance(account or {"account_id": 12345, "group": "demo", "amount_free": "100.00"})
        self.sent = []

    async def send_request(self, event_code, data, requires_response=True, timeout=None):
        self.sent.append((event_code, data, requires_response, timeout))
        return {"e": 23, "d": [{"id": 9876, "status": "accepted"}]}


def test_place_order_requires_verified_demo_balance_and_caps_stake():
    async def run():
        client = FakeTradeClient()
        api = TradeAPI(client)

        with pytest.raises(ValueError, match="available demo balance"):
            await api.place_order("EURUSD", 101, "up", 60, 12345)

        assert client.sent == []

    asyncio.run(run())


def test_place_order_accepts_valid_demo_order_and_preserves_payload_shape():
    async def run():
        client = FakeTradeClient()
        api = TradeAPI(client)

        result = await api.place_order("EURUSD", 10, "up", 60, 12345)

        assert result == {"id": 9876, "status": "accepted"}
        event_code, payload, requires_response, timeout = client.sent[0]
        assert event_code == 23
        assert requires_response is True
        assert timeout == 5.0
        assert payload[0]["amount"] == 10
        assert payload[0]["group"] == "demo"
        assert payload[0]["account_id"] == 12345

    asyncio.run(run())


def test_place_order_rejects_missing_demo_balance_before_sending():
    async def run():
        client = FakeTradeClient(account=None)
        client.balance.account = None
        api = TradeAPI(client)

        with pytest.raises(RuntimeError, match="verified demo balance"):
            await api.place_order("EURUSD", 10, "up", 60, 12345)

        assert client.sent == []

    asyncio.run(run())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pos": True},
        {"timestamp": False},
        {"risk_free_id": True},
        {"is_flex": 1},
        {"source": "platform\r\nCookie: injected"},
        {"category": " digital"},
    ],
)
def test_place_order_rejects_malformed_order_fields(kwargs):
    async def run():
        client = FakeTradeClient()
        api = TradeAPI(client)
        parameters = {
            "pair": "EURUSD",
            "amount": 10,
            "direction": "up",
            "duration": 60,
            "account_id": 12345,
        }
        parameters.update(kwargs)

        with pytest.raises(ValueError):
            await api.place_order(**parameters)

        assert client.sent == []

    asyncio.run(run())
