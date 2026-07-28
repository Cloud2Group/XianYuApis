from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from xianyu_web.paths import EXPORTS_DIR

DEFAULT_INPUT = str(EXPORTS_DIR / "xianyu_chats_full_20260714" / "xianyu_chats.json")
DEFAULT_OUTPUT = str(EXPORTS_DIR / "requirements_analysis_20260701_20260718")

NEED_PATTERN = re.compile(
    r"[?？]|能不能|可不可以|可以.*吗|怎么|咋|如何|有没有|有.*吗|能否|是否|为什么|"
    r"我想|想要|需要|希望|支持|能导|能把|能不能把|能不能导|怎么办|该怎么办|哪里|多久"
)
FAILURE_PATTERN = re.compile(
    r"失败|报错|不行|不能用|没反应|卡住|卡了|导不出|导不了|打不开|找不到|没找到|"
    r"弄不好|不会弄|还是不行|没有成功|进度不动|一直没好|用不了"
)
UNAVAILABLE_PATTERN = re.compile(
    r"目前没有|暂时没有|没有这个|不支持|做不了|没办法|不能|不可以|导不了|只能|"
    r"不确定|不知道|没做|还没有"
)
WORKAROUND_PATTERN = re.compile(
    r"试试|手动|刷新|重新|用.*浏览器|小说阅读器|网盘|解压|插件|拼在一起|丢给.*总结|"
    r"找.*免费|换.*打开|下载.*手机|复制.*浏览器"
)

CATEGORY_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("持续更新与增量导出", re.compile(r"后续|之后.*聊天|继续.*聊天|再导|重新导|增量|更新记录|链接.*一次|只能导一次|截止到")),
    ("长期记忆、人设与智能体设定", re.compile(r"长期记忆|记忆|人设|设定|原设|作者写|智能体.*信息")),
    ("图片、语音与富媒体", re.compile(r"语音|音频|图片|视频|表情|附件|文件|媒体")),
    ("格式转换、阅读与导入", re.compile(r"备忘录|txt|pdf|word|格式|阅读器|导入|网盘|解压|合并|拼在一起|打开")),
    ("多智能体、批量与多账号", re.compile(r"多个智能体|好几个智能体|批量|一单|多个账号|多个.*导|群聊")),
    ("设备、平台与兼容性", re.compile(r"手机|电脑|安卓|苹果|iphone|ipad|浏览器|微信|qq", re.I)),
    ("完整性、范围与历史深度", re.compile(r"全部|多少条|一年|两年|三年|历史|完整|最早|所有记录|截止")),
    ("稳定性、进度与失败恢复", re.compile(r"失败|报错|卡住|卡了|没反应|进度|刷新|导不出|打不开|一直没好|中断")),
    ("隐私、登录与账号安全", re.compile(r"登录|账号|密码|cookie|隐私|安全|验证码", re.I)),
    ("交付自动化与自助操作", re.compile(r"自动|自助|自己弄|链接|多久|发货|一次性|次数")),
]

