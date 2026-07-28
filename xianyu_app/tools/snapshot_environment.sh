#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT="${1:-$APP_WORKSPACE/docs/ENVIRONMENT.local.md}"
OUTER_APP="${XIANYU_APP_PATH:-/Applications/闲鱼.app}"
RUNNER_APP="${XIANYU_RUNNER_APP:-$OUTER_APP/Wrapper/Runner.app}"
BINARY="${XIANYU_BINARY:-$RUNNER_APP/Runner}"

plist_value() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$RUNNER_APP/Info.plist" 2>/dev/null || true
}

db_paths=()
uids=()
for data_root in "$HOME"/Library/Containers/*/Data; do
  for path in \
    "$data_root"/Documents/fleamarket_idlefish_im_*.db \
    "$data_root"/Library/Caches/if_msg_xstore_user_*.db \
    "$data_root"/Documents/AIMData/*@goofish/database/im.sqlite; do
    [[ -e "$path" ]] || continue
    db_paths+=("$path")
    if [[ "$path" =~ fleamarket_idlefish_im_([0-9]+)\.db$ ]]; then
      [[ "${BASH_REMATCH[1]}" == "0" ]] || uids+=("${BASH_REMATCH[1]}")
    elif [[ "$path" =~ if_msg_xstore_user_([0-9]+)\.db$ ]]; then
      [[ "${BASH_REMATCH[1]}" == "0" ]] || uids+=("${BASH_REMATCH[1]}")
    elif [[ "$path" =~ /([0-9]+)@goofish/database/im\.sqlite$ ]]; then
      uids+=("${BASH_REMATCH[1]}")
    fi
  done
done

unique_uids="$(printf '%s\n' "${uids[@]:-}" | sed '/^$/d' | sort -u | paste -sd ', ' -)"
runner_pids="$(pgrep -f 'Runner\.app/Runner' 2>/dev/null | paste -sd ', ' - || true)"
entitlements="$(codesign -d --entitlements :- "$RUNNER_APP" 2>/dev/null || true)"
if grep -q '<key>get-task-allow</key>' <<< "$entitlements"; then
  get_task_allow="present"
else
  get_task_allow="absent"
fi

mkdir -p "$(dirname "$OUTPUT")"
{
  echo '# Local App environment snapshot'
  echo
  echo '> Local-only operational data. This file is ignored by Git.'
  echo
  echo "- Generated: \`$(date '+%Y-%m-%d %H:%M:%S %z')\`"
  echo "- Outer App: \`$OUTER_APP\`"
  echo "- Runner App: \`$RUNNER_APP\`"
  echo "- Binary: \`$BINARY\`"
  echo "- Bundle ID: \`$(plist_value CFBundleIdentifier)\`"
  echo "- Version: \`$(plist_value CFBundleShortVersionString)\`"
  echo "- Build: \`$(plist_value CFBundleVersion)\`"
  echo "- Binary SHA-256: \`$(shasum -a 256 "$BINARY" | awk '{print $1}')\`"
  echo "- Architecture: \`$(file "$BINARY" | sed 's/.*: //')\`"
  echo "- Running PID(s): \`${runner_pids:-none}\`"
  echo "- Discovered account UID(s): \`${unique_uids:-none}\`"
  echo "- Frida: \`$(frida --version 2>/dev/null || echo missing)\`"
  echo "- Python: \`$(python3 --version 2>&1)\`"
  echo "- Node: \`$(node --version 2>/dev/null || echo missing)\`"
  echo "- SIP: \`$(csrutil status 2>/dev/null || echo unknown)\`"
  echo "- Developer tools: \`$(DevToolsSecurity -status 2>/dev/null || echo unknown)\`"
  echo "- get-task-allow entitlement: \`$get_task_allow\`"
  echo
  echo '## Observed IM stores'
  echo
  if ((${#db_paths[@]})); then
    printf -- '- `%s`\n' "${db_paths[@]}"
  else
    echo '- none'
  fi
} > "$OUTPUT"

echo "Environment snapshot written to: $OUTPUT"
