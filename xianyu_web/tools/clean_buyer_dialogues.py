from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from xianyu_web.paths import EXPORTS_DIR

DEFAULT_INPUT = str(EXPORTS_DIR / "xianyu_chats_2026_my_items" / "xianyu_chats.json")
DEFAULT_OUTPUT = str(EXPORTS_DIR / "xianyu_chats_2026_my_items" / "buyer_dialogues_cleaned")


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _safe_filename(value: str, default: str) -> str:
    name = _first_text(value, default)
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._")
    return (name or default)[:100]


def _clean_content(message: Dict[str, Any]) -> str:
    text = _first_text(message.get("text"))
    if text:
        return text
    message_type = _first_text(message.get("type"), "unknown")
    if message_type == "image":
        return "[图片]"
    if message_type == "card":
        return "[卡片]"
    return f"[{message_type}]"


def _speaker_for(sender_id: str, my_user_id: str, buyer_user_id: str) -> str:
    if sender_id == my_user_id:
        return "me"
    if buyer_user_id and sender_id == buyer_user_id:
        return "buyer"
    return ""


def _speaker_label(speaker: str) -> str:
    return "我" if speaker == "me" else "买家"


def _sort_messages(messages: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        messages,
        key=lambda item: (item.get("created_at_ms") or 0, item.get("message_id") or ""),
    )


