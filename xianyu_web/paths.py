"""Stable local paths for the physically isolated Web workspace."""

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
EXPORTS_DIR = PACKAGE_ROOT / "exports"
RUNTIME_DIR = PACKAGE_ROOT / "runtime"
COOKIE_FILE = RUNTIME_DIR / ".xianyu_cookie"
AUTH_FILE = RUNTIME_DIR / ".xianyu_auth.json"
CHAT_READER_DIR = PACKAGE_ROOT / "chat_reader"
