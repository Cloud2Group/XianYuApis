#!/usr/bin/env bash
set -euo pipefail

# Extract only the Objective-C metadata blocks needed by the single-account
# IM bridge.  `otool -ov` is intentionally streamed: the complete dump is
# hundreds of megabytes on the current Runner binary.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$APP_WORKSPACE/research/generated}"
OUTER_APP="${XIANYU_APP_PATH:-/Applications/闲鱼.app}"
RUNNER_APP="${XIANYU_RUNNER_APP:-$OUTER_APP/Wrapper/Runner.app}"
BINARY="${XIANYU_BINARY:-$RUNNER_APP/Runner}"
OUTPUT_FILE="${OUTPUT_FILE:-$OUTPUT_DIR/aim_objc_types.txt}"

if [[ ! -f "$BINARY" ]]; then
  echo "Runner binary not found: $BINARY" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

# Keep the selector/type evidence small and reviewable.  The class names are
# static metadata only; no runtime values or account material are collected.
otool -ov "$BINARY" \
  | awk '
    BEGIN { capture = 0 }
    /^        name[[:space:]]+0x[0-9a-f]+[[:space:]]+AIMPubMsg(Service|Content|TextContent|ReplyContent|SendMessage|SendReplyMessage|Reference|SimpleContent)[[:space:]]*$/ {
      capture = 1
      print "## " $0
      next
    }
    capture {
      print
      if ($0 ~ /^Meta Class$/) {
        capture = 0
        print ""
      }
    }
  ' > "$OUTPUT_FILE"

# `otool -ov` output differs slightly between Xcode/macOS releases: some
# versions append a space to ``layout map`` lines and an extra blank line at
# EOF.  Normalize those presentation-only differences so version comparisons
# and Git checks focus on selectors, encodings and fields.
awk '
  {
    sub(/[ \t]+$/, "")
    lines[NR] = $0
  }
  END {
    last = NR
    while (last > 0 && lines[last] == "") last--
    for (i = 1; i <= last; i++) print lines[i]
  }
' "$OUTPUT_FILE" > "$OUTPUT_FILE.tmp"
mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"

echo "Objective-C AIM type evidence written to: $OUTPUT_FILE"
