# core/client.py
import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
# core/client.py - Line 6 (Corrected)
from olymptrade_ws.olympconfig import parameters
from .connection import Connection
from .protocol import format_message, parse_message, generate_uuid
from olymptrade_ws.api import balance, market, trade # Import API modules
import olymptrade_ws.olympconfig.parameters as settings

logger = logging.getLogger(__name__)

class OlympTradeClient:
    def __init__(self, access_token: str, uri: str = parameters.DEFAULT_WEBSOCKET_URI, log_raw_messages: bool = False, account_id: int = None, account_group: str = None, allow_custom_endpoint: bool = False):
        self.uri = uri
        self.account_id = account_id
        self.account_group = account_group
        self.message_queue = asyncio.Queue(maxsize=1000)
        self.connection = Connection(self.uri, access_token, self.message_queue, self._connection_lost_handler, allow_custom_endpoint=allow_custom_endpoint)

        self._response_futures: Dict[str, asyncio.Future] = {}
        self._event_callbacks: Dict[int, List[Callable[[Dict[str, Any]], Union[Awaitable[None], None]]]] = defaultdict(list)
        self._callback_tasks: set[asyncio.Future] = set()
        self._is_running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._log_raw_messages = False
        if log_raw_messages:
            logger.warning(
                "Raw message logging is unsupported because payloads may contain private account data."
            )

        # --- API Modules ---
        self.balance = balance.BalanceAPI(self)
        self.market = market.MarketAPI(self)
        self.trade = trade.TradeAPI(self)
        # Add other API modules here

        self._latest_balance: Dict[str, Any] = {}
        self._session_initialized = False


    async def start(self):
        logger.info("Starting NIGHTSHIFT client...")
        if self._is_running:
            logger.warning("Client is already running.")
            return
        
        try:
            await self.connection.connect()
            self._is_running = True
            self._processing_task = asyncio.create_task(self._process_messages())
            self._ping_task = asyncio.create_task(self._ping_loop())
            logger.info("NIGHTSHIFT client started.")
        except ConnectionError as e:
            logger.error(f"Client failed to start: {e}")
            self._is_running = False
            # Optionally re-raise or handle startup failure
            raise

    async def stop(self):
        """Stop the client and clean up tasks and pending requests."""
        logger.info("Stopping NIGHTSHIFT client...")
        self._is_running = False

        current_task = asyncio.current_task()
        tasks = [self._ping_task, self._processing_task]
        for task in tasks:
            if task is not None and task is not current_task and not task.done():
                task.cancel()

        callback_tasks = tuple(
            task for task in self._callback_tasks if task is not current_task
        )
        for task in callback_tasks:
            if not task.done():
                task.cancel()

        await self.connection.disconnect()

        active_tasks = [
            task for task in tasks
            if task is not None and task is not asyncio.current_task()
        ]
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)
        if callback_tasks:
            await asyncio.gather(*callback_tasks, return_exceptions=True)
        self._callback_tasks.clear()

        while not self.message_queue.empty():
            try:
                self.message_queue.get_nowait()
                self.message_queue.task_done()
            except asyncio.QueueEmpty:
                break

        self._ping_task = None
        self._processing_task = None

        for future in self._response_futures.values():
            if not future.done():
                future.cancel()
        self._response_futures.clear()

        self._session_initialized = False
        self.balance._subscribed = False

        logger.info("NIGHTSHIFT client stopped.")

    async def _connection_lost_handler(self):
        """Callback executed by Connection when the websocket closes unexpectedly."""
        logger.warning("Connection lost. Attempting to clean up and stop client.")
        # Signal loops to stop if they haven't already noticed
        self._is_running = False 
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            
        # Reset session state after an unexpected disconnect.
        self._session_initialized = False
        self.balance._subscribed = False

        for task in tuple(self._callback_tasks):
            if not task.done():
                task.cancel()

        # Wake callers waiting for UUID-correlated responses.
        for fut in tuple(self._response_futures.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("WebSocket connection lost"))
        self._response_futures.clear()
        
        # TODO: Implement reconnection logic here if desired
        logger.info("Client state reset due to connection loss. Manual restart required (or implement auto-reconnect).")


    def register_callback(
        self,
        event_code: int,
        callback: Callable[[Dict[str, Any]], Union[Awaitable[None], None]],
    ) -> None:
        """Register a callback for a specific unsolicited event code."""
        if (
            not isinstance(event_code, int)
            or isinstance(event_code, bool)
            or event_code < 0
        ):
            raise ValueError("event_code must be a non-negative integer")
        if not callable(callback):
            raise TypeError("callback must be callable")
        if callback not in self._event_callbacks[event_code]:
            self._event_callbacks[event_code].append(callback)

    def unregister_callback(
        self,
        event_code: int,
        callback: Callable[[Dict[str, Any]], Union[Awaitable[None], None]],
    ) -> None:
        """Unregister a specific callback."""
        if event_code in self._event_callbacks:
            try:
                self._event_callbacks[event_code].remove(callback)
                if not self._event_callbacks[event_code]: # Remove key if list is empty
                    del self._event_callbacks[event_code]
            except ValueError:
                return


    async def send_request(
        self,
        event_code: int,
        data: Any,
        requires_response: bool = True,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a protocol request and optionally await its UUID response."""
        if not self.connection.is_connected:
            raise ConnectionError("Not connected")

        request_uuid = generate_uuid() if requires_response else None
        message_str = format_message(event_code, data, request_uuid)

        logger.debug(
            "Sending event %s (request id %s).",
            event_code,
            request_uuid or "none",
        )

        future = None
        if request_uuid:
            future = asyncio.get_running_loop().create_future()
            self._response_futures[request_uuid] = future

        try:
            await self.connection.send(message_str)
        except Exception:
            if request_uuid:
                self._response_futures.pop(request_uuid, None)
            if future is not None and not future.done():
                future.cancel()
            raise

        if future is None:
            return None

        try:
            response_timeout = (
                timeout
                if timeout is not None
                else parameters.DEFAULT_RESPONSE_TIMEOUT
            )
            return await asyncio.wait_for(future, timeout=response_timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for event %s (request id %s).",
                event_code,
                request_uuid,
            )
            self._response_futures.pop(request_uuid, None)
            raise
        except asyncio.CancelledError:
            self._response_futures.pop(request_uuid, None)
            raise

    async def _process_messages(self):
        logger.debug("Message dispatcher started.")
        """Continuously processes messages from the connection queue."""
        while self._is_running:
            try:
                raw_message = await self.message_queue.get()
            except asyncio.CancelledError:
                logger.info("Message processing loop cancelled.")
                break

            try:
                parsed_messages = parse_message(raw_message)
                if parsed_messages:
                    for message in parsed_messages:
                        await self._dispatch_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Message processing failed (%s).", type(exc).__name__)
                await asyncio.sleep(1)
            finally:
                self.message_queue.task_done()
        logger.info("Message processing loop finished.")

    async def _dispatch_message(self, message: Dict[str, Any]):
        request_uuid = message.get("uuid")
        event_code = message.get("e")
        if not isinstance(event_code, int) or isinstance(event_code, bool):
            logger.warning("Received a message with an invalid event code.")
            return

        if event_code == settings.E_BALANCE_UPDATE:
            self._latest_balance = message

        matched = bool(
            request_uuid and request_uuid in self._response_futures
        )

        if matched:
            future = self._response_futures.pop(request_uuid)
            if not future.done():
                future.set_result(message)

        if event_code in self._event_callbacks:
            for callback in list(self._event_callbacks[event_code]):
                try:
                    result = callback(message)
                    if inspect.isawaitable(result):
                        task = asyncio.ensure_future(result)
                        self._callback_tasks.add(task)

                        def report_callback_error(done_task, code=event_code):
                            self._callback_tasks.discard(done_task)
                            if done_task.cancelled():
                                return
                            error = done_task.exception()
                            if error is not None:
                                logger.error(
                                    "Event callback failed for event %s (%s).",
                                    code,
                                    type(error).__name__,
                                )

                        task.add_done_callback(report_callback_error)
                except Exception as exc:
                    logger.error(
                        "Event callback failed for event %s (%s).",
                        event_code,
                        type(exc).__name__,
                    )

    async def _ping_loop(self):
        while self._is_running:
            try:
                await self.send_request(
                    settings.E_PING,
                    {},
                    requires_response=True,
                    timeout=10.0,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Ping request failed (%s).", type(exc).__name__)
            await asyncio.sleep(settings.PING_INTERVAL)

    # --- Convenience property to get last known balance ---
    @property
    def current_balance(self) -> Dict[str, Any]:
        """Returns the last known balance dictionary received from the server (event 55)."""
        return self._latest_balance

    async def initialize_session(self):
        if self._session_initialized:
            return

        if not self.connection.is_connected:
            raise ConnectionError("Cannot initialize a disconnected client.")

        self.account_id = None
        self.account_group = None

        startup_subscriptions = [
            [220],
            [110, 700, 112, 140, 1038, 1037, 1039, 141, 22, 26, 111],
            [1054, 1076, 1301, 1097],
            [141, 241],
            [230, 231],
            [75],
            [1055],
            [2223, 2301, 55, 150, 152, 151, 126, 602, 601],
            [2076],
            [126],
        ]

        for subscription in startup_subscriptions:
            await self.send_request(
                settings.E_SUBSCRIBE_EVENTS,
                subscription,
                requires_response=False,
            )

        self.balance._subscribed = True

        await self.wait_for_balance(timeout=10.0)

        demo_account = self.balance.get_demo_account()
        if not demo_account:
            raise RuntimeError(
                "Could not identify exactly one demo account. "
                "Order submission remains disabled."
            )

        demo_id = demo_account.get("account_id")
        if (
            not isinstance(demo_id, int)
            or isinstance(demo_id, bool)
            or demo_id <= 0
        ):
            raise RuntimeError("Invalid demo account ID.")

        self.account_id = demo_id
        self.account_group = "demo"
        self._session_initialized = True

        logger.info("Demo account selected: %s", demo_id)

    async def wait_for_balance(self, timeout: float = 10.0, poll_interval: float = 0.5):
        """
        Waits until a balance update is received or timeout is reached.
        Returns the balance dict if received, else None.
        """
        if timeout < 0:
            raise ValueError("timeout must not be negative")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")

        logger.info("Waiting for a balance update (timeout=%s seconds).", timeout)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            balance_data = self.balance.get_last_balance()
            if balance_data and balance_data.get("d"):
                logger.info("Balance update received.")
                return balance_data

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(poll_interval, remaining))

        logger.warning("Timed out waiting for a balance update.")
        return None
