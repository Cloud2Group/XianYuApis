#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$APP_WORKSPACE/research/generated}"
OUTER_APP="${XIANYU_APP_PATH:-/Applications/闲鱼.app}"
RUNNER_APP="${XIANYU_RUNNER_APP:-$OUTER_APP/Wrapper/Runner.app}"
BINARY="${XIANYU_BINARY:-$RUNNER_APP/Runner}"

if [[ ! -f "$BINARY" ]]; then
  echo "Runner binary not found: $BINARY" >&2
  exit 2
fi

mkdir -p "$OUTPUT_DIR"

plist_value() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$RUNNER_APP/Info.plist" 2>/dev/null || true
}

{
  echo "generated_at=$(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "outer_app=$OUTER_APP"
  echo "runner_app=$RUNNER_APP"
  echo "binary=$BINARY"
  echo "bundle_id=$(plist_value CFBundleIdentifier)"
  echo "version=$(plist_value CFBundleShortVersionString)"
  echo "build=$(plist_value CFBundleVersion)"
  echo "architecture=$(file "$BINARY")"
  echo "binary_size=$(stat -f '%z' "$BINARY")"
  echo "binary_sha256=$(shasum -a 256 "$BINARY" | awk '{print $1}')"
} > "$OUTPUT_DIR/app_metadata.txt"

otool -L "$BINARY" > "$OUTPUT_DIR/linked_libraries.txt"
codesign -d --entitlements :- "$RUNNER_APP" \
  > "$OUTPUT_DIR/codesign_entitlements.plist" 2>/dev/null || true

LC_ALL=C strings -a "$BINARY" \
  | grep -E 'AIMPubMsg|AIMMsg(Service|Listener|Notify|Hook)|NotifyAddedNewMsg|OnAddedMessages|PreReceiveMessage|PreSendMessage|CipherDB|tls-goofish\.dingtalk\.com|wss-goofish\.dingtalk\.com' \
  | awk 'length($0) < 1200' \
  | sort -u \
  > "$OUTPUT_DIR/aim_static_strings.txt" || true

LC_ALL=C strings -a "$BINARY" \
  | grep -E '^AIM(PubMsg|Msg|Manager|PubConv|PubConversation|Extension|Media|Search|Trace)' \
  | awk 'length($0) < 800' \
  | sort -u \
  > "$OUTPUT_DIR/aim_class_inventory.txt" || true

LC_ALL=C strings -a "$BINARY" \
  | grep -E 'AIM(PubMsgService|MsgServiceEx|MsgRPC|ConvRPCService|ExtensionService|PubMsg.*With|PubConv.*With)' \
  | awk 'length($0) < 1200' \
  | sort -u \
  > "$OUTPUT_DIR/aim_action_focus.txt" || true

LC_ALL=C strings -a "$BINARY" \
  | grep -Eo 'mtop\.[A-Za-z0-9._-]+' \
  | sort -u \
  > "$OUTPUT_DIR/mtop_all.txt" || true

grep -Ei 'idle|goofish|fleamarket|message|chat|session|publish|delivery' \
  "$OUTPUT_DIR/mtop_all.txt" \
  > "$OUTPUT_DIR/mtop_relevant.txt" || true

LC_ALL=C strings -a "$BINARY" \
  | grep -Eo '(tls|wss|https)://[^[:space:]"<>]+' \
  | grep -Ei 'goofish|dingtalk|taobao|alibaba' \
  | sed 's/[),;]$//' \
  | sort -u \
  > "$OUTPUT_DIR/network_endpoints.txt" || true

# Objective-C type encodings are useful for the dynamic bridge.  Keep this as
# a separate streamed pass so the main reports remain readable.
if command -v otool >/dev/null 2>&1; then
  OUTPUT_DIR="$OUTPUT_DIR" XIANYU_APP_PATH="$OUTER_APP" \
    XIANYU_RUNNER_APP="$RUNNER_APP" XIANYU_BINARY="$BINARY" \
    "$SCRIPT_DIR/extract_aim_objc_types.sh" || true
fi

(
  cd "$OUTPUT_DIR"
  files=( \
    app_metadata.txt \
    linked_libraries.txt \
    codesign_entitlements.plist \
    aim_static_strings.txt \
    aim_class_inventory.txt \
    aim_action_focus.txt \
    mtop_all.txt \
    mtop_relevant.txt \
    network_endpoints.txt \
  )
  [[ -f aim_objc_types.txt ]] && files+=(aim_objc_types.txt)
  shasum -a 256 "${files[@]}" > SHA256SUMS
)

echo "Static evidence written to: $OUTPUT_DIR"