HUMAN_MESSAGE_TYPES = {
    "text",
    "content:1",
    "image",
    "custom:3",   # 语音
    "custom:4",   # 视频
    "custom:5",   # 表情
    "custom:7",   # 双方主动发送的商品卡片
    "custom:33",  # 文件
}


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def safe_filename(value: str, default: str) -> str:
    name = first_text(value, default)
    name = re.sub(r"[\\/:*?\"<>|\s]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("._")
    return (name or default)[:100]


def message_content(message: Dict[str, Any]) -> str:
    message_type = str(message.get("type") or "消息")
    payload = message.get("custom_payload") or {}
    if message_type == "custom:3":
        audio = payload.get("audio") or {}
        return f"[语音 {audio.get('duration') or 0}秒] {audio.get('url') or ''}".rstrip()
    if message_type == "custom:4":
        video = payload.get("video") or {}
        return f"[视频] {video.get('url') or video.get('snapshot') or ''}".rstrip()
    if message_type == "custom:5":
        expression = payload.get("expression") or {}
        return f"[表情 {expression.get('name') or ''}] {expression.get('url') or ''}".rstrip()
    if message_type == "custom:7":
        item = ((payload.get("itemCard") or {}).get("item") or {})
        return f"[商品卡片] {item.get('title') or ''} {item.get('price') or ''} ID={item.get('itemId') or ''}".rstrip()
    if message_type == "custom:33":
        file_info = payload.get("file") or {}
        return (
            f"[文件] {file_info.get('displayName') or ''} "
            f"({file_info.get('fileType') or 'unknown'}, {file_info.get('fileSize') or 0} bytes)"
        ).strip()
    text = first_text(message.get("text"))
    return text or f"[{message_type}]"


def is_direct_message(message: Dict[str, Any], my_user_id: str, buyer_user_id: str) -> bool:
    sender_id = str(message.get("sender_id") or "")
    return bool(sender_id and sender_id in {my_user_id, buyer_user_id})


def is_human_dialogue_message(message: Dict[str, Any]) -> bool:
    return str(message.get("type") or "unknown") in HUMAN_MESSAGE_TYPES


def speaker(message: Dict[str, Any], my_user_id: str) -> str:
    return "seller" if str(message.get("sender_id") or "") == my_user_id else "buyer"


def join_block(messages: Iterable[Dict[str, Any]]) -> str:
    return "\n".join(message_content(message) for message in messages).strip()


def categorize(text: str) -> List[str]:
    categories = [name for name, pattern in CATEGORY_PATTERNS if pattern.search(text)]
    return categories or ["其他未归类需求"]


def conversation_item_title(conversation: Dict[str, Any]) -> str:
    raw = conversation.get("raw") or {}
    user_conversation = raw.get("singleChatUserConversation") or {}
    single_conversation = user_conversation.get("singleChatConversation") or {}
    extension = single_conversation.get("extension") or {}
    return first_text(extension.get("itemTitle"))


def build_blocks(messages: List[Dict[str, Any]], my_user_id: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for message in messages:
        role = speaker(message, my_user_id)
        if blocks and blocks[-1]["role"] == role:
            blocks[-1]["messages"].append(message)
        else:
            blocks.append({"role": role, "messages": [message]})
    for block in blocks:
        block["text"] = join_block(block["messages"])
        block["started_at"] = block["messages"][0].get("created_at")
        block["ended_at"] = block["messages"][-1].get("created_at")
    return blocks


def classify_candidate(
    need_text: str,
    response_text: str,
    next_buyer_text: str,
) -> Tuple[str, List[str]]:
    flags: List[str] = []
    if not response_text:
        return "被忽略或未回复", ["no_seller_response"]
    if UNAVAILABLE_PATTERN.search(response_text):
        flags.append("explicit_unavailable")
    if WORKAROUND_PATTERN.search(response_text):
        flags.append("workaround")
    if next_buyer_text and FAILURE_PATTERN.search(next_buyer_text):
        flags.append("still_failing")

    if "still_failing" in flags:
        return "失败后仍未解决", flags
    if "explicit_unavailable" in flags:
        return "当时做不了或明确不支持", flags
    if "workaround" in flags:
        return "仅提供临时绕路", flags
    return "可能已满足，需人工复核", flags


def extract_candidates(
    source: Dict[str, Any],
    start_date: str,
    end_date: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    my_user_id = str((source.get("account") or {}).get("user_id") or "")
    candidates: List[Dict[str, Any]] = []
    filtered_conversations: List[Dict[str, Any]] = []
    all_dates: List[str] = []
    all_message_types: Counter[str] = Counter()
    direct_message_types: Counter[str] = Counter()
    speaker_counts: Counter[str] = Counter()
    human_message_types: Counter[str] = Counter()
    source_conversation_ids = set()

    for conversation in source.get("conversations") or []:
        buyer_user_id = str(conversation.get("peer_user_id") or "")
        item_title = conversation_item_title(conversation)
        messages = []
        for message in conversation.get("messages") or []:
            created_at = str(message.get("created_at") or "")
            date = created_at[:10]
            if not date or not (start_date <= date <= end_date):
                continue
            all_dates.append(date)
            source_conversation_ids.add(str(conversation.get("cid") or ""))
            all_message_types[str(message.get("type") or "unknown")] += 1
            if is_direct_message(message, my_user_id, buyer_user_id):
                message_speaker = speaker(message, my_user_id)
                direct_message_types[str(message.get("type") or "unknown")] += 1
                if not is_human_dialogue_message(message):
                    continue
                speaker_counts[message_speaker] += 1
                human_message_types[str(message.get("type") or "unknown")] += 1
                messages.append({
                    key: message.get(key)
                    for key in (
                        "message_id", "created_at", "created_at_ms", "direction", "sender_id",
                        "sender_name", "type", "text", "content_type",
                        "custom_payload",
                    )
                })
        if not messages:
            continue

        messages.sort(key=lambda item: (item.get("created_at_ms") or 0, item.get("message_id") or ""))
        if not any(str(message.get("sender_id") or "") == buyer_user_id for message in messages):
            continue
        filtered_conversations.append({
            "cid": conversation.get("cid"),
            "title": conversation.get("title"),
            "item_id": conversation.get("item_id"),
            "item_title": item_title,
            "buyer_user_id": buyer_user_id,
            "message_count": len(messages),
            "messages": messages,
        })

        blocks = build_blocks(messages, my_user_id)
        for index, block in enumerate(blocks):
            if block["role"] != "buyer" or not NEED_PATTERN.search(block["text"]):
                continue
            response_block: Optional[Dict[str, Any]] = blocks[index + 1] if index + 1 < len(blocks) and blocks[index + 1]["role"] == "seller" else None
            next_buyer_block: Optional[Dict[str, Any]] = blocks[index + 2] if response_block and index + 2 < len(blocks) and blocks[index + 2]["role"] == "buyer" else None
            response_text = response_block["text"] if response_block else ""
            next_buyer_text = next_buyer_block["text"] if next_buyer_block else ""
            status, flags = classify_candidate(block["text"], response_text, next_buyer_text)
            candidates.append({
                "cid": conversation.get("cid"),
                "title": conversation.get("title"),
                "item_id": conversation.get("item_id"),
                "item_title": item_title,
                "buyer_user_id": buyer_user_id,
                "started_at": block["started_at"],
                "need": block["text"],
                "seller_response": response_text,
                "buyer_follow_up": next_buyer_text,
                "status": status,
                "flags": flags,
                "categories": categorize("\n".join([block["text"], response_text, next_buyer_text])),
            })

    filtered_messages = [
        message
        for conversation in filtered_conversations
        for message in conversation.get("messages") or []
    ]
    filtered_speaker_counts = Counter(speaker(message, my_user_id) for message in filtered_messages)
    filtered_message_types = Counter(str(message.get("type") or "unknown") for message in filtered_messages)
    coverage = {
        "requested_start": start_date,
        "requested_end": end_date,
        "source_exported_at": source.get("exported_at"),
        "actual_first_date": min(all_dates) if all_dates else None,
        "actual_last_date": max(all_dates) if all_dates else None,
        "covered_dates": sorted(set(all_dates)),
        "source_conversation_count": len(source_conversation_ids),
        "source_message_count": sum(all_message_types.values()),
        "conversation_count": len(filtered_conversations),
        "direct_sender_message_count": sum(direct_message_types.values()),
        "human_sender_message_count": sum(human_message_types.values()),
        "direct_message_count": sum(item["message_count"] for item in filtered_conversations),
        "speaker_counts": dict(filtered_speaker_counts),
        "all_message_types": dict(all_message_types.most_common()),
        "direct_message_types": dict(direct_message_types.most_common()),
        "human_dialogue_types": dict(filtered_message_types.most_common()),
        "candidate_count": len(candidates),
    }
    return candidates, coverage, filtered_conversations


def dialogue_line(message: Dict[str, Any], my_user_id: str) -> str:
    role = "我" if str(message.get("sender_id") or "") == my_user_id else "买家"
    content = message_content(message).replace("\r\n", "\n").replace("\r", "\n")
    content = content.replace("\n", f"\n{role}：")
    return f"{role}：{content}"


def write_dialogue_texts(
    conversations: List[Dict[str, Any]],
    coverage: Dict[str, Any],
    my_user_id: str,
    output_dir: Path,
) -> None:
    conversations_dir = output_dir / "conversations_txt"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    for stale_path in conversations_dir.glob("*.txt"):
        stale_path.unlink()
    index_lines = [
        "闲鱼买卖双方对话 TXT 索引",
        f"请求范围：{coverage['requested_start']} 至 {coverage['requested_end']}",
        f"实际覆盖：{coverage['actual_first_date']} 至 {coverage['actual_last_date']}",
        f"会话数：{coverage['conversation_count']}",
        f"买卖双方消息数：{coverage['direct_message_count']}",
        "",
    ]
    corpus_lines = [
        "闲鱼买卖双方完整对话合订本",
        "只保留双方对话正文，不包含消息时间；图片、语音、视频、表情和文件以可读标记保留。",
        "",
    ]

    for index, conversation in enumerate(conversations, 1):
        cid = str(conversation.get("cid") or f"conversation_{index}")
        title = first_text(conversation.get("title"), cid)
        filename = f"{index:04d}_{safe_filename(title, cid)}_{safe_filename(cid, str(index))}.txt"
        path = conversations_dir / filename
        lines = [dialogue_line(message, my_user_id) for message in conversation.get("messages") or []]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        index_lines.append(f"{index:04d} | {title} | {conversation.get('message_count') or 0} 条 | {filename}")
        corpus_lines.extend(["=" * 80, f"会话 {index:04d}：{title}", "", *lines, ""])

    (output_dir / "dialogues_index.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    (output_dir / "all_dialogues.txt").write_text("\n".join(corpus_lines) + "\n", encoding="utf-8")


def write_candidate_markdown(candidates: List[Dict[str, Any]], coverage: Dict[str, Any], output: Path) -> None:
    by_status = Counter(item["status"] for item in candidates)
    by_category = Counter(category for item in candidates for category in item["categories"])
    lines = [
        "# 闲鱼对话需求候选清单",
        "",
        f"- 请求范围：{coverage['requested_start']} 至 {coverage['requested_end']}",
        f"- 实际数据覆盖：{coverage['actual_first_date']} 至 {coverage['actual_last_date']}",
        f"- 会话数：{coverage['conversation_count']}",
        f"- 买卖双方直接消息：{coverage['direct_message_count']}",
        f"- 候选需求块：{coverage['candidate_count']}",
        "",
        "## 状态统计",
        "",
    ]
    lines.extend(f"- {name}：{count}" for name, count in by_status.most_common())
    lines.extend(["", "## 类别统计", ""])
    lines.extend(f"- {name}：{count}" for name, count in by_category.most_common())
    lines.extend(["", "## 候选明细", ""])

    for index, item in enumerate(candidates, 1):
        lines.extend([
            f"### {index}. {item['status']}｜{'、'.join(item['categories'])}",
            "",
            f"- 时间：{item['started_at']}",
            f"- 会话：{item['title'] or item['buyer_user_id']}（CID `{item['cid']}`，商品 `{item['item_id'] or ''}`）",
            f"- 商品：{item.get('item_title') or '[未知商品]'}",
            "- 买家需求：",
            "",
            item["need"] or "[空]",
            "",
            "- 当时回复：",
            "",
            item["seller_response"] or "[未回复]",
            "",
        ])
        if item["buyer_follow_up"]:
            lines.extend(["- 买家后续：", "", item["buyer_follow_up"], ""])

    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="从闲鱼聊天记录中提取未满足需求候选")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    parser.add_argument("--start", default="2026-07-01")
    parser.add_argument("--end", default="2026-07-18")
    args = parser.parse_args()

    source = json.loads(Path(args.input).expanduser().read_text(encoding="utf-8"))
    candidates, coverage, conversations = extract_candidates(source, args.start, args.end)
    output_dir = Path(args.out).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "need_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "dialogues.json").write_text(json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "coverage": coverage,
        "conversations": conversations,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    my_user_id = str((source.get("account") or {}).get("user_id") or "")
    write_dialogue_texts(conversations, coverage, my_user_id, output_dir)
    write_candidate_markdown(candidates, coverage, output_dir / "need_candidates.md")
    print(json.dumps(coverage, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
