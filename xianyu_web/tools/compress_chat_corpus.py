from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from xianyu_web.paths import EXPORTS_DIR

_ANALYSIS_DIR = EXPORTS_DIR / "requirements_analysis_20260701_20260718"
DEFAULT_INPUT = str(_ANALYSIS_DIR / "dialogues.json")
DEFAULT_CANDIDATES = str(_ANALYSIS_DIR / "need_candidates.json")
DEFAULT_REPORT = str(_ANALYSIS_DIR / "unmet_requirements_report.md")
DEFAULT_OUTPUT = str(_ANALYSIS_DIR / "compact")
MY_USER_ID = "2215217271688"

URL_PATTERN = re.compile(r"(?:https?|fleamarket)://\S+", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)1\d{10}(?!\d)")
SECRET_PATTERN = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|[A-Za-z0-9_-]{40,})\b")
LONG_ID_PATTERN = re.compile(r"(?<!\d)\d{16,}(?!\d)")
MEDIA_PATH_PATTERN = re.compile(r"\borigin_ugc_voice/\S+", re.I)
CODE_PATTERN = re.compile(r"^(?:\d{4,8}|[A-Z0-9]{12,})$")
SPACE_PATTERN = re.compile(r"[ \t]+")
ACK_PATTERN = re.compile(
    r"^(?:你?好(?:呀|啊|哦)?|在吗|在的|好+|好的+|好滴+|好哒+|好嘞|嗯+|嗯嗯|"
    r"哦+|哦哦|ok+|okk+|okok|行|行的|可以|可以的|对|对的|是的|谢谢|谢谢你|"
    r"收到|明白|知道了|没事|没问题|稍等|等一下|宝子|宝宝|老师|亲|哈喽|hello|"
    r"[\[【].+?[\]】])(?:[~～!！。.]*)$",
    re.I,
)
ACK_SEQUENCE_PATTERN = re.compile(
    r"^(?:(?:好(?:的|滴|哒|嘞)?|谢谢(?:你)?|嗯+|哦+|ok+|行(?:的)?|可以(?:的)?|"
    r"对(?:的)?|是(?:的)?|没事|没问题|明白(?:了)?|知道(?:了)?|收到|稍等|等一下|"
    r"宝子|宝宝|老师|亲|哈喽|你好|在吗|在的))+$",
    re.I,
)

CANNED_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"工具链接是一次性的.*导出工具链接发你", re.S), "[标准说明：一次性自助导出链接]"),
    (re.compile(r"主页还有.*自助导出工具.*保护客户隐私", re.S), "[标准说明：可自助导出，无需提供账号信息]"),
    (re.compile(r"夸克怎么免费解压缩.*小红书", re.S), "[标准说明：夸克下载解压教程]"),
    (re.compile(r"网盘打开.*下载压缩包到手机.*解压", re.S), "[标准说明：下载压缩包后在手机解压]"),
    (re.compile(r"宝子这个是网址链接.*教程走", re.S), "[标准说明：打开链接按教程导出]"),
]


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = URL_PATTERN.sub("<链接>", text)
    text = text.replace("https://", "<链接>").replace("http://", "<链接>")
    text = PHONE_PATTERN.sub("<手机号>", text)
    text = SECRET_PATTERN.sub("<密钥/令牌>", text)
    text = LONG_ID_PATTERN.sub("<长ID>", text)
    text = MEDIA_PATH_PATTERN.sub("<音频资源>", text)
    text = re.sub(r"\[(图片|视频|语音)[^\]]*]\s*<链接>", r"[\1]", text)
    lines = []
    for line in text.splitlines():
        line = SPACE_PATTERN.sub(" ", line).strip()
        if line and line not in lines:
            lines.append(line)
    text = " / ".join(lines)
    for pattern, replacement in CANNED_PATTERNS:
        if pattern.search(text):
            return replacement
    return text


def is_low_signal(text: str) -> bool:
    normalized = text.strip(" ，,。.!！?？~～")
    if not normalized:
        return True
    if normalized.startswith(("[图片", "[视频", "[语音", "[文件", "[商品卡片")):
        return False
    without_reactions = re.sub(r"\[[^\]]+]", "", normalized)
    without_reactions = re.sub(r"[\s，,。.!！?？~～、]+", "", without_reactions)
    return bool(
        ACK_PATTERN.fullmatch(normalized)
        or ACK_SEQUENCE_PATTERN.fullmatch(without_reactions)
    )


def compact_message_content(message: Dict[str, Any]) -> str:
    message_type = str(message.get("type") or "unknown")
    payload = message.get("custom_payload") or {}
    if message_type == "image":
        return "[图片]"
    if message_type == "custom:3":
        duration = (payload.get("audio") or {}).get("duration") or 0
        return f"[语音 {duration}秒]"
    if message_type == "custom:4":
        return "[视频]"
    if message_type == "custom:5":
        name = (payload.get("expression") or {}).get("name") or ""
        return f"[表情 {name}]".strip()
    if message_type == "custom:7":
        item = ((payload.get("itemCard") or {}).get("item") or {})
        return f"[商品卡片 {item.get('title') or ''} {item.get('price') or ''}]".strip()
    if message_type == "custom:33":
        file_info = payload.get("file") or {}
        return f"[文件 {file_info.get('displayName') or ''} {file_info.get('fileSize') or 0}B]".strip()
    return clean_text(message.get("text"))


