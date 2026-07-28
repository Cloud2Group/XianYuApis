"""Self-contained tests for the local JSONL bridge.

Run with:

    .venv/bin/python -m unittest xianyu_app.bridge.test_bridge -v
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

from .client import BusinessBridgeClient, NativeBridgeClient
from .protocol import make_message_received, make_send_result, make_status
from .server import NativeBridgeServer


async def _next_event(client: BusinessBridgeClient, event_name: str) -> Dict[str, Any]:
    async for event in client.events():
        if event.get("event") == event_name:
            return event
    raise AssertionError("bridge client closed")


class BridgeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.socket = str(Path(self.tempdir.name) / "bridge.sock")
        self.server = NativeBridgeServer(self.socket, "ACCOUNT")
        await self.server.start()
        self.native = NativeBridgeClient(self.socket, "ACCOUNT")
        self.business = BusinessBridgeClient(self.socket, "ACCOUNT")
        await self.native.connect()
        await self.business.connect()
        self.command_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self.command_pump = asyncio.create_task(self._pump_commands())
        # Consume the initial status frame so event assertions stay focused.
        await _next_event(self.business, "transport.status")

    async def _pump_commands(self) -> None:
        async for command in self.native.commands():
            await self.command_queue.put(command)

    async def asyncTearDown(self) -> None:
        await self.business.close()
        await self.native.close()
        self.command_pump.cancel()
        try:
            await self.command_pump
        except asyncio.CancelledError:
            pass
        await self.server.stop()
        self.tempdir.cleanup()

    async def test_inbound_event_is_broadcast_and_deduplicated(self) -> None:
        event = make_message_received(
            account_id="ACCOUNT",
            message_id="MID-1",
            sid="SID-1",
            app_cid="CID-1",
            peer_uid="BUYER-1",
            text="询价",
        )
        await self.native.send(event)
        received = await asyncio.wait_for(
            _next_event(self.business, "message.received"), timeout=1
        )
        self.assertEqual(received["message_id"], "MID-1")
        await self.native.send(event)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(
                _next_event(self.business, "message.received"), timeout=0.15
            )

    async def test_send_text_waits_for_native_terminal_result(self) -> None:
        result_task = asyncio.create_task(
            self.business.send_text(text="报价", app_cid="CID-1", timeout=2)
        )
        command = await asyncio.wait_for(self.command_queue.get(), timeout=1)
        self.assertEqual(command["action"], "send_text")
        self.assertEqual(command["text"], "报价")
        self.assertFalse(result_task.done())
        await self.native.send(make_send_result(
            account_id="ACCOUNT",
            request_id=command["request_id"],
            status="sent",
            message_id="MID-OUT-1",
        ))
        result = await asyncio.wait_for(result_task, timeout=1)
        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["message_id"], "MID-OUT-1")

    async def test_same_session_is_serialised(self) -> None:
        first = asyncio.create_task(
            self.business.send_text(text="一", app_cid="CID-serial", timeout=2)
        )
        first_command = await asyncio.wait_for(self.command_queue.get(), timeout=1)
        second = asyncio.create_task(
            self.business.send_text(text="二", app_cid="CID-serial", timeout=2)
        )
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(self.command_queue.get(), timeout=0.15)
        await self.native.send(make_send_result(
            account_id="ACCOUNT",
            request_id=first_command["request_id"],
            status="sent",
            message_id="OUT-1",
        ))
        second_command = await asyncio.wait_for(self.command_queue.get(), timeout=1)
        self.assertEqual(second_command["text"], "二")
        await self.native.send(make_send_result(
            account_id="ACCOUNT",
            request_id=second_command["request_id"],
            status="sent",
            message_id="OUT-2",
        ))
        self.assertEqual((await first)["message_id"], "OUT-1")
        self.assertEqual((await second)["message_id"], "OUT-2")

    async def test_native_disconnect_reports_reconnecting(self) -> None:
        await self.native.close()
        status = await asyncio.wait_for(
            _next_event(self.business, "transport.status"), timeout=1
        )
        self.assertEqual(status["state"], "reconnecting")

    async def test_offline_send_fails(self) -> None:
        await self.native.close()
        # Drain the status event generated by disconnect.
        await _next_event(self.business, "transport.status")
        result = await self.business.send_text(text="测试", app_cid="CID-offline", timeout=1)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "NATIVE_OFFLINE")


if __name__ == "__main__":
    unittest.main()
