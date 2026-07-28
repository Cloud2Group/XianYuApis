"""Async business/native clients for the Unix JSONL bridge."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, Optional

from .protocol import (
    ProtocolError,
    decode_line,
    encode_message,
    make_hello,
    new_request_id,
    validate_event,
)


class BridgeClient:
    """One connected bridge peer.

    ``role=business`` exposes ``send_text`` and an event iterator.  A native
    adapter can use the same class with ``role=native`` and call ``send`` for
    events, then consume ``commands()``.
    """

    def __init__(
        self,
        path: str,
        *,
        role: str,
        account_id: str,
        connect_timeout: float = 10.0,
    ):
        self.path = path
        self.role = role
        self.account_id = account_id
        self.connect_timeout = connect_timeout
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._read_task: Optional[asyncio.Task[Any]] = None
        self._events: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._commands: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._pending: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._closed = False

    async def connect(self) -> Dict[str, Any]:
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_unix_connection(self.path), timeout=self.connect_timeout
        )
        await self._write(make_hello(self.role, self.account_id))
        raw = await asyncio.wait_for(self.reader.readline(), timeout=self.connect_timeout)
        if not raw:
            raise ConnectionError("bridge closed during handshake")
        hello = decode_line(raw)
        if hello.get("type") != "hello.ok":
            raise ProtocolError("bridge handshake failed")
        self._read_task = asyncio.create_task(self._reader_loop())
        return hello

    async def _write(self, frame: Dict[str, Any]) -> None:
        if self.writer is None or self._closed:
            raise ConnectionError("bridge client is not connected")
        self.writer.write(encode_message(frame))
        await self.writer.drain()

    async def send(self, frame: Dict[str, Any]) -> None:
        await self._write(frame)

    async def send_text(
        self,
        *,
        text: str,
        app_cid: Optional[str] = None,
        sid: Optional[str] = None,
        peer_uid: Optional[str] = None,
        reply_to_mid: Optional[str] = None,
        request_id: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        if self.role != "business":
            raise RuntimeError("send_text is a business-client operation")
        request_id = request_id or new_request_id()
        action = "reply_text" if reply_to_mid else "send_text"
        frame: Dict[str, Any] = {
            "action": action,
            "request_id": request_id,
            "account_id": self.account_id,
            "app_cid": app_cid,
            "sid": sid,
            "peer_uid": peer_uid,
            "text": text,
        }
        if reply_to_mid:
            frame["reply_to_mid"] = reply_to_mid
        future: "asyncio.Future[Dict[str, Any]]" = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._write(frame)
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def events(self) -> AsyncIterator[Dict[str, Any]]:
        while not self._closed:
            yield await self._events.get()

    async def commands(self) -> AsyncIterator[Dict[str, Any]]:
        while not self._closed:
            yield await self._commands.get()

    async def _reader_loop(self) -> None:
        assert self.reader is not None
        try:
            while True:
                raw = await self.reader.readline()
                if not raw:
                    break
                frame = decode_line(raw)
                if frame.get("event"):
                    try:
                        event = validate_event(frame)
                    except ProtocolError:
                        # Preserve unknown diagnostic events for callers while
                        # rejecting malformed business events from pending maps.
                        event = frame
                    if (
                        event.get("event") == "message.send.result"
                        and event.get("status")
                        in {"sent", "failed", "timeout", "duplicate"}
                    ):
                        request_id = event.get("request_id")
                        future = self._pending.get(request_id)
                        if future is not None and not future.done():
                            future.set_result(event)
                    await self._events.put(event)
                elif frame.get("action"):
                    await self._commands.put(frame)
                elif frame.get("type") == "error":
                    await self._events.put(frame)
        except (asyncio.CancelledError, ConnectionError, OSError, ProtocolError):
            pass
        finally:
            self._closed = True
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(ConnectionError("bridge connection closed"))
            self._pending.clear()

    async def close(self) -> None:
        self._closed = True
        if self._read_task is not None:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None
        if self.writer is not None:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (AttributeError, OSError):
                pass
            self.writer = None


class BusinessBridgeClient(BridgeClient):
    def __init__(self, path: str, account_id: str, **kwargs: Any):
        super().__init__(path, role="business", account_id=account_id, **kwargs)


class NativeBridgeClient(BridgeClient):
    def __init__(self, path: str, account_id: str, **kwargs: Any):
        super().__init__(path, role="native", account_id=account_id, **kwargs)
