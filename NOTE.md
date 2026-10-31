# NIGHTSHIFT / Field Notes

**Operating mode:** quiet, local-first, deliberate.

This workspace is a tool, not an autopilot. It should tell me what it knows, admit what it cannot verify, and never turn a market observation into a live order without an explicit decision.

## House rules

1. Secrets belong in hidden input or the current shell environment, never in source files.
2. Logs describe events, not private payloads. No balances, account identifiers, cookies, or session messages are dumped to disk.
3. Default behavior is read-only. An example must not surprise me with a trade.
4. The broker endpoint is the only default destination for the authentication token.
5. Unknown protocol behavior is marked as uncertain instead of dressed up as fact.
6. Small, reversible changes beat clever complexity.

## Visual identity

NIGHTSHIFT uses a restrained terminal aesthetic: midnight background, cool cyan signals, amber warnings, short labels, and direct status messages. The code follows the same idea: explicit names, compact control flow, and no noise that hides important events.

## Before a session

- Use a demo account where possible.
- Confirm the configured WebSocket hostname.
- Check that no token is committed or printed.
- Run the local tests.
- Stop the client when the session is over.
