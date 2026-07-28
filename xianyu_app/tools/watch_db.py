#!/usr/bin/env python3
"""Tail the local Xianyu IM SQLite stores.

This is deliberately a read-only bridge.  It does not open a network socket,
write to the app database, or read cookies/tokens.  The 7.27.x app has used
both the legacy ``Message`` store and the newer ``PMessage`` xstore, so the
watcher accepts either schema and can watch both at the same time.

Example:

    python -m xianyu_app.tools.watch_db --uid ACCOUNT_UID

The default mode starts at the current end of each store and prints only new
rows.  Add ``--replay`` to emit rows already present when the process starts.
Output is JSONL so it can be piped into the existing Python message service.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote


DEFAULT_UID = os.environ.get("XIANYU_APP_UID", "")
DEFAULT_CONTAINER_GLOB = os.path.expanduser(
    "~/Library/Containers/*/Data"
)
UID_PATTERNS = (
    re.compile(r"fleamarket_idlefish_im_(\d+)\.db$"),
    re.compile(r"if_msg_xstore_user_(\d+)\.db$"),
    re.compile(r"^(\d+)@goofish$"),
)


@dataclass(frozen=True)
class Store:
    path: Path
    schema: str


def discover_uids(explicit: Sequence[str] = ()) -> List[str]:
    """Discover account UIDs from known local IM store names."""
    candidates: List[Path] = [Path(value).expanduser() for value in explicit]
    if not explicit:
        for data_root in sorted(glob.glob(DEFAULT_CONTAINER_GLOB)):
            root = Path(data_root)
            candidates.extend(root.glob("Documents/fleamarket_idlefish_im_*.db"))
            candidates.extend(root.glob("Library/Caches/if_msg_xstore_user_*.db"))
            candidates.extend(root.glob("Documents/AIMData/*@goofish/database/im.sqlite"))

    result: Set[str] = set()
    for path in candidates:
        values = (path.name, *(part for part in path.parts if part.endswith("@goofish")))
        for value in values:
            for pattern in UID_PATTERNS:
                match = pattern.search(value)
                if match and match.group(1) != "0":
                    result.add(match.group(1))
    return sorted(result)


def _json_load(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _stringify(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _find_text(value: Any) -> Optional[str]:
    """Find a useful text field in nested AIM/xstore content JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Prefer actual message text over titles/metadata.
        for key in (
            "text",
            "textContent",
            "content",
            "value",
            "reminderContent",
            "title",
        ):
            if key in value:
                found = _find_text(value[key])
                if found:
                    return found
        for child in value.values():
            found = _find_text(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_text(child)
            if found:
                return found
    return None


def _content_text(*values: Any) -> Optional[str]:
    for value in values:
        if value is None:
            continue
        direct = _stringify(value)
        if direct:
            parsed = _json_load(direct)
            if parsed is not None:
                found = _find_text(parsed)
                if found:
                    return found
            return direct
        found = _find_text(value)
        if found:
            return found
    return None


def _connect(path: Path) -> sqlite3.Connection:
    # Do not use immutable=1: it would ignore a live SQLite WAL.
    uri = "file:" + quote(str(path), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=0.25)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=250")
    return conn


def _table_names(conn: sqlite3.Connection) -> Set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def discover_stores(uid: str, explicit: Sequence[str]) -> List[Store]:
    paths: List[Path] = [Path(p).expanduser() for p in explicit]
    if not explicit:
        for data_root in sorted(glob.glob(DEFAULT_CONTAINER_GLOB)):
            root = Path(data_root)
            paths.extend(
                [
                    root / "Documents" / f"fleamarket_idlefish_im_{uid}.db",
                    root
                    / "Library"
                    / "Caches"
                    / f"if_msg_xstore_user_{uid}.db",
                ]
            )

    stores: List[Store] = []
    seen: Set[Path] = set()
    for path in paths:
        path = path.resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            conn = _connect(path)
            tables = _table_names(conn)
            conn.close()
        except (OSError, sqlite3.Error):
            continue
        if "PMessage" in tables:
            stores.append(Store(path, "pmessage"))
        elif "Message" in tables:
            stores.append(Store(path, "message"))
    return stores


def discover_cipher_db(uid: str) -> List[Path]:
    """Return AIM CipherDB files that need an in-process hook."""
    result: List[Path] = []
    for data_root in sorted(glob.glob(DEFAULT_CONTAINER_GLOB)):
        candidate = (
            Path(data_root)
            / "Documents"
            / "AIMData"
            / f"{uid}@goofish"
            / "database"
            / "im.sqlite"
        )
        if candidate.exists():
            result.append(candidate)
    return result


def _query_store(store: Store, since_ms: int) -> Iterable[Dict[str, Any]]:
    try:
        conn = _connect(store.path)
    except (OSError, sqlite3.Error):
        return []

    try:
        if store.schema == "pmessage":
            # The dollar signs are part of the xstore column names.
            sql = """
                SELECT rowid AS _rowid,
                       messageId AS message_id,
                       Sid AS sid,
                       Uid AS uid,
                       "sessionInfo$$$$sessionId" AS session_id,
                       "senderInfo$$$$userId" AS sender_uid,
                       "receiver$$$$userId" AS receiver_uid,
                       content AS content,
                       proposal AS proposal,
                       attachment AS attachment,
                       extJson AS ext_json,
                       timeStamp AS timestamp_ms,
                       LocalJson AS local_json,
                       XState AS state
                  FROM PMessage
                 WHERE COALESCE(timeStamp, 0) >= ?
                 ORDER BY COALESCE(timeStamp, 0), _rowid
            """
        else:
            sql = """
                SELECT rowid AS _rowid,
                       messageId AS message_id,
                       sid AS sid,
                       uid AS uid,
                       sid AS session_id,
                       uid AS sender_uid,
                       NULL AS receiver_uid,
                       textContent AS content,
                       NULL AS proposal,
                       NULL AS attachment,
                       NULL AS ext_json,
                       timeStamp AS timestamp_ms,
                       message AS local_json,
                       sendState AS state,
                       contentType AS content_type,
                       readState AS read_state
                  FROM Message
                 WHERE COALESCE(timeStamp, 0) >= ?
                 ORDER BY COALESCE(timeStamp, 0), _rowid
            """

        for row in conn.execute(sql, (since_ms,)):
            item = dict(row)
            item["source"] = store.schema
            item["store"] = str(store.path)
            yield item
    except sqlite3.Error:
        return
    finally:
        conn.close()


def _normalise(row: Dict[str, Any], uid: str, include_raw: bool) -> Dict[str, Any]:
    message_id = _stringify(row.get("message_id")) or ""
    sender = _stringify(row.get("sender_uid"))
    receiver = _stringify(row.get("receiver_uid"))
    own = str(uid)
    if sender == own:
        direction = "out"
    elif receiver == own or sender:
        direction = "in"
    else:
        direction = "unknown"

    event: Dict[str, Any] = {
        "event": "message.received",
        "source": row.get("source"),
        "message_id": message_id,
        "sid": _stringify(row.get("sid")),
        "session_id": _stringify(row.get("session_id")),
        "sender_uid": sender,
        "receiver_uid": receiver,
        "direction": direction,
        "content_type": row.get("content_type"),
        "text": _content_text(row.get("content"), row.get("local_json")),
        "timestamp_ms": row.get("timestamp_ms"),
        "observed_at_ms": int(time.time() * 1000),
        "state": row.get("state"),
    }
    if include_raw:
        event["raw"] = {
            key: value
            for key, value in row.items()
            if key not in {"_rowid", "store"}
        }
    return event


def _emit(event: Dict[str, Any], human: bool) -> None:
    if human:
        text = event.get("text") or "<非文本消息>"
        print(
            "[{direction}] sid={sid} sender={sender} id={mid} {text}".format(
                direction=event.get("direction"),
                sid=event.get("sid") or event.get("session_id") or "-",
                sender=event.get("sender_uid") or "-",
                mid=event.get("message_id") or "-",
                text=text.replace("\n", "\\n"),
            ),
            flush=True,
        )
    else:
        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uid",
        default=DEFAULT_UID,
        help="闲鱼账号 UID；省略时从本地 IM 数据库自动发现",
    )
    parser.add_argument(
        "--db",
        action="append",
        default=[],
        help="显式指定 SQLite 文件，可重复传入",
    )
    parser.add_argument(
        "--interval", type=float, default=0.5, help="轮询间隔（秒）"
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="启动时回放现有消息；默认只监听启动后的新增消息",
    )
    parser.add_argument(
        "--once", action="store_true", help="扫描一次后退出"
    )
    parser.add_argument(
        "--human", action="store_true", help="使用可读文本而不是 JSONL"
    )
    parser.add_argument(
        "--include-raw", action="store_true", help="输出原始字段（可能包含较多正文）"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.interval <= 0:
        print("--interval 必须大于 0", file=sys.stderr)
        return 2

    uid = str(args.uid or "").strip()
    if not uid:
        candidates = discover_uids(args.db)
        if len(candidates) == 1:
            uid = candidates[0]
            print(f"[native-im] auto-detected account UID: {uid}", file=sys.stderr)
        elif not candidates:
            print(
                "[native-im] no account UID was found; pass --uid ACCOUNT_UID",
                file=sys.stderr,
            )
            return 2
        else:
            print(
                "[native-im] multiple account UIDs were found; pass --uid: "
                + ", ".join(candidates),
                file=sys.stderr,
            )
            return 2

    # A message can be mirrored into both stores during a schema migration;
    # deduplicate by message id across stores.
    seen: Set[Tuple[str, str]] = set()
    initialised: Set[Path] = set()
    warned_cipher_db = False
    # A small look-back catches a row committed just as a poll starts.
    since_ms = 0 if args.replay else int(time.time() * 1000)

    try:
        while True:
            stores = discover_stores(uid, args.db)
            if not warned_cipher_db and not args.db:
                cipher_dbs = discover_cipher_db(uid)
                if cipher_dbs:
                    print(
                        "[native-im] detected AIM CipherDB; "
                        "plain sqlite tailing covers fallback stores only: "
                        + ", ".join(str(path) for path in cipher_dbs),
                        file=sys.stderr,
                    )
                warned_cipher_db = True
            for store in stores:
                for row in _query_store(store, since_ms):
                    event = _normalise(row, uid, args.include_raw)
                    message_id = str(event.get("message_id") or "")
                    key = (
                        ("message", message_id)
                        if message_id
                        else (
                            str(event.get("source")),
                            f"{event.get('sid')}:{event.get('timestamp_ms')}"
                        )
                    )
                    if key[1] and key in seen:
                        continue
                    # In tail mode, suppress the pre-existing rows on the
                    # first successful scan of each store.
                    if not args.replay and store.path not in initialised:
                        if key[1]:
                            seen.add(key)
                        continue
                    if key[1]:
                        seen.add(key)
                    _emit(event, args.human)
                initialised.add(store.path)

            if args.once:
                return 0
            # Keep a modest look-back so commits sharing the same millisecond
            # are not missed; the seen set makes this idempotent.
            since_ms = max(0, int(time.time() * 1000) - 1500)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
