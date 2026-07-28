from __future__ import annotations

import argparse
import json
from pathlib import Path

from .build_chat_reader import build_slim_data
from xianyu_web.paths import CHAT_READER_DIR, EXPORTS_DIR


DEFAULT_SOURCE = str(EXPORTS_DIR / "xianyu_chats_full_20260714" / "xianyu_chats.json")
DEFAULT_TARGET = str(CHAT_READER_DIR / "src" / "chat_data.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 React 聊天阅读器的数据文件")
    parser.add_argument("--input", default=DEFAULT_SOURCE, help=f"输入 JSON，默认 {DEFAULT_SOURCE}")
    parser.add_argument("--target", default=DEFAULT_TARGET, help=f"输出数据文件，默认 {DEFAULT_TARGET}")
    args = parser.parse_args()

    source = Path(args.input).expanduser()
    target = Path(args.target).expanduser()
    data = json.loads(source.read_text(encoding="utf-8"))
    slim = build_slim_data(data)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"已生成阅读器数据：{target}（{target.stat().st_size / 1024 / 1024:.2f} MB）")


if __name__ == "__main__":
    main()
