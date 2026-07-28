"""Versioned JSONL wire protocol for the local App-native IM bridge.

The wire format is intentionally boring: one UTF-8 JSON object per line.  It
works with Python, Frida's ``send()`` messages, and small command-line tools,
while keeping the App-specific AIM objects on the native side of the bridge.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any, Dict, Mapping, Optional


PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 256 * 1024
MAX_TEXT_CHARS = 64 * 1024


class ProtocolError(ValueError):
    """Raised when a bridge frame is malformed or violates the contract."""


def now_ms() -> int:
    return int(time.time() * 1000)


def new_request_id(prefix: str = "req") -> str:
    return "%s_%s_%s" % (prefix, now_ms(), secrets.token_hex(5))


def _string(value: Any, field: str, *, required: bool = False) -> Optional[str]:
    if value is None:
        if required:
            raise ProtocolError("missing %s" % field)
        return None
    if not isinstance(value, (str, int)):
        raise ProtocolError("%s must be a string" % field)
    result = str(value).strip()
    if required and not result:
        raise ProtocolError("empty %s" % field)
    return result


def _text(value: Any, field: str = "text") -> str:
    if not isinstance(value, str):
        raise ProtocolError("%s must be a string" % field)
    if not value:
        raise ProtocolError("empty %s" % field)
    if len(value) > MAX_TEXT_CHARS:
        raise ProtocolError("%s is too long" % field)
    return value


def _object(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError("frame must be a JSON object")
    return dict(value)


def decode_line(line: bytes | str) -> Dict[str, Any]:
    """Decode one newline-delimited frame and reject oversized input."""
    if isinstance(line, bytes):
        if len(line) > MAX_LINE_BYTES:
            raise ProtocolError("frame is too large")
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError("frame is not UTF-8") from exc
    elif not isinstance(line, str):
        raise ProtocolError("frame must be bytes or string")
    if len(line.encode("utf-8")) > MAX_LINE_BYTES:
        raise ProtocolError("frame is too large")
    try:
        value = json.loads(line)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("invalid JSON") from exc
    return _object(value)


def encode_message(message: Mapping[str, Any]) -> bytes:
    """Encode a frame with a single trailing newline."""
    value = _object(message)
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError("frame is not JSON serialisable") from exc
    if len(encoded) > MAX_LINE_BYTES:
        raise ProtocolError("frame is too large")
    return encoded + b"\n"


def make_hello(role: str, account_id: str, **extra: Any) -> Dict[str, Any]:
    role = _string(role, "role", required=True)  # type: ignore[assignment]
    if role not in {"native", "business", "observer"}:
        raise ProtocolError("unsupported role")
    account_id = _string(account_id, "account_id", required=True)  # type: ignore[assignment]
    frame: Dict[str, Any] = {
        "type": "hello",
        "protocol": PROTOCOL_VERSION,
        "role": role,
        "account_id": account_id,
        "sent_at_ms": now_ms(),
    }
    frame.update(extra)
    return frame


def validate_hello(frame: Mapping[str, Any]) -> Dict[str, Any]:
    frame = _object(frame)
    if frame.get("type") != "hello":
        raise ProtocolError("first frame must be hello")
    protocol = frame.get("protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    role = _string(frame.get("role"), "role", required=True)
    if role not in {"native", "business", "observer"}:
        raise ProtocolError("unsupported role")
    account_id = _string(frame.get("account_id"), "account_id", required=True)
    result = dict(frame)
    result["role"] = role
    result["account_id"] = account_id
    return result


def make_message_received(
    *,
    account_id: str,
    message_id: str,
    sid: Optional[str] = None,
    app_cid: Optional[str] = None,
    peer_uid: Optional[str] = None,
    direction: str = "in",
    content_type: str = "text",
    text: Optional[str] = None,
    created_at_ms: Optional[int] = None,
    raw_ref: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "event": "message.received",
        "account_id": _string(account_id, "account_id", required=True),
        "message_id": _string(message_id, "message_id", required=True),
        "sid": _string(sid, "sid"),
        "app_cid": _string(app_cid, "app_cid"),
        "peer_uid": _string(peer_uid, "peer_uid"),
        "direction": direction,
        "content_type": content_type,
        "text": text,
        "created_at_ms": created_at_ms if created_at_ms is not None else now_ms(),
        "observed_at_ms": now_ms(),
    }
    if text is not None:
        result["text"] = _text(text)
    if raw_ref is not None:
        result["raw_ref"] = _string(raw_ref, "raw_ref")
    result.update(extra)
    return result


def validate_event(frame: Mapping[str, Any]) -> Dict[str, Any]:
    frame = _object(frame)
    event = _string(frame.get("event"), "event", required=True)
    account_id = _string(frame.get("account_id"), "account_id", required=True)
    result = dict(frame)
    result["event"] = event
    result["account_id"] = account_id
    if event == "message.received":
        result["message_id"] = _string(
            frame.get("message_id"), "message_id", required=True
        )
        direction = frame.get("direction", "in")
        if direction not in {"in", "out", "unknown"}:
            raise ProtocolError("invalid direction")
        result["direction"] = direction
        if frame.get("text") is not None:
            result["text"] = _text(frame.get("text"))
    elif event == "message.send.result":
        result["request_id"] = _string(
            frame.get("request_id"), "request_id", required=True
        )
        status = _string(frame.get("status"), "status", required=True)
        if status not in {"accepted", "sent", "failed", "timeout", "duplicate"}:
            raise ProtocolError("invalid send result status")
        result["status"] = status
    elif event == "transport.status":
        state = _string(frame.get("state"), "state", required=True)
        if state not in {
            "starting",
            "app_ready",
            "aim_connecting",
            "connected",
            "reconnecting",
            "auth_refreshing",
            "disconnected",
            "error",
        }:
            raise ProtocolError("invalid transport state")
        result["state"] = state
    return result


def validate_command(frame: Mapping[str, Any]) -> Dict[str, Any]:
    frame = _object(frame)
    action = _string(frame.get("action"), "action", required=True)
    if action not in {"send_text", "reply_text", "mark_read", "ping"}:
        raise ProtocolError("unsupported action")
    result = dict(frame)
    result["action"] = action
    result["account_id"] = _string(
        frame.get("account_id"), "account_id", required=True
    )
    if action in {"send_text", "reply_text"}:
        result["request_id"] = _string(
            frame.get("request_id"), "request_id", required=True
        )
        result["text"] = _text(frame.get("text"))
        if action == "reply_text":
            result["reply_to_mid"] = _string(
                frame.get("reply_to_mid"), "reply_to_mid", required=True
            )
        elif frame.get("reply_to_mid") is not None:
            result["reply_to_mid"] = _string(frame.get("reply_to_mid"), "reply_to_mid")
        # A session key is needed for serialisation.  app_cid is preferred,
        # but sid/peer_uid are accepted while the native fields are still
        # being mapped from the callback object.
        if not any(frame.get(key) for key in ("app_cid", "sid", "peer_uid")):
            raise ProtocolError("one of app_cid, sid, peer_uid is required")
    elif action == "mark_read":
        result["mids"] = frame.get("mids") or []
        if not isinstance(result["mids"], list):
            raise ProtocolError("mids must be a list")
    return result


def make_send_result(
    *,
    account_id: str,
    request_id: str,
    status: str,
    message_id: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "event": "message.send.result",
        "account_id": _string(account_id, "account_id", required=True),
        "request_id": _string(request_id, "request_id", required=True),
        "status": status,
        "message_id": _string(message_id, "message_id"),
        "error_code": _string(error_code, "error_code"),
        "error_message": _string(error_message, "error_message"),
        "observed_at_ms": now_ms(),
    }
    result.update(extra)
    return result


def make_status(
    *,
    account_id: str,
    state: str,
    last_heartbeat_ms: Optional[int] = None,
    reconnect_count: int = 0,
    **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "event": "transport.status",
        "account_id": _string(account_id, "account_id", required=True),
        "state": state,
        "last_heartbeat_ms": last_heartbeat_ms,
        "reconnect_count": reconnect_count,
        "observed_at_ms": now_ms(),
    }
    result.update(extra)
    return result


def safe_log_frame(frame: Mapping[str, Any]) -> Dict[str, Any]:
    """Return a recursively redacted copy for console/runtime logs."""
    hidden = {"text", "raw", "raw_ref", "token", "cookie", "authorization"}

    def redact(value: Any, key: Optional[str] = None) -> Any:
        if key is not None and key.lower() in hidden:
            return "<redacted>"
        if isinstance(value, Mapping):
            return {str(child_key): redact(child, str(child_key)) for child_key, child in value.items()}
        if isinstance(value, list):
            return [redact(child) for child in value]
        if isinstance(value, tuple):
            return [redact(child) for child in value]
        return value

    return redact(dict(frame))
