import asyncio
import inspect
import logging
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

import websockets

from olymptrade_ws.olympconfig import parameters

logger = logging.getLogger(__name__)


class Connection:
    def __init__(self, uri: str, access_token: str, message_queue: asyncio.Queue, connection_lost_callback: Optional[Callable[[], Awaitable[None]]] = None, allow_custom_endpoint: bool = False):
        parsed_uri = urlsplit(uri)
        if parsed_uri.scheme != "wss":
            raise ValueError("The WebSocket endpoint must use wss://.")
        if not parsed_uri.hostname:
            raise ValueError("The WebSocket endpoint must include a hostname.")
        if not allow_custom_endpoint and parsed_uri.hostname.lower() != "ws.olymptrade.com":
            raise ValueError("Custom WebSocket hosts are blocked. Set allow_custom_endpoint=True only if you trust the endpoint.")
        if not access_token or not access_token.strip():
            raise ValueError("An access token is required.")
        self.uri = uri
        self.access_token = access_token.strip()
        self.message_queue = message_queue
        self.connection_lost_callback = connection_lost_callback
        self.websocket = None
        self._receive_task = None
        self._is_connected = False
        self._connect_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        if not self._is_connected or self.websocket is None:
            return False
        state = getattr(self.websocket, "state", None)
        if state is not None:
            return getattr(state, "name", "") == "OPEN"
        return not getattr(self.websocket, "closed", True)

    async def connect(self):
        async with self._connect_lock:
            if self.is_connected:
                return
            headers = {
                "Origin": parameters.DEFAULT_ORIGIN,
                "User-Agent": parameters.DEFAULT_USER_AGENT,
                "Cookie": f"access_token={self.access_token}",
            }
            connect_options = {
                "ping_interval": None,
                "open_timeout": parameters.DEFAULT_CONNECT_TIMEOUT,
                "max_size": parameters.MAX_MESSAGE_SIZE,
                "close_timeout": 5,
            }
            connect_parameters = inspect.signature(websockets.connect).parameters
            if "additional_headers" in connect_parameters:
                connect_options["additional_headers"] = headers
            else:
                connect_options["extra_headers"] = headers
            try:
                self.websocket = await websockets.connect(self.uri, **connect_options)
                self._is_connected = True
                self._receive_task = asyncio.create_task(self._receiver(), name="nightshift-websocket-receiver")
                logger.info("Connected to the configured OlympTrade WebSocket endpoint.")
            except Exception as exc:
                self._is_connected = False
                self.websocket = None
                logger.error("WebSocket connection failed (%s).", type(exc).__name__)
                raise ConnectionError(f"WebSocket connection failed: {type(exc).__name__}") from exc

    async def disconnect(self):
        async with self._connect_lock:
            self._is_connected = False
            task = self._receive_task
            self._receive_task = None
            if task and task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            websocket = self.websocket
            self.websocket = None
            if websocket is not None:
                try:
                    await websocket.close()
                except Exception as exc:
                    logger.debug("WebSocket close ended with %s.", type(exc).__name__)

    async def send(self, message: str):
        if not self.is_connected:
            raise ConnectionError("WebSocket is not connected.")
        try:
            await self.websocket.send(message)
        except Exception as exc:
            await self._handle_connection_loss()
            raise ConnectionError("WebSocket send failed.") from exc

    async def _receiver(self):
        try:
            while self._is_connected and self.websocket is not None:
                message = await self.websocket.recv()
                await self.message_queue.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("WebSocket receiver stopped (%s).", type(exc).__name__)
            await self._handle_connection_loss()

    async def _handle_connection_loss(self):
        was_connected = self._is_connected
        self._is_connected = False
        current_task = asyncio.current_task()
        receive_task = self._receive_task
        self._receive_task = None
        if receive_task and receive_task is not current_task and not receive_task.done():
            receive_task.cancel()
        self.websocket = None
        if was_connected and self.connection_lost_callback:
            asyncio.create_task(self.connection_lost_callback(), name="nightshift-connection-lost")
