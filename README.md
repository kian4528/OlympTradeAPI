# NIGHTSHIFT | OlympTrade API Workbench

A terminal-first workspace for experimenting with the existing OlympTrade WebSocket client. The original `olymptrade_ws` package remains the foundation; local tooling emphasizes safer configuration, visible warnings, and read-only examples by default.

## Design rules

- Credentials stay in your local environment or hidden terminal input.
- Raw WebSocket payloads are not written to disk.
- The default connection must use encrypted WebSockets and the official `ws.olymptrade.com` host.
- Example scripts do not place orders.
- API event mappings are reverse-engineered and can change without notice.

## Termux setup

```sh
pkg update
pkg install python
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configure and run

The safest approach is to enter the token only when prompted. To use an environment variable for the current shell session:

```sh
export OLYMPTRADE_ACCESS_TOKEN='paste-your-token-here'
python -m olymptrade_ws.main
```

Avoid putting a real token in shell history, screenshots, shared files, or source code. Clear the variable after use with `unset OLYMPTRADE_ACCESS_TOKEN`.

Run the read-only candle example with:

```sh
python simple_bot.py
```

The example inspects the latest candle and reports a simple directional bias. It does not submit a trade.

## Tests

```sh
python -m pytest -q
```

Tests are local and do not connect to OlympTrade or require a token.

## Privacy and network behavior

The Python client connects to `wss://ws.olymptrade.com/otp` by default and sends the supplied token as the `access_token` cookie to that host. Tokens containing cookie separators or control characters are rejected before connection. Trade submission is restricted to the configured demo account and now requires a verified `amount_free` value sufficient for the requested stake. It cannot authenticate without sending the token to the broker. Custom hosts are rejected unless the caller explicitly opts in with `allow_custom_endpoint=True`; do not enable that option for an endpoint you do not control and trust. The documentation website may load third-party assets if opened in a browser; the Python runtime does not need those website assets. Its browser trading panel is a local simulation and does not connect to a broker or submit real orders.

No source review can guarantee that a third-party service or a reverse-engineered private API is safe or stable. Use a demo account first, inspect future changes, and never provide this client with credentials you cannot afford to revoke.

## Project map

- `olymptrade_ws/core/` — WebSocket transport, protocol encoding, and message dispatch
- `olymptrade_ws/api/` — balance, market, and trade API wrappers
- `olymptrade_ws/main.py` — read-only interactive account overview
- `run_nightshift.py` — Rich terminal dashboard and demo-only strategy runner
- `simple_bot.py` — read-only candle and demo-balance example
- `olymptrade_ws/strategy/` — signal strategies and session tick recorder
- `REFERENCE.md` — protocol notes and implementation reference
- `docs/` — static documentation website and explicitly simulated trading panel

## Trading risk

This project is not affiliated with or endorsed by OlympTrade. It uses an undocumented/reverse-engineered protocol that may break at any time. No strategy or example guarantees a profit. Real-money orders should only be added deliberately and tested in demo mode first.