def role_for(message: Dict[str, Any]) -> str:
    return "我" if str(message.get("sender_id") or "") == MY_USER_ID else "买家"


def compact_conversation(conversation: Dict[str, Any]) -> List[str]:
    cleaned: List[Tuple[str, str, str]] = []
    seen = set()
    for message in conversation.get("messages") or []:
        content = compact_message_content(message)
        if not content or is_low_signal(content):
            continue
        if CODE_PATTERN.fullmatch(content):
            content = "[验证码/识别码]"
        role = role_for(message)
        dedupe_key = (role, content)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        timestamp = str(message.get("created_at") or "")[5:16]
        cleaned.append((role, timestamp, content))

    blocks: List[Tuple[str, str, List[str]]] = []
    for role, timestamp, content in cleaned:
        if blocks and blocks[-1][0] == role:
            blocks[-1][2].append(content)
        else:
            blocks.append((role, timestamp, [content]))

    if not blocks:
        return []
    title = str(conversation.get("title") or conversation.get("buyer_user_id") or conversation.get("cid") or "会话")
    item_title = str(conversation.get("item_title") or "未知商品")
    cid = str(conversation.get("cid") or "")
    lines = [f"## {title} | {item_title} | CID {cid}"]
    for role, timestamp, contents in blocks:
        lines.append(f"{timestamp} {role}: {' / '.join(contents)}")
    return lines


def write_compact_dialogues(data: Dict[str, Any], output: Path) -> Dict[str, int]:
    lines = [
        "# 闲鱼对话压缩语料",
        "规则：去掉寒暄、确认词、重复模板和长链接；连续同方消息合并；媒体保留类型标记。",
        "",
    ]
    kept_conversations = 0
    for conversation in data.get("conversations") or []:
        block = compact_conversation(conversation)
        if not block:
            continue
        kept_conversations += 1
        lines.extend(block)
        lines.append("")
    text = "\n".join(lines).strip() + "\n"
    output.write_text(text, encoding="utf-8")
    return {"conversations": kept_conversations, "characters": len(text), "lines": len(lines)}


def clean_candidate_block(text: Any) -> str:
    parts = []
    for raw_line in str(text or "").splitlines():
        cleaned = clean_text(raw_line)
        if not cleaned or is_low_signal(cleaned) or cleaned in parts:
            continue
        parts.append(cleaned)
    return " / ".join(parts)


def candidate_key(candidate: Dict[str, Any]) -> Tuple[str, str, str]:
    need = re.sub(r"[\W_]+", "", clean_candidate_block(candidate.get("need")).lower())
    return str(candidate.get("cid") or ""), str(candidate.get("status") or ""), need


def write_requirements_only(candidates: Iterable[Dict[str, Any]], output: Path) -> Dict[str, int]:
    lines = [
        "# 未满足需求压缩语料",
        "仅保留：明确不支持、临时绕路、失败未解决、未回复。",
        "",
    ]
    seen = set()
    kept = 0
    for candidate in candidates:
        if candidate.get("status") == "可能已满足，需人工复核":
            continue
        key = candidate_key(candidate)
        if not key[2] or key in seen:
            continue
        seen.add(key)
        need = clean_candidate_block(candidate.get("need"))
        response = clean_candidate_block(candidate.get("seller_response")) or "[未回复]"
        follow_up = clean_candidate_block(candidate.get("buyer_follow_up"))
        categories = "、".join(candidate.get("categories") or ["其他"])
        date = str(candidate.get("started_at") or "")[:16]
        item = str(candidate.get("item_title") or "未知商品")
        cid = str(candidate.get("cid") or "")
        lines.append(f"[{candidate.get('status')} | {categories}] {date} | {item} | CID {cid}")
        lines.append(f"买家: {need}")
        lines.append(f"回复: {response}")
        if follow_up:
            lines.append(f"后续: {follow_up}")
        lines.append("")
        kept += 1
    text = "\n".join(lines).strip() + "\n"
    output.write_text(text, encoding="utf-8")
    return {"requirements": kept, "characters": len(text), "lines": len(lines)}


def write_summary(report_path: Path, output: Path) -> Dict[str, int]:
    text = report_path.read_text(encoding="utf-8")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    output.write_text(text, encoding="utf-8")
    return {"characters": len(text), "lines": text.count("\n")}


def main() -> None:
    parser = argparse.ArgumentParser(description="压缩闲鱼聊天语料，降低模型输入 token")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--candidates", default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = json.loads(Path(args.input).expanduser().read_text(encoding="utf-8"))
    candidates = json.loads(Path(args.candidates).expanduser().read_text(encoding="utf-8"))
    output_dir = Path(args.out).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    compact_stats = write_compact_dialogues(data, output_dir / "all_dialogues_compact.txt")
    requirements_stats = write_requirements_only(candidates, output_dir / "requirements_only.txt")
    summary_stats = write_summary(
        Path(args.report).expanduser(), output_dir / "requirements_summary.txt"
    )
    stats = {
        "source": args.input,
        "compact_dialogues": compact_stats,
        "requirements_only": requirements_stats,
        "requirements_summary": summary_stats,
    }
    (output_dir / "compression_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
