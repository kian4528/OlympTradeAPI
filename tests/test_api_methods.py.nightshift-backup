import json

from olymptrade_ws.core.protocol import format_message, generate_uuid, parse_message


def test_generated_request_ids_are_unique_and_nonempty():
    identifiers = {generate_uuid() for _ in range(100)}
    assert len(identifiers) == 100
    assert all(len(identifier) == 12 for identifier in identifiers)


def test_format_message_uses_compact_json_and_expected_shape():
    encoded = format_message(12, [{"pair": "EURUSD"}], "request123456")
    assert json.loads(encoded) == [{"t": 2, "e": 12, "d": [{"pair": "EURUSD"}], "uuid": "request123456"}]
    assert " " not in encoded


def test_format_message_rejects_invalid_event_code():
    try:
        format_message(-1, {})
    except ValueError:
        pass
    else:
        raise AssertionError("negative event codes must be rejected")


def test_parse_message_ignores_non_dictionary_items():
    assert parse_message('[{"e": 1}, 3, null, {"e": 55}]') == [{"e": 1}, {"e": 55}]


def test_parse_message_rejects_invalid_json_and_non_lists():
    assert parse_message("not json") is None
    assert parse_message('{"e": 1}') is None


def test_connection_rejects_plaintext_websocket_urls():
    import asyncio
    import pytest
    from olymptrade_ws.core.connection import Connection

    with pytest.raises(ValueError):
        Connection("ws://ws.olymptrade.com/otp", "token", asyncio.Queue())


def test_connection_rejects_unapproved_hosts():
    import asyncio
    import pytest
    from olymptrade_ws.core.connection import Connection

    with pytest.raises(ValueError):
        Connection("wss://example.com/socket", "token", asyncio.Queue())


def test_client_preserves_explicit_account_context():
    from olymptrade_ws.core.client import OlympTradeClient

    client = OlympTradeClient("test-token", account_id=12345, account_group="demo")
    assert client.account_id == 12345
    assert client.account_group == "demo"
    assert client._log_raw_messages is False
