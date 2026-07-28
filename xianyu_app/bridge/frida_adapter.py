"""Connect the Frida AIM probe to the local Unix bridge.

This module is the temporary App-side adapter for Milestone 1.  A future
signed helper can replace it while keeping the same JSONL contract.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .client import NativeBridgeClient
from .protocol import ProtocolError, safe_log_frame, validate_event
from .server import NativeBridgeServer


class FridaNativeAdapter:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server: Optional[NativeBridgeServer] = None
        self.native: Optional[NativeBridgeClient] = None
        self.device: Any = None
        self.session: Any = None
        self.script: Any = None
        self.spawned_pid: Optional[int] = None
        self._messages: "asyncio.Queue[Tuple[Dict[str, Any], Optional[bytes]]]" = asyncio.Queue()
        self._tasks: list[asyncio.Task[Any]] = []
        self._stop = asyncio.Event()
        self._observation_file = None

    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        if not self.args.connect_existing:
            self.server = NativeBridgeServer(
                self.args.socket,
                self.args.account_id,
                command_timeout=self.args.command_timeout,
            )
            await self.server.start()

        self.native = NativeBridgeClient(self.args.socket, self.args.account_id)
        await self.native.connect()

        if self.args.observation_log:
            path = Path(self.args.observation_log).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._observation_file = path.open("a", encoding="utf-8")

        try:
            import frida  # type: ignore
        except ImportError as exc:
            raise RuntimeError("install the optional frida Python package") from exc

        self.device = frida.get_local_device()
        if self.args.pid is not None:
            self.session = self.device.attach(int(self.args.pid))
        elif self.args.name:
            self.session = self.device.attach(self.args.name)
        else:
            target = str(Path(self.args.spawn).expanduser())
            self.spawned_pid = int(self.device.spawn([target]))
            self.session = self.device.attach(self.spawned_pid)

        self.session.on("detached", self._on_detached)
        source = Path(self.args.script).read_text(encoding="utf-8")
        self.script = self.session.create_script(source)
        self.script.on("message", self._on_message)
        self.script.load()
        self._configure_script()
        if self.spawned_pid is not None:
            self.device.resume(self.spawned_pid)

        self._tasks = [
            asyncio.create_task(self._process_script_messages()),
            asyncio.create_task(self._forward_commands()),
        ]

    def _configure_script(self) -> None:
        patch = {
            "accountId": self.args.account_id,
            "captureText": bool(self.args.capture_text),
            "registerListener": bool(self.args.register_listener),
            "invokeEnabled": bool(self.args.invoke_enabled),
            "contentTypeText": int(self.args.content_type_text),
        }
        try:
            exports = self.script.exports_sync
            state = exports.configure(patch)
            if self.args.verbose:
                self._log("script.configured", state)
        except Exception as exc:
            self._log("script.configure_error", {"error": str(exc)})

    def _on_message(self, message: Dict[str, Any], data: Optional[bytes]) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._messages.put_nowait, (message, data))

    def _on_detached(self, reason: Any, crash: Any = None) -> None:
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(
            self._log,
            "session.detached",
            {"reason": str(reason), "crash": str(crash) if crash else None},
        )
        self.loop.call_soon_threadsafe(self._stop.set)

    async def _process_script_messages(self) -> None:
        assert self.native is not None
        while not self._stop.is_set():
            message, data = await self._messages.get()
            kind = message.get("type")
            if kind == "send":
                payload = message.get("payload")
                if not isinstance(payload, dict):
                    self._log("script.payload", {"payload_type": type(payload).__name__})
                    continue
                payload_kind = payload.get("kind")
                if payload_kind == "native.event":
                    frame = payload.get("frame")
                    if not isinstance(frame, dict):
                        self._log("script.bad_event", {"reason": "event frame is not an object"})
                        continue
                    try:
                        validate_event(frame)
                    except ProtocolError as exc:
                        self._log("script.bad_event", {"error": str(exc), "frame": frame})
                        continue
                    await self.native.send(frame)
                elif payload_kind == "native.observation":
                    self._log("native.observation", payload.get("observation") or {})
                elif self.args.verbose:
                    self._log("script.send", payload)
            elif kind == "error":
                self._log("script.error", {
                    "description": message.get("description"),
                    "stack": message.get("stack"),
                    "fileName": message.get("fileName"),
                    "lineNumber": message.get("lineNumber"),
                })
            elif self.args.verbose:
                self._log("script.message", message)

    async def _forward_commands(self) -> None:
        assert self.native is not None
        async for command in self.native.commands():
            if self.script is None:
                break
            try:
                self.script.post({"type": "native.command", "payload": command})
            except Exception as exc:
                self._log("script.post_error", {
                    "error": str(exc),
                    "request_id": command.get("request_id"),
                })

    def _log(self, event: str, payload: Any) -> None:
        frame = safe_log_frame({
            "event": event,
            "payload": payload,
        })
        line = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
        if self.args.verbose or event in {
            "script.error",
            "script.configure_error",
            "script.bad_event",
            "session.detached",
        }:
            print(line, file=sys.stderr, flush=True)
        if self._observation_file is not None:
            self._observation_file.write(line + "\n")
            self._observation_file.flush()

    async def wait(self) -> None:
        if self.args.run_seconds > 0:
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.args.run_seconds)
            except asyncio.TimeoutError:
                return
        else:
            await self._stop.wait()

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self.script is not None:
            try:
                self.script.unload()
            except Exception:
                pass
            self.script = None
        if self.session is not None:
            try:
                self.session.detach()
            except Exception:
                pass
            self.session = None
        if self.spawned_pid is not None and self.args.kill_on_exit:
            try:
                self.device.kill(self.spawned_pid)
            except Exception:
                pass
        self.spawned_pid = None
        if self.native is not None:
            await self.native.close()
            self.native = None
        if self.server is not None:
            await self.server.stop()
            self.server = None
        if self._observation_file is not None:
            self._observation_file.close()
            self._observation_file = None


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--pid", type=int)
    target.add_argument("--name")
    target.add_argument("--spawn", metavar="EXECUTABLE")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--socket", default="/tmp/xianyu_app_native/bridge.sock")
    parser.add_argument(
        "--script",
        default=str(root / "hooks" / "native_aim_bridge.js"),
    )
    parser.add_argument("--connect-existing", action="store_true")
    parser.add_argument("--capture-text", action="store_true")
    parser.add_argument("--register-listener", action="store_true")
    parser.add_argument("--invoke-enabled", action="store_true")
    parser.add_argument("--content-type-text", type=int, default=1)
    parser.add_argument("--command-timeout", type=float, default=30.0)
    parser.add_argument("--run-seconds", type=float, default=0.0)
    parser.add_argument("--kill-on-exit", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--observation-log",
        default=str(root / "research" / "runtime" / "frida_observations.jsonl"),
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    adapter = FridaNativeAdapter(args)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, adapter._stop.set)
        except NotImplementedError:
            pass
    try:
        await adapter.start()
        print("native adapter connected: %s" % args.socket, flush=True)
        await adapter.wait()
        return 0
    finally:
        await adapter.stop()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print("native adapter error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
