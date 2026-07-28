"""Permissioned Unix-domain bridge between the App and business logic."""

from __future__ import annotations

import argparse
import asyncio
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from .protocol import (
    ProtocolError,
    decode_line,
    encode_message,
    make_send_result,
    make_status,
    now_ms,
    safe_log_frame,
    validate_command,
    validate_event,
    validate_hello,
)
from .queueing import ResultLedger, SessionSerialiser


@dataclass(eq=False)
class _Peer:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    role: str = "unknown"
    account_id: str = ""
    closed: bool = False

    async def send(self, frame: Dict[str, Any]) -> None:
        if self.closed:
            raise ConnectionError("peer is closed")
        self.writer.write(encode_message(frame))
        await self.writer.drain()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (AttributeError, OSError):
            pass


class NativeBridgeServer:
    """Route native events and business commands for one account.

    The server never opens the App database and never handles login material.
    A native adapter (Frida, a signed helper, or a future in-process shim)
    owns AIM objects and speaks this small protocol.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        account_id: str,
        *,
        command_timeout: float = 30.0,
        max_frame_bytes: int = 256 * 1024,
    ):
        self.path = str(Path(path).expanduser())
        self.account_id = str(account_id)
        self.command_timeout = max(0.1, float(command_timeout))
        self.max_frame_bytes = max_frame_bytes
        self._server: Optional[asyncio.AbstractServer] = None
        self._native: Optional[_Peer] = None
        self._business: Set[_Peer] = set()
        self._tasks: Set[asyncio.Task[Any]] = set()
        self._pending: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._pending_commands: Dict[str, Dict[str, Any]] = {}
        self._seen_messages = ResultLedger(max_entries=8192, ttl_seconds=3600)
        self._completed_requests = ResultLedger(max_entries=4096, ttl_seconds=1800)
        self._serialiser = SessionSerialiser()
        self._stopping = False
        self._last_heartbeat_ms: Optional[int] = None
        self._reconnect_count = 0

    @property
    def socket_path(self) -> str:
        return self.path

    async def start(self) -> None:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        parent_stat = path.parent.stat()
        if parent_stat.st_uid == os.getuid():
            os.chmod(str(path.parent), 0o700)
        if path.exists() or path.is_symlink():
            path_stat = path.lstat()
            mode = path_stat.st_mode
            if not stat.S_ISSOCK(mode):
                raise RuntimeError("refusing to replace non-socket path: %s" % path)
            if path_stat.st_uid != os.getuid():
                raise RuntimeError("refusing to replace socket owned by another user: %s" % path)
            path.unlink()
        self._server = await asyncio.start_unix_server(
            self._accept, path=self.path
        )
        os.chmod(self.path, 0o600)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        self._stopping = True
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        peers = list(self._business)
        if self._native is not None:
            peers.append(self._native)
        for peer in peers:
            await peer.close()
        self._business.clear()
        self._native = None
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(ConnectionError("bridge stopped"))
        self._pending.clear()
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        try:
            Path(self.path).unlink()
        except FileNotFoundError:
            pass

    def _track(self, task: asyncio.Task[Any]) -> None:
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = _Peer(reader, writer)
        task = asyncio.create_task(self._peer_loop(peer))
        self._track(task)

    async def _peer_loop(self, peer: _Peer) -> None:
        try:
            raw = await asyncio.wait_for(peer.reader.readline(), timeout=10.0)
            if not raw:
                return
            hello = validate_hello(decode_line(raw))
            if hello["account_id"] != self.account_id:
                await peer.send({"type": "error", "code": "ACCOUNT_MISMATCH"})
                return
            peer.role = hello["role"]
            peer.account_id = hello["account_id"]
            if peer.role == "native":
                if self._native is not None:
                    await self._native.close()
                    self._reconnect_count += 1
                self._native = peer
                await peer.send({
                    "type": "hello.ok",
                    "protocol": 1,
                    "role": "native",
                    "account_id": self.account_id,
                })
                await self._broadcast_status("connected")
            else:
                self._business.add(peer)
                await peer.send({
                    "type": "hello.ok",
                    "protocol": 1,
                    "role": peer.role,
                    "account_id": self.account_id,
                })
                await peer.send(
                    make_status(
                        account_id=self.account_id,
                        state="connected" if self._native else "app_ready",
                        last_heartbeat_ms=self._last_heartbeat_ms,
                        reconnect_count=self._reconnect_count,
                    )
                )

            while True:
                raw = await peer.reader.readline()
                if not raw:
                    break
                if len(raw) > self.max_frame_bytes:
                    await peer.send({"type": "error", "code": "FRAME_TOO_LARGE"})
                    break
                try:
                    frame = decode_line(raw)
                    if peer.role == "native":
                        await self._handle_native(peer, frame)
                    else:
                        await self._handle_business(peer, frame)
                except ProtocolError as exc:
                    await peer.send({
                        "type": "error",
                        "code": "PROTOCOL_ERROR",
                        "message": str(exc),
                    })
        except (asyncio.CancelledError, asyncio.TimeoutError, ConnectionError, OSError):
            pass
        finally:
            await self._remove_peer(peer)

    async def _remove_peer(self, peer: _Peer) -> None:
        if peer.closed:
            return
        peer.closed = True
        if peer is self._native:
            self._native = None
            if not self._stopping:
                await self._broadcast_status("reconnecting")
                self._fail_pending("NATIVE_DISCONNECTED", "native peer disconnected")
        self._business.discard(peer)
        try:
            peer.writer.close()
            await peer.writer.wait_closed()
        except (AttributeError, OSError):
            pass

    async def _handle_native(self, peer: _Peer, frame: Dict[str, Any]) -> None:
        if frame.get("event"):
            event = validate_event(frame)
            if event["account_id"] != self.account_id:
                raise ProtocolError("account mismatch")
            if event["event"] == "message.received":
                message_id = str(event["message_id"])
                if await self._seen_messages.get(message_id) is not None:
                    return
                await self._seen_messages.put(message_id, {"seen": True})
            elif event["event"] == "transport.status":
                self._last_heartbeat_ms = event.get("last_heartbeat_ms") or now_ms()
            elif event["event"] == "message.send.result":
                await self._resolve_result(event)
                # Accepted/progress notifications are useful to observers.
                # The terminal result is broadcast by _complete(), once the
                # per-session operation has been released.
                if event.get("status") in {"accepted"}:
                    await self._broadcast(event)
                return
            await self._broadcast(event)
            return
        # Native adapters may send a lightweight heartbeat without wrapping it
        # in a transport.status event.
        if frame.get("type") == "heartbeat":
            self._last_heartbeat_ms = now_ms()
            return
        raise ProtocolError("native frame must be an event")

    async def _handle_business(self, peer: _Peer, frame: Dict[str, Any]) -> None:
        command = validate_command(frame)
        if command["account_id"] != self.account_id:
            raise ProtocolError("account mismatch")
        if command["action"] == "ping":
            await peer.send(make_status(
                account_id=self.account_id,
                state="connected" if self._native else "app_ready",
                last_heartbeat_ms=self._last_heartbeat_ms,
                reconnect_count=self._reconnect_count,
            ))
            return
        if command["action"] == "mark_read":
            await self._forward_to_native(command)
            return

        request_id = str(command["request_id"])
        previous = await self._completed_requests.get(request_id)
        if previous is not None:
            await peer.send(dict(previous, status="duplicate"))
            return
        key = self._session_key(command)
        task = asyncio.create_task(self._run_command(key, command))
        self._track(task)
        # The task broadcasts the result to every business peer.  A short
        # accepted acknowledgement makes the caller observable before the App
        # callback arrives and is also useful when the App is offline.
        await peer.send(make_send_result(
            account_id=self.account_id,
            request_id=request_id,
            status="accepted" if self._native else "failed",
            error_code=None if self._native else "NATIVE_OFFLINE",
            error_message=None if self._native else "native adapter is offline",
        ))

    async def _run_command(self, key: Tuple[str, str], command: Dict[str, Any]) -> None:
        async def operation() -> None:
            request_id = str(command["request_id"])
            if self._native is None:
                result = make_send_result(
                    account_id=self.account_id,
                    request_id=request_id,
                    status="failed",
                    error_code="NATIVE_OFFLINE",
                    error_message="native adapter is offline",
                )
                await self._complete(request_id, result)
                return
            future: "asyncio.Future[Dict[str, Any]]" = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            self._pending_commands[request_id] = command
            try:
                await self._native.send(command)
                result = await asyncio.wait_for(future, timeout=self.command_timeout)
            except asyncio.TimeoutError:
                result = make_send_result(
                    account_id=self.account_id,
                    request_id=request_id,
                    status="timeout",
                    error_code="NATIVE_TIMEOUT",
                    error_message="native adapter did not confirm the command",
                )
            except (ConnectionError, OSError):
                result = make_send_result(
                    account_id=self.account_id,
                    request_id=request_id,
                    status="failed",
                    error_code="NATIVE_DISCONNECTED",
                    error_message="native adapter disconnected",
                )
            finally:
                self._pending.pop(request_id, None)
                self._pending_commands.pop(request_id, None)
            await self._complete(request_id, result)

        await self._serialiser.run(key, operation)

    async def _complete(self, request_id: str, result: Dict[str, Any]) -> None:
        await self._completed_requests.put(request_id, result)
        # The native callback may have already been broadcast; the result is
        # broadcast again with a stable terminal status for business clients.
        await self._broadcast(result)

    async def _resolve_result(self, event: Dict[str, Any]) -> None:
        request_id = str(event["request_id"])
        future = self._pending.get(request_id)
        if (
            future is not None
            and not future.done()
            and event.get("status") in {"sent", "failed", "timeout", "duplicate"}
        ):
            future.set_result(event)

    async def _forward_to_native(self, command: Dict[str, Any]) -> None:
        if self._native is None:
            return
        await self._native.send(command)

    def _session_key(self, command: Dict[str, Any]) -> Tuple[str, str]:
        session = str(
            command.get("app_cid")
            or command.get("sid")
            or command.get("peer_uid")
            or "unknown"
        )
        return self.account_id, session

    async def _broadcast(self, frame: Dict[str, Any]) -> None:
        dead = []
        for peer in list(self._business):
            try:
                await peer.send(frame)
            except (ConnectionError, OSError):
                dead.append(peer)
        for peer in dead:
            await self._remove_peer(peer)

    async def _broadcast_status(self, state: str) -> None:
        await self._broadcast(make_status(
            account_id=self.account_id,
            state=state,
            last_heartbeat_ms=self._last_heartbeat_ms,
            reconnect_count=self._reconnect_count,
        ))

    def _fail_pending(self, code: str, message: str) -> None:
        for request_id, future in list(self._pending.items()):
            if not future.done():
                future.set_result(make_send_result(
                    account_id=self.account_id,
                    request_id=request_id,
                    status="failed",
                    error_code=code,
                    error_message=message,
                ))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default="/tmp/xianyu_app_native/bridge.sock")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--command-timeout", type=float, default=30.0)
    return parser


async def _run(args: argparse.Namespace) -> None:
    server = NativeBridgeServer(
        args.socket,
        args.account_id,
        command_timeout=args.command_timeout,
    )
    await server.start()
    print("bridge listening on %s" % server.socket_path, flush=True)
    try:
        await server.serve_forever()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.stop()


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
