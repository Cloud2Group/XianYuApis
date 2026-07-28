from __future__ import annotations

import argparse
import asyncio
import base64
import inspect
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from loguru import logger
import requests
import websockets

from xianyu_web.goofish_apis import XianyuApis, qrcode_login
from xianyu_web.paths import AUTH_FILE, COOKIE_FILE, EXPORTS_DIR
from xianyu_web.utils.goofish_utils import (
    generate_device_id,
    generate_mid,
    get_session_cookies_str,
    trans_cookies,
)


MAX_SAFE_CURSOR = 9007199254740991
GOOFISH_DOMAIN = "goofish"
DEFAULT_OUTPUT_ROOT = str(EXPORTS_DIR)
DEFAULT_COOKIE_FILE = str(COOKIE_FILE)
DEFAULT_AUTH_FILE = str(AUTH_FILE)
DEFAULT_VALIDATE_FILE = str(EXPORTS_DIR / "runtime" / "xianyu_validate.html")
DEFAULT_REQUEST_DELAY = 3.0
FLOW_CONTROL_CODE = "400600001"

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = None


def _strip_domain(value: Any) -> str:
    text = str(value or "")
    return text.split("@", 1)[0] if "@" in text else text


def _with_domain(value: Any) -> str:
    text = str(value or "")
    return text if "@" in text else f"{text}@{GOOFISH_DOMAIN}"


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _deep_get(data: Dict[str, Any], path: Iterable[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _format_time(timestamp_ms: Any) -> str:
    timestamp = _as_int(timestamp_ms)
    if timestamp <= 0:
        return ""
    dt = datetime.fromtimestamp(timestamp / 1000)
    if LOCAL_TZ:
        dt = dt.astimezone(LOCAL_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _current_year() -> int:
    now = datetime.now(LOCAL_TZ) if LOCAL_TZ else datetime.now()
    return now.year


def _year_bounds_ms(year: int) -> Tuple[int, int]:
    start = datetime(year, 1, 1, tzinfo=LOCAL_TZ)
    end = datetime(year + 1, 1, 1, tzinfo=LOCAL_TZ)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _in_time_range(timestamp_ms: Any, start_ms: int = 0, end_ms: int = 0) -> bool:
    timestamp = _as_int(timestamp_ms)
    if timestamp <= 0:
        return not start_ms and not end_ms
    if start_ms and timestamp < start_ms:
        return False
    if end_ms and timestamp >= end_ms:
        return False
    return True


def _open_path_or_url(target: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["open", target],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            import webbrowser

            webbrowser.open(target)
    except Exception as exc:
        logger.warning(f"自动打开失败，请手动打开：{target}；{exc}")


def _write_validate_page(validate_url: str) -> Path:
    output_path = Path(DEFAULT_VALIDATE_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_url = validate_url.replace("&", "&amp;").replace('"', "&quot;")
    output_path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0; url={escaped_url}">
  <title>闲鱼安全校验</title>
</head>
<body>
  <p>正在打开闲鱼安全校验页。若没有跳转，请点击：
    <a href="{escaped_url}">{escaped_url}</a>
  </p>
</body>
</html>
""",
        encoding="utf-8",
    )
    return output_path


def _extract_validate_url(data: Dict[str, Any]) -> str:
    if not isinstance(data, dict):
        return ""
    ret = " ".join(str(item) for item in data.get("ret", []))
    url = _first_text((data.get("data") or {}).get("url"))
    if "FAIL_SYS_USER_VALIDATE" in ret or "punish" in url or "captcha" in url:
        return url
    return ""


def _safe_filename(value: str, default: str) -> str:
    name = _first_text(value, default)
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._")
    return (name or default)[:100]


def _json_preview(value: Any) -> str:
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_custom_payload(data: Any) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not data:
        return None, None

    try:
        if isinstance(data, bytes):
            raw = data
        else:
            raw = str(data).encode("utf-8")
        decoded = base64.b64decode(raw).decode("utf-8")
        payload = json.loads(decoded)
        if isinstance(payload, dict):
            return payload, None
        return {"value": payload}, None
    except Exception as exc:
        return None, str(exc)


def _extract_payload_summary(payload: Optional[Dict[str, Any]]) -> Tuple[str, str]:
    if not payload:
        return "", ""

    content_type = payload.get("contentType")
    if content_type == 1:
        text = _first_text(
            _deep_get(payload, ["text", "text"]),
            _deep_get(payload, ["text", "content"]),
            payload.get("text"),
        )
        return "text", text

    if content_type == 2:
        pics = _deep_get(payload, ["image", "pics"]) or []
        urls = []
        if isinstance(pics, list):
            for pic in pics:
                if isinstance(pic, dict):
                    url = _first_text(pic.get("url"), pic.get("mediaId"))
                    if url:
                        urls.append(url)
        return "image", "\n".join(f"[图片] {url}" for url in urls) or "[图片]"

    dx_card = payload.get("dxCard")
    if isinstance(dx_card, dict):
        title = _first_text(
            _deep_get(dx_card, ["item", "main", "exContent", "title"]),
            dx_card.get("title"),
            _deep_get(dx_card, ["item", "title"]),
        )
        desc = _first_text(
            _deep_get(dx_card, ["item", "main", "exContent", "desc"]),
            dx_card.get("desc"),
            _deep_get(dx_card, ["item", "desc"]),
        )
        target_url = _first_text(
            _deep_get(dx_card, ["item", "targetUrl"]),
            _deep_get(dx_card, ["item", "main", "targetUrl"]),
            dx_card.get("targetUrl"),
        )
        parts = [part for part in [title, desc, target_url] if part]
        return "card", " | ".join(parts) or "[卡片消息]"

    for key in ("text", "title", "summary", "desc", "content"):
        text = payload.get(key)
        if isinstance(text, str) and text.strip():
            return "custom", text.strip()
        if isinstance(text, dict):
            nested = _first_text(text.get("text"), text.get("content"), text.get("title"))
            if nested:
                return "custom", nested

    return f"custom:{content_type}" if content_type is not None else "custom", _json_preview(payload)


def normalize_user_message(
    user_message: Dict[str, Any],
    my_user_id: str,
    include_raw: bool,
) -> Dict[str, Any]:
    message = user_message.get("message") or {}
    content = message.get("content") or {}
    extension = message.get("extension") or {}
    custom = content.get("custom") or {}
    custom_payload, decode_error = _decode_custom_payload(custom.get("data"))

    sender_id = _strip_domain(
        _first_text(
            extension.get("senderUserId"),
            _deep_get(message, ["sender", "uid"]),
        )
    )
    is_me = bool(sender_id and sender_id == my_user_id)
    sender_name = _first_text(
        extension.get("senderUserNick"),
        extension.get("senderNick"),
        extension.get("reminderTitle"),
        "我" if is_me else sender_id,
    )

    message_type, text = _extract_payload_summary(custom_payload)
    if not text:
        text = _first_text(
            _deep_get(content, ["text", "content"]),
            _deep_get(content, ["text", "text"]),
            custom.get("title"),
            custom.get("summary"),
            custom.get("degrade"),
            extension.get("reminderContent"),
        )
    if not message_type:
        content_type = content.get("contentType")
        message_type = "custom" if content_type == 101 else f"content:{content_type}"

    normalized = {
        "message_id": _first_text(message.get("messageId"), message.get("uuid")),
        "cid": _strip_domain(message.get("cid")),
        "created_at_ms": _as_int(message.get("createAt")),
        "created_at": _format_time(message.get("createAt")),
        "direction": "out" if is_me else "in",
        "sender_id": sender_id,
        "sender_name": sender_name,
        "type": message_type,
        "text": text or "[无法解析的消息]",
        "content_type": content.get("contentType"),
        "custom_type": custom.get("type"),
        "read_status": user_message.get("readStatus"),
        "message_status": user_message.get("msgStatus"),
        "decode_error": decode_error,
        "custom_payload": custom_payload,
    }
    if include_raw:
        normalized["raw"] = user_message
    return normalized


def normalize_conversation(
    conversation: Dict[str, Any],
    my_user_id: str,
    include_raw: bool,
) -> Dict[str, Any]:
    single = conversation.get("singleChatUserConversation") or {}
    group = conversation.get("groupChatUserConversation") or {}
    wrapper = single or group
    chat = (
        wrapper.get("singleChatConversation")
        or wrapper.get("groupChatConversation")
        or {}
    )
    conversation_type = "single" if single else "group" if group else "unknown"
    cid = _strip_domain(chat.get("cid") or wrapper.get("cid"))

    pair_first = _strip_domain(chat.get("pairFirst"))
    pair_second = _strip_domain(chat.get("pairSecond"))
    peer_user_id = ""
    if conversation_type == "single":
        peer_user_id = pair_second if pair_first == my_user_id else pair_first

    last_message = None
    if isinstance(wrapper.get("lastMessage"), dict):
        last_message = normalize_user_message(wrapper["lastMessage"], my_user_id, False)

    chat_ext = chat.get("extension") or {}
    user_ext = wrapper.get("userExtension") or wrapper.get("user_extension") or {}
    title = _first_text(
        user_ext.get("peerNick"),
        user_ext.get("nick"),
        chat_ext.get("peerNick"),
        chat_ext.get("title"),
        last_message.get("sender_name") if last_message else "",
        peer_user_id,
        cid,
    )
    item_id = _first_text(chat_ext.get("itemId"), user_ext.get("itemId"))
    owner_user_id = _strip_domain(_first_text(chat_ext.get("ownerUserId"), user_ext.get("ownerUserId")))
    related_user_id = _strip_domain(_first_text(chat_ext.get("extUserId"), user_ext.get("extUserId")))

    normalized = {
        "cid": cid,
        "type": conversation_type,
        "title": title,
        "peer_user_id": peer_user_id,
        "item_id": item_id,
        "owner_user_id": owner_user_id,
        "related_user_id": related_user_id,
        "is_my_item": bool(owner_user_id and owner_user_id == my_user_id),
        "visible": wrapper.get("visible"),
        "unread_count": wrapper.get("redPoint"),
        "joined_at_ms": _as_int(wrapper.get("joinTime")),
        "joined_at": _format_time(wrapper.get("joinTime")),
        "modified_at_ms": _as_int(wrapper.get("modifyTime")),
        "modified_at": _format_time(wrapper.get("modifyTime")),
        "last_message": last_message,
    }
    if include_raw:
        normalized["raw"] = conversation
    return normalized


def _websocket_headers(api: XianyuApis) -> Dict[str, str]:
    return {
        "Cookie": get_session_cookies_str(api.session),
        "Host": "wss-goofish.dingtalk.com",
        "Connection": "Upgrade",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        ),
        "Origin": "https://www.goofish.com",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }


def _connect_websocket(url: str, headers: Dict[str, str]) -> Any:
    params = inspect.signature(websockets.connect).parameters
    if "extra_headers" in params:
        return websockets.connect(url, extra_headers=headers)
    return websockets.connect(url, additional_headers=headers)


class XianyuRpcClient:
    def __init__(
        self,
        api: XianyuApis,
        device_id: str,
        timeout: float = 30.0,
        request_delay: float = DEFAULT_REQUEST_DELAY,
    ):
        self.api = api
        self.device_id = device_id
        self.timeout = timeout
        self.request_delay = max(0.0, request_delay)
        self.base_url = "wss://wss-goofish.dingtalk.com/"
        self.ws = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._ready = asyncio.Event()
        self._receiver_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._recent_messages: List[Dict[str, Any]] = []
        self._last_request_at = 0.0

    async def __aenter__(self) -> "XianyuRpcClient":
        self.ws = await _connect_websocket(self.base_url, _websocket_headers(self.api))
        self._receiver_task = asyncio.create_task(self._receive_loop())
        await self._init_session()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        for task in (self._heartbeat_task, self._receiver_task):
            if task:
                task.cancel()
        for task in (self._heartbeat_task, self._receiver_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self.ws:
            await self.ws.close()

    async def _init_session(self) -> None:
        data = self.api.get_token()
        validate_url = _extract_validate_url(data)
        if validate_url:
            validate_page = _write_validate_page(validate_url)
            logger.warning(f"闲鱼要求安全校验，已打开校验页：{validate_page}")
            _open_path_or_url(str(validate_page.resolve()))
            deadline = datetime.now().timestamp() + 120
            while datetime.now().timestamp() < deadline:
                await asyncio.sleep(5)
                data = self.api.get_token()
                if not _extract_validate_url(data):
                    break

        token = data.get("data", {}).get("accessToken") if isinstance(data, dict) else ""
        if not token:
            raise RuntimeError(f"获取闲鱼 IM token 失败：{data}")

        reg_response = await self.request(
            "/reg",
            None,
            headers={
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": token,
                "ua": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 "
                    "DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) "
                    "DingWeb/2.1.5 IMPaaS DingWeb/2.1.5"
                ),
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "set-ver": "",
                "reg-type": "",
            },
        )
        logger.info(f"WebSocket 登录完成：{reg_response.get('headers', {}).get('sid', '')}")
        current_time = int(datetime.now().timestamp() * 1000)
        await self._send(
            {
                "lwp": "/r/SyncStatus/ackDiff",
                "headers": {"mid": generate_mid()},
                "body": [
                    {
                        "pipeline": "sync",
                        "tooLong2Tag": "PNM,1",
                        "channel": "sync",
                        "topic": "sync",
                        "highPts": 0,
                        "pts": current_time * 1000,
                        "seq": 0,
                        "timestamp": current_time,
                    }
                ],
            }
        )

    async def _send(self, payload: Dict[str, Any]) -> None:
        if not self.ws:
            raise RuntimeError("WebSocket 尚未连接")
        await self.ws.send(json.dumps(payload, ensure_ascii=False))

    async def _send_ack(self, message: Dict[str, Any]) -> None:
        headers = message.get("headers") or {}
        if not headers:
            return
        ack_headers = {
            "mid": headers.get("mid") or generate_mid(),
            "sid": headers.get("sid") or "",
        }
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack_headers[key] = headers[key]
        await self._send({"code": 200, "headers": ack_headers})

    async def _receive_loop(self) -> None:
        assert self.ws is not None
        async for raw_message in self.ws:
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.debug(f"跳过非 JSON WebSocket 消息：{raw_message}")
                continue
            self._recent_messages.append(message)
            self._recent_messages = self._recent_messages[-20:]

            try:
                await self._send_ack(message)
            except Exception as exc:
                logger.debug(f"发送 ACK 失败：{exc}")

            if message.get("lwp") == "/s/vulcan":
                self._ready.set()

            mid = str((message.get("headers") or {}).get("mid") or "")
            if mid and mid in self._pending:
                future = self._pending[mid]
                if not future.done():
                    future.set_result(message)

    async def _heartbeat_loop(self) -> None:
        while True:
            await self._send({"lwp": "/!", "headers": {"mid": generate_mid()}})
            await asyncio.sleep(15)

    async def _wait_before_request(self, lwp: str) -> None:
        if lwp in {"/reg", "/!"} or self.request_delay <= 0:
            return
        now = datetime.now().timestamp()
        elapsed = now - self._last_request_at
        if elapsed < self.request_delay:
            await asyncio.sleep(self.request_delay - elapsed)
        self._last_request_at = datetime.now().timestamp()

    @staticmethod
    def _is_flow_control(response: Dict[str, Any]) -> bool:
        body = response.get("body") or {}
        return response.get("code") == 400 and str(body.get("code")) == FLOW_CONTROL_CODE

    @staticmethod
    def _response_summary(response: Dict[str, Any]) -> Dict[str, Any]:
        body = response.get("body") or {}
        return {
            "code": response.get("code"),
            "headers": response.get("headers"),
            "body_code": body.get("code") if isinstance(body, dict) else None,
            "reason": body.get("reason") if isinstance(body, dict) else None,
            "scope": body.get("scope") if isinstance(body, dict) else None,
            "body_keys": list(body.keys()) if isinstance(body, dict) else [],
        }

    async def request(
        self,
        lwp: str,
        body: Optional[List[Any]],
        headers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        last_response: Optional[Dict[str, Any]] = None
        for attempt in range(1, 6):
            await self._wait_before_request(lwp)
            mid = generate_mid()
            request_headers = dict(headers or {})
            request_headers["mid"] = mid
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._pending[mid] = future
            try:
                payload = {"lwp": lwp, "headers": request_headers}
                if body is not None:
                    payload["body"] = body
                await self._send(payload)
                response = await asyncio.wait_for(future, timeout=self.timeout)
            finally:
                self._pending.pop(mid, None)

            if response.get("code") == 200:
                return response

            last_response = response
            if self._is_flow_control(response) and attempt < 5:
                wait_seconds = min(30, 3 * attempt)
                logger.warning(f"闲鱼 IM 接口触发限流，{wait_seconds}s 后重试：{lwp}")
                await asyncio.sleep(wait_seconds)
                continue
            break

        raise RuntimeError(
            f"接口 {lwp} 返回异常：{self._response_summary(last_response or {})}"
        )


class ChatExporter:
    def __init__(
        self,
        api: XianyuApis,
        my_user_id: str,
        device_id: str,
        include_raw: bool,
        timeout: float,
        request_delay: float,
        only_my_items: bool,
        start_ms: int,
        end_ms: int,
        checkpoint_writer: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.api = api
        self.my_user_id = my_user_id
        self.device_id = device_id
        self.include_raw = include_raw
        self.timeout = timeout
        self.request_delay = request_delay
        self.only_my_items = only_my_items
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.checkpoint_writer = checkpoint_writer

    def _build_export_data(self, conversations: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "exported_at": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S") if LOCAL_TZ else datetime.now().isoformat(timespec="seconds"),
            "account": {"user_id": self.my_user_id},
            "conversation_count": len(conversations),
            "message_count": sum(item.get("message_count", 0) for item in conversations),
            "conversations": conversations,
        }

    def _write_checkpoint(self, conversations: List[Dict[str, Any]]) -> None:
        if not self.checkpoint_writer:
            return
        self.checkpoint_writer(self._build_export_data(conversations))

    async def export(
        self,
        cids: List[str],
        list_only: bool,
        page_size: int,
        message_page_size: int,
        max_conversations: int,
        max_messages_per_conversation: int,
        oldest_first: bool,
        resume_conversations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        async with XianyuRpcClient(
            self.api,
            self.device_id,
            self.timeout,
            self.request_delay,
        ) as rpc:
            conversations = (
                resume_conversations
                if resume_conversations is not None
                else (
                    await self._list_selected_conversations(cids)
                    if cids
                    else await self._list_conversations(rpc, page_size, max_conversations)
                )
            )
            if resume_conversations is None:
                conversations = self._filter_conversations(conversations)
            self._write_checkpoint(conversations)

            if not list_only:
                for index, conversation in enumerate(conversations, 1):
                    if resume_conversations is not None and "messages" in conversation:
                        continue
                    cid = conversation["cid"]
                    logger.info(f"开始导出会话 {index}/{len(conversations)}：{conversation['title']} ({cid})")

                    def on_message_page(messages: List[Dict[str, Any]]) -> None:
                        conversation["messages"] = self._sort_messages(messages, oldest_first)
                        conversation["message_count"] = len(messages)
                        self._write_checkpoint(conversations)
                        logger.info(f"已保存进度：会话 {index}/{len(conversations)}，当前 {len(messages)} 条消息")

                    messages = await self._list_messages(
                        rpc,
                        cid,
                        message_page_size,
                        max_messages_per_conversation,
                        oldest_first,
                        on_message_page,
                    )
                    conversation["messages"] = messages
                    conversation["message_count"] = len(messages)
                    self._write_checkpoint(conversations)
                    logger.info(f"完成会话 {index}/{len(conversations)}：{len(messages)} 条消息")
            else:
                for conversation in conversations:
                    conversation["messages"] = []
                    conversation["message_count"] = 0
                self._write_checkpoint(conversations)

        return self._build_export_data(conversations)

    def _filter_conversations(self, conversations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered = []
        for conversation in conversations:
            if self.only_my_items and not conversation.get("is_my_item"):
                continue
            if (self.start_ms or self.end_ms) and not _in_time_range(conversation.get("modified_at_ms"), self.start_ms, self.end_ms):
                continue
            filtered.append(conversation)
        return filtered

    async def _list_selected_conversations(self, cids: List[str]) -> List[Dict[str, Any]]:
        conversations = []
        for cid in cids:
            conversations.append(
                {
                    "cid": _strip_domain(cid),
                    "type": "unknown",
                    "title": _strip_domain(cid),
                    "peer_user_id": "",
                    "item_id": "",
                    "owner_user_id": "",
                    "related_user_id": "",
                    "is_my_item": False,
                    "visible": None,
                    "unread_count": None,
                    "joined_at_ms": 0,
                    "joined_at": "",
                    "modified_at_ms": 0,
                    "modified_at": "",
                    "last_message": None,
                }
            )
        return conversations

    async def _list_conversations(
        self,
        rpc: XianyuRpcClient,
        page_size: int,
        max_conversations: int,
    ) -> List[Dict[str, Any]]:
        cursor = MAX_SAFE_CURSOR
        conversations: List[Dict[str, Any]] = []
        seen_cids = set()

        while True:
            response = await rpc.request("/r/Conversation/listNewestPagination", [cursor, page_size])
            body = response.get("body") or {}
            raw_conversations = body.get("userConvs") or []
            for raw in raw_conversations:
                if not isinstance(raw, dict):
                    continue
                conversation = normalize_conversation(raw, self.my_user_id, self.include_raw)
                cid = conversation.get("cid")
                if not cid or cid in seen_cids:
                    continue
                seen_cids.add(cid)
                conversations.append(conversation)
                if max_conversations and len(conversations) >= max_conversations:
                    self._write_checkpoint(conversations)
                    return conversations

            self._write_checkpoint(conversations)
            logger.info(f"已读取会话列表：{len(conversations)} 个")
            if not _as_bool(body.get("hasMore")):
                break
            next_cursor = body.get("nextCursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return conversations

    async def _list_messages(
        self,
        rpc: XianyuRpcClient,
        cid: str,
        page_size: int,
        max_messages: int,
        oldest_first: bool,
        on_page: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
    ) -> List[Dict[str, Any]]:
        cursor = MAX_SAFE_CURSOR
        messages: List[Dict[str, Any]] = []
        seen = set()

        while True:
            response = await rpc.request(
                "/r/MessageManager/listUserMessages",
                [_with_domain(cid), False, cursor, page_size, False],
            )
            body = response.get("body") or {}
            raw_messages = body.get("userMessageModels") or []
            raw_timestamps = []
            for raw in raw_messages:
                if not isinstance(raw, dict):
                    continue
                message = normalize_user_message(raw, self.my_user_id, self.include_raw)
                raw_timestamps.append(message.get("created_at_ms") or 0)
                if (self.start_ms or self.end_ms) and not _in_time_range(message.get("created_at_ms"), self.start_ms, self.end_ms):
                    continue
                key = _first_text(
                    message.get("message_id"),
                    f"{message.get('created_at_ms')}|{message.get('sender_id')}|{message.get('text')}",
                )
                if key in seen:
                    continue
                seen.add(key)
                messages.append(message)
                if max_messages and len(messages) >= max_messages:
                    if on_page:
                        on_page(messages)
                    return self._sort_messages(messages, oldest_first)

            if on_page:
                on_page(messages)
            if self.start_ms and raw_timestamps and max(raw_timestamps) < self.start_ms:
                break
            if not _as_bool(body.get("hasMore")):
                break
            next_cursor = body.get("nextCursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor

        return self._sort_messages(messages, oldest_first)

    @staticmethod
    def _sort_messages(messages: List[Dict[str, Any]], oldest_first: bool) -> List[Dict[str, Any]]:
        return sorted(
            messages,
            key=lambda item: (item.get("created_at_ms") or 0, item.get("message_id") or ""),
            reverse=not oldest_first,
        )


def write_json(export_data: Dict[str, Any], output_dir: Path) -> Path:
    output_path = output_dir / "xianyu_chats.json"
    output_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def write_checkpoint(export_data: Dict[str, Any], output_dir: Path) -> Path:
    output_path = output_dir / "xianyu_chats.partial.json"
    tmp_path = output_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)
    return output_path


def _markdown_text(text: Any) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return value.strip() or "[空消息]"


def write_markdown(export_data: Dict[str, Any], output_dir: Path) -> Tuple[Path, Path]:
    conversations_dir = output_dir / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# 闲鱼聊天记录导出",
        "",
        f"- 导出时间：{export_data.get('exported_at')}",
        f"- 账号 ID：{export_data.get('account', {}).get('user_id')}",
        f"- 会话数：{export_data.get('conversation_count')}",
        f"- 消息数：{export_data.get('message_count')}",
        "",
        "## 会话列表",
        "",
    ]

    for index, conversation in enumerate(export_data.get("conversations") or [], 1):
        cid = conversation.get("cid") or f"conversation_{index}"
        title = conversation.get("title") or cid
        filename = f"{index:04d}_{_safe_filename(title, cid)}_{_safe_filename(cid, str(index))}.md"
        transcript_path = conversations_dir / filename
        relative_path = transcript_path.relative_to(output_dir)
        index_lines.append(
            f"- [{title}]({relative_path.as_posix()})：{conversation.get('message_count', 0)} 条消息，CID `{cid}`"
        )

        transcript_lines = [
            f"# {title}",
            "",
            f"- 会话 ID：`{cid}`",
            f"- 对方用户 ID：`{conversation.get('peer_user_id') or ''}`",
            f"- 商品 ID：`{conversation.get('item_id') or ''}`",
            f"- 消息数：{conversation.get('message_count', 0)}",
            "",
            "## 消息",
            "",
        ]
        for message in conversation.get("messages") or []:
            sender = "我" if message.get("direction") == "out" else (message.get("sender_name") or message.get("sender_id") or "对方")
            created_at = message.get("created_at") or "未知时间"
            message_type = message.get("type") or "unknown"
            transcript_lines.extend(
                [
                    f"### {created_at} · {sender} · {message_type}",
                    "",
                    _markdown_text(message.get("text")),
                    "",
                ]
            )

        transcript_path.write_text("\n".join(transcript_lines), encoding="utf-8")

    index_path = output_dir / "index.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    return index_path, conversations_dir


def parse_cids(values: List[str]) -> List[str]:
    cids: List[str] = []
    for value in values:
        for part in value.split(","):
            cid = _strip_domain(part.strip())
            if cid:
                cids.append(cid)
    return cids


def parse_year_filter(args: argparse.Namespace) -> Tuple[int, int, str]:
    year = _current_year() if args.this_year else args.year
    if not year:
        return 0, 0, ""
    start_ms, end_ms = _year_bounds_ms(year)
    return start_ms, end_ms, f"{year} 年"


def load_cookie(args: argparse.Namespace) -> str:
    if args.cookie:
        return args.cookie.strip()
    cookie_file = Path(args.cookie_file or DEFAULT_COOKIE_FILE).expanduser()
    if cookie_file.exists() and not args.qrcode:
        return cookie_file.read_text(encoding="utf-8").strip()
    return os.getenv("XIANYU_COOKIE", "").strip() or os.getenv("GOOFISH_COOKIE", "").strip()


def load_saved_auth(args: argparse.Namespace) -> Dict[str, Any]:
    auth_file = Path(args.auth_file).expanduser()
    if args.qrcode or not auth_file.exists():
        return {}
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_api(args: argparse.Namespace) -> Tuple[XianyuApis, str, str]:
    cookie = load_cookie(args)
    if args.qrcode or not cookie:
        try:
            api = qrcode_login(
                show_qrcode=not args.no_qrcode_image,
                qrcode_output_path=args.qrcode_file,
                open_qrcode=not args.no_open_qrcode,
            )
        except requests.RequestException as exc:
            raise RuntimeError(
                "扫码登录请求超时或连接失败。先确认能在浏览器打开 https://www.goofish.com；"
                "如果当前网络访问淘宝/闲鱼较慢，换网络或代理后重试。"
            ) from exc
        my_user_id = _strip_domain(api.session.cookies.get("unb") or api.session.cookies.get_dict().get("unb"))
        if not my_user_id:
            raise RuntimeError("扫码登录成功后没有拿到 unb，无法确认账号 ID")
        device_id = api.device_id
        args.used_qrcode_login = True
        return api, my_user_id, device_id

    cookies = trans_cookies(cookie)
    my_user_id = _strip_domain(cookies.get("unb"))
    if not my_user_id:
        raise RuntimeError("Cookie 里缺少 unb，请确认复制的是登录后的完整 Cookie")
    saved_auth = load_saved_auth(args)
    saved_user_id = _strip_domain(saved_auth.get("user_id"))
    if saved_user_id and saved_user_id != my_user_id:
        logger.info("本地设备信息属于其他账号，已为当前 Cookie 生成新的设备标识\n")
        saved_auth = {}
    device_id = _first_text(saved_auth.get("device_id"), generate_device_id(my_user_id))
    return XianyuApis(cookies, device_id), my_user_id, device_id


def save_cookie_if_needed(api: XianyuApis, cookie_file: Optional[str]) -> Optional[Path]:
    if not cookie_file:
        return None
    output = Path(cookie_file).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(get_session_cookies_str(api.session), encoding="utf-8")
    try:
        output.chmod(0o600)
    except OSError:
        pass
    return output


def save_auth_if_needed(api: XianyuApis, my_user_id: str, auth_file: Optional[str]) -> Optional[Path]:
    if not auth_file:
        return None
    output = Path(auth_file).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "user_id": my_user_id,
                "device_id": api.device_id,
                "saved_at": datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
                if LOCAL_TZ
                else datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    try:
        output.chmod(0o600)
    except OSError:
        pass
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出自己的闲鱼聊天记录")
    parser.add_argument("--cookie", help="登录后的完整 Cookie。更建议用 --cookie-file 或 XIANYU_COOKIE 环境变量")
    parser.add_argument("--cookie-file", default=DEFAULT_COOKIE_FILE, help=f"保存完整 Cookie 的文本文件，默认 {DEFAULT_COOKIE_FILE}")
    parser.add_argument("--auth-file", default=DEFAULT_AUTH_FILE, help=f"保存登录设备信息的 JSON 文件，默认 {DEFAULT_AUTH_FILE}")
    parser.add_argument("--qrcode", action="store_true", help="强制使用闲鱼 App 扫码登录，并覆盖本地 Cookie")
    parser.add_argument("--qrcode-file", help=f"二维码 HTML 文件路径，默认写入 {EXPORTS_DIR}/runtime/qrcode_login.html")
    parser.add_argument("--no-open-qrcode", action="store_true", help="只生成二维码 HTML，不自动打开浏览器")
    parser.add_argument("--no-qrcode-image", action="store_true", help="扫码登录时只打印二维码 URL，不生成二维码页面")
    parser.add_argument("--save-cookie-file", help="扫码登录后把本次会话 Cookie 保存到指定文件，默认写入 --cookie-file")
    parser.add_argument("--resume", help="从已有 xianyu_chats.partial.json 续跑，跳过已完成会话")
    parser.add_argument("--cid", action="append", default=[], help="只导出指定会话。可重复传入，也可用逗号分隔")
    parser.add_argument("--only-my-items", action="store_true", help="只导出自己发布商品相关的会话")
    parser.add_argument("--this-year", action="store_true", help="只导出今年的聊天记录")
    parser.add_argument("--year", type=int, help="只导出指定年份的聊天记录，例如 2026")
    parser.add_argument("--list-only", action="store_true", help="只导出会话列表，不拉取消息")
    parser.add_argument("--out", help=f"输出目录，默认写入 {DEFAULT_OUTPUT_ROOT}/xianyu_chats_时间")
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both", help="输出格式")
    parser.add_argument("--page-size", type=int, default=50, help="会话分页大小")
    parser.add_argument("--message-page-size", type=int, default=50, help="消息分页大小")
    parser.add_argument("--max-conversations", type=int, default=0, help="最多导出多少个会话，0 表示不限制")
    parser.add_argument("--max-messages-per-conversation", type=int, default=0, help="每个会话最多导出多少条消息，0 表示不限制")
    parser.add_argument("--newest-first", action="store_true", help="消息按从新到旧输出，默认从旧到新")
    parser.add_argument("--no-raw", action="store_true", help="JSON 不保留闲鱼接口原始字段")
    parser.add_argument("--timeout", type=float, default=30.0, help="WebSocket 单次请求超时时间，单位秒")
    parser.add_argument("--request-delay", type=float, default=DEFAULT_REQUEST_DELAY, help=f"IM 接口请求间隔，默认 {DEFAULT_REQUEST_DELAY:g} 秒")
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    return parser


async def async_main(args: argparse.Namespace) -> None:
    logger.remove()
    logger.add(lambda msg: print(msg, end="", flush=True), level="DEBUG" if args.debug else "INFO")
    args.used_qrcode_login = False

    api, my_user_id, device_id = build_api(args)
    saved_cookie = save_cookie_if_needed(
        api,
        (args.save_cookie_file or args.cookie_file) if args.used_qrcode_login else None,
    )
    if saved_cookie:
        logger.info(f"已保存本次会话 Cookie：{saved_cookie}\n")
    saved_auth = save_auth_if_needed(
        api,
        my_user_id,
        args.auth_file if args.used_qrcode_login else None,
    )
    if saved_auth:
        logger.info(f"已保存本次设备信息：{saved_auth}\n")

    timestamp = datetime.now(LOCAL_TZ).strftime("%Y%m%d_%H%M%S") if LOCAL_TZ else datetime.now().strftime("%Y%m%d_%H%M%S")
    resume_path = Path(args.resume).expanduser() if args.resume else None
    output_dir = Path(
        args.out
        or (resume_path.parent if resume_path else Path(DEFAULT_OUTPUT_ROOT) / f"xianyu_chats_{timestamp}")
    ).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    resume_conversations = None
    if resume_path:
        resume_data = json.loads(resume_path.read_text(encoding="utf-8"))
        resume_user_id = _strip_domain((resume_data.get("account") or {}).get("user_id"))
        if resume_user_id and resume_user_id != my_user_id:
            raise RuntimeError("断点文件账号与当前 Cookie 不一致，拒绝续跑")
        resume_conversations = resume_data.get("conversations") or []
        completed = sum(1 for conversation in resume_conversations if "messages" in conversation)
        logger.info(f"继续断点导出：已完成 {completed}/{len(resume_conversations)} 个会话\n")

    cids = parse_cids(args.cid)
    start_ms, end_ms, year_label = parse_year_filter(args)
    filters = []
    if args.only_my_items:
        filters.append("自己发布的商品")
    if year_label:
        filters.append(year_label)
    if filters:
        logger.info(f"启用筛选：{'，'.join(filters)}\n")

    exporter = ChatExporter(
        api=api,
        my_user_id=my_user_id,
        device_id=device_id,
        include_raw=not args.no_raw,
        timeout=args.timeout,
        request_delay=args.request_delay,
        only_my_items=args.only_my_items,
        start_ms=start_ms,
        end_ms=end_ms,
        checkpoint_writer=lambda data: write_checkpoint(data, output_dir),
    )
    export_data = await exporter.export(
        cids=cids,
        list_only=args.list_only,
        page_size=max(1, args.page_size),
        message_page_size=max(1, args.message_page_size),
        max_conversations=max(0, args.max_conversations),
        max_messages_per_conversation=max(0, args.max_messages_per_conversation),
        oldest_first=not args.newest_first,
        resume_conversations=resume_conversations,
    )

    written = []
    if args.format in {"json", "both"}:
        written.append(write_json(export_data, output_dir))
    if args.format in {"markdown", "both"}:
        index_path, _ = write_markdown(export_data, output_dir)
        written.append(index_path)

    logger.info(
        f"导出完成：{export_data['conversation_count']} 个会话，"
        f"{export_data['message_count']} 条消息\n"
    )
    for path in written:
        logger.info(f"- {path}\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
