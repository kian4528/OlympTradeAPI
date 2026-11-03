"""NIGHTSHIFT OlympTrade client package with lazy public exports."""

__all__ = [
    "OlympTradeClient",
    "CoreOlympTradeClient",
    "BalanceAPI",
    "MarketAPI",
    "TradeAPI",
]


def __getattr__(name):
    if name == "OlympTradeClient":
        from .main import OlympTradeClient
        return OlympTradeClient
    if name == "CoreOlympTradeClient":
        from .core.client import OlympTradeClient
        return OlympTradeClient
    if name == "BalanceAPI":
        from .api.balance import BalanceAPI
        return BalanceAPI
    if name == "MarketAPI":
        from .api.market import MarketAPI
        return MarketAPI
    if name == "TradeAPI":
        from .api.trade import TradeAPI
        return TradeAPI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
