import asyncio
import inspect
import logging
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

import websockets

from olymptrade_ws.olympconfig import parameters

logger = logging.getLogger(__name__)


class Connection:
    def __init__(
        self,
        uri: str,
        access_token: str,
        message_queue: asyncio.Queue,
        connection_lost_callback: Optional[Callable[[], Awaitable[None]]] = None,
        allow_custom_endpoint: bool = False,
    ):
        if not isinstance(uri, str) or not uri:
            raise ValueError("A valid secure WebSocket endpoint is required.")

        try:
            parsed_uri = urlsplit(uri)
            port = parsed_uri.port
        except ValueError as exc:
            raise ValueError("A valid secure WebSocket endpoint is required.") from exc

        if (
            parsed_uri.scheme != "wss"
            or not parsed_uri.hostname
            or parsed_uri.username is not None
            or parsed_uri.password is not None
            or parsed_uri.fragment
        ):
            raise ValueError("A valid secure WebSocket endpoint is required.")

        if not allow_custom_endpoint:
            if parsed_uri.hostname.lower() != "ws.olymptrade.com":
                raise ValueError("Custom WebSocket hosts are blocked.")
            if port not in (None, 443):
                raise ValueError("Non-standard WebSocket ports are blocked.")

        if not isinstance(access_token, str) or not access_token:
            raise ValueError("An access token is required.")

        token = access_token.strip()
        if not token or any(
            not (
                0x21 == ord(character)
                or 0x23 <= ord(character) <= 0x2B
                or 0x2D <= ord(character) <= 0x3A
                or 0x3C <= ord(character) <= 0x5B
                or 0x5D <= ord(character) <= 0x7E
            )
            for character in token
        ):
            raise ValueError("The access token contains invalid cookie characters.")

        self.uri = uri
        self.access_token = token
        self.message_queue = message_queue
        self.connection_lost_callback = connection_lost_callback
        self.websocket = None
        self._receive_task = None
        self._is_connected = False
        self._connect_lock = asyncio.Lock()
        self._closing = False

    @property
    def is_connected(self):
        websocket = self.websocket
        if not self._is_connected or websocket is None:
            return False
        state = getattr(websocket, "state", None)
        if state is not None:
            return getattr(state, "name", "") == "OPEN"
        return not getattr(websocket, "closed", True)

    async def connect(self):
        async with self._connect_lock:
            if self.is_connected:
                return

            self._closing = False
            headers = {
                "Origin": parameters.DEFAULT_ORIGIN,
                "User-Agent": parameters.DEFAULT_USER_AGENT,
                "Cookie": f"access_token={self.access_token}",
            }
            options = {
                "ping_interval": None,
                "open_timeout": parameters.DEFAULT_CONNECT_TIMEOUT,
                "max_size": parameters.MAX_MESSAGE_SIZE,
                "close_timeout": 5,
            }
            signature = inspect.signature(websockets.connect).parameters
            if "additional_headers" in signature:
                options["additional_headers"] = headers
            else:
                options["extra_headers"] = headers

            try:
                self.websocket = await websockets.connect(self.uri, **options)
                self._is_connected = True
                self._receive_task = asyncio.create_task(
                    self._receiver(),
                    name="nightshift-websocket-receiver",
                )
                logger.info("WebSocket handshake completed.")
            except Exception as exc:
                self._is_connected = False
                websocket = self.websocket
                self.websocket = None
                if websocket is not None:
                    await websocket.close()
                logger.exception("WebSocket connection failed.")
                raise ConnectionError(
                    f"WebSocket connection failed: {type(exc).__name__}"
                ) from exc

    async def disconnect(self):
        async with self._connect_lock:
            self._closing = True
            self._is_connected = False
            task = self._receive_task
            self._receive_task = None

            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

            websocket = self.websocket
            self.websocket = None
            if websocket is not None:
                try:
                    await websocket.close()
                except Exception as exc:
                    logger.debug("WebSocket close ended with %s.", type(exc).__name__)

    async def send(self, message):
        if not self.is_connected:
            raise ConnectionError("WebSocket is not connected.")
        try:
            await self.websocket.send(message)
        except Exception as exc:
            await self._handle_connection_loss()
            raise ConnectionError("WebSocket send failed.") from exc

    async def _receiver(self):
        try:
            while self.is_connected:
                message = await self.websocket.recv()
                await self.message_queue.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._closing:
                logger.exception("WebSocket receiver failed.")
                await self._handle_connection_loss()

    async def _handle_connection_loss(self):
        if self._closing:
            return

        was_connected = self._is_connected
        self._is_connected = False
        current_task = asyncio.current_task()
        receive_task = self._receive_task
        self._receive_task = None

        if receive_task and receive_task is not current_task and not receive_task.done():
            receive_task.cancel()

        websocket = self.websocket
        self.websocket = None
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass

        if was_connected and self.connection_lost_callback:
            asyncio.create_task(
                self.connection_lost_callback(),
                name="nightshift-connection-lost",
            )