def clean_export_data(
    export_data: Dict[str, Any],
    require_item: bool,
    require_buyer: bool,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    my_user_id = str((export_data.get("account") or {}).get("user_id") or "")
    cleaned_conversations: List[Dict[str, Any]] = []
    dropped_reasons: Counter[str] = Counter()
    dropped_message_types: Counter[str] = Counter()
    kept_message_types: Counter[str] = Counter()

    for conversation in export_data.get("conversations") or []:
        buyer_user_id = str(conversation.get("peer_user_id") or "")
        item_id = str(conversation.get("item_id") or "")
        if require_buyer and not buyer_user_id:
            dropped_reasons["missing_buyer"] += 1
            continue
        if require_item and not item_id:
            dropped_reasons["missing_item"] += 1
            continue

        cleaned_messages = []
        for message in conversation.get("messages") or []:
            sender_id = str(message.get("sender_id") or "")
            speaker = _speaker_for(sender_id, my_user_id, buyer_user_id)
            if not speaker:
                dropped_message_types[str(message.get("type") or "unknown")] += 1
                continue

            message_type = str(message.get("type") or "unknown")
            kept_message_types[message_type] += 1
            cleaned_messages.append(
                {
                    "message_id": message.get("message_id"),
                    "created_at_ms": message.get("created_at_ms"),
                    "created_at": message.get("created_at"),
                    "speaker": speaker,
                    "speaker_label": _speaker_label(speaker),
                    "sender_id": sender_id,
                    "sender_name": message.get("sender_name"),
                    "type": message_type,
                    "content": _clean_content(message),
                }
            )

        cleaned_messages = _sort_messages(cleaned_messages)
        if not cleaned_messages:
            dropped_reasons["no_buyer_dialogue_messages"] += 1
            continue

        speaker_counts = Counter(message["speaker"] for message in cleaned_messages)
        cleaned_conversations.append(
            {
                "cid": conversation.get("cid"),
                "title": conversation.get("title"),
                "item_id": item_id,
                "buyer_user_id": buyer_user_id,
                "owner_user_id": conversation.get("owner_user_id"),
                "modified_at": conversation.get("modified_at"),
                "message_count": len(cleaned_messages),
                "speaker_counts": dict(speaker_counts),
                "messages": cleaned_messages,
            }
        )

    message_count = sum(item["message_count"] for item in cleaned_conversations)
    cleaned_data = {
        "cleaned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_exported_at": export_data.get("exported_at"),
        "account": {"user_id": my_user_id},
        "conversation_count": len(cleaned_conversations),
        "message_count": message_count,
        "cleaning_rule": {
            "kept": "只保留发送人为账号本人或会话买家的消息，保留文本、图片、卡片和自定义消息。",
            "dropped": "剔除闲小蜜、交易通知、工作台通知等非买卖双方发送的消息。",
            "require_item": require_item,
            "require_buyer": require_buyer,
        },
        "conversations": cleaned_conversations,
    }
    report = {
        "source_conversation_count": len(export_data.get("conversations") or []),
        "source_message_count": sum(len(item.get("messages") or []) for item in export_data.get("conversations") or []),
        "cleaned_conversation_count": len(cleaned_conversations),
        "cleaned_message_count": message_count,
        "dropped_reasons": dict(dropped_reasons),
        "kept_message_types": dict(kept_message_types),
        "dropped_message_types": dict(dropped_message_types),
    }
    return cleaned_data, report


def write_json(data: Dict[str, Any], output_dir: Path) -> Path:
    output_path = output_dir / "buyer_dialogues.json"
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def write_report(report: Dict[str, Any], output_dir: Path) -> Path:
    output_path = output_dir / "cleaning_report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _markdown_content(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text or "[空消息]"


def _dialogue_line(message: Dict[str, Any]) -> str:
    created_at = _first_text(message.get("created_at"), "未知时间")
    speaker = _first_text(message.get("speaker_label"), "未知")
    message_type = _first_text(message.get("type"), "unknown")
    content = _markdown_content(message.get("content"))
    return f"- {created_at}｜{speaker}｜{message_type}：{content}"


def write_markdown(data: Dict[str, Any], output_dir: Path) -> Tuple[Path, Path, Path]:
    conversations_dir = output_dir / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# 买卖双方对话清洗结果",
        "",
        f"- 清洗时间：{data.get('cleaned_at')}",
        f"- 源导出时间：{data.get('source_exported_at')}",
        f"- 会话数：{data.get('conversation_count')}",
        f"- 消息数：{data.get('message_count')}",
        "",
        "## 会话列表",
        "",
    ]
    corpus_lines = [
        "# 买卖双方对话语料",
        "",
        "这份文件只保留账号本人和买家发出的消息，适合用于分析买家问题、疑虑、成交话术和商品介绍表达。",
        "",
    ]

    for index, conversation in enumerate(data.get("conversations") or [], 1):
        cid = str(conversation.get("cid") or f"conversation_{index}")
        title = _first_text(conversation.get("title"), cid)
        item_id = _first_text(conversation.get("item_id"), "")
        filename = f"{index:04d}_{_safe_filename(title, cid)}_{_safe_filename(cid, str(index))}.md"
        path = conversations_dir / filename
        relative_path = path.relative_to(output_dir)
        index_lines.append(
            f"- [{title}]({relative_path.as_posix()})：{conversation.get('message_count', 0)} 条消息，商品 `{item_id}`，CID `{cid}`"
        )

        header = [
            f"# {title}",
            "",
            f"- 会话 ID：`{cid}`",
            f"- 商品 ID：`{item_id}`",
            f"- 买家 ID：`{conversation.get('buyer_user_id') or ''}`",
            f"- 消息数：{conversation.get('message_count', 0)}",
            "",
            "## 对话",
            "",
        ]
        message_lines = [_dialogue_line(message) for message in conversation.get("messages") or []]
        path.write_text("\n".join(header + message_lines) + "\n", encoding="utf-8")

        corpus_lines.extend(
            [
                f"## 会话 {index:04d}：{title}",
                "",
                f"- 商品 ID：`{item_id}`",
                f"- 买家 ID：`{conversation.get('buyer_user_id') or ''}`",
                "",
            ]
        )
        corpus_lines.extend(message_lines)
        corpus_lines.append("")

    index_path = output_dir / "index.md"
    corpus_path = output_dir / "dialogue_corpus.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    corpus_path.write_text("\n".join(corpus_lines) + "\n", encoding="utf-8")
    return index_path, corpus_path, conversations_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="清洗闲鱼导出结果，只保留账号本人和买家的对话")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"输入 JSON，默认 {DEFAULT_INPUT}")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help=f"输出目录，默认 {DEFAULT_OUTPUT}")
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both", help="输出格式")
    parser.add_argument("--allow-missing-item", action="store_true", help="允许没有商品 ID 的会话进入结果")
    parser.add_argument("--allow-missing-buyer", action="store_true", help="允许没有买家 ID 的会话进入结果")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser()
    output_dir = Path(args.out).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    export_data = json.loads(input_path.read_text(encoding="utf-8"))
    cleaned_data, report = clean_export_data(
        export_data,
        require_item=not args.allow_missing_item,
        require_buyer=not args.allow_missing_buyer,
    )

    written = [write_report(report, output_dir)]
    if args.format in {"json", "both"}:
        written.append(write_json(cleaned_data, output_dir))
    if args.format in {"markdown", "both"}:
        index_path, corpus_path, _ = write_markdown(cleaned_data, output_dir)
        written.extend([index_path, corpus_path])

    print(
        f"清洗完成：{report['cleaned_conversation_count']} 个会话，"
        f"{report['cleaned_message_count']} 条消息"
    )
    for path in written:
        print(f"- {path}")


if __name__ == "__main__":
    main()
