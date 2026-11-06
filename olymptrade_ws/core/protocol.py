import json
import logging
import secrets
import string
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def generate_uuid() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(12))


def format_message(
    event_code: int,
    data: Any,
    request_uuid: Optional[str] = None,
) -> str:
    if not isinstance(event_code, int) or event_code < 0:
        raise ValueError("event_code must be a non-negative integer")

    message = {"t": 2, "e": event_code, "d": data}
    if request_uuid:
        message["uuid"] = request_uuid

    return json.dumps(
        [message],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def parse_message(raw_message: str) -> Optional[List[Dict[str, Any]]]:
    try:
        data = json.loads(raw_message)
    except (json.JSONDecodeError, TypeError) as exc:
        # Never log the raw message: it could contain sensitive data.
        logger.debug(
            "Ignoring malformed protocol message (%s).",
            type(exc).__name__,
        )
        return None

    if not isinstance(data, list):
        logger.debug(
            "Ignoring protocol message with unexpected top-level type %s.",
            type(data).__name__,
        )
        return None

    parsed_items = [item for item in data if isinstance(item, dict)]
    ignored_count = len(data) - len(parsed_items)

    if ignored_count:
        logger.debug(
            "Ignored %d non-object item(s) in protocol message.",
            ignored_count,
        )

    return parsed_items


def get_current_timestamp_ms() -> int:
    return time.time_ns() // 1_000_000
