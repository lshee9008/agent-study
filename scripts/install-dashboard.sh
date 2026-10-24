#!/usr/bin/env bash
# 대시보드를 로그인 시 자동으로 켜고(꺼지면 다시 켬) 브라우저로 연다.
#   해제: ./scripts/install-dashboard.sh --uninstall
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LABEL=com.seungko.hermes-dashboard
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT=8765

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$PLIST"; echo "✅ 대시보드 자동 실행 해제"; exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" logs
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/usr/bin/python3</string><string>$ROOT/dashboard/server.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/logs/dashboard.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/dashboard.log</string>
</dict></plist>
PL
launchctl bootstrap "gui/$(id -u)" "$PLIST"
for i in {1..20}; do curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.5; done
echo "✅ 대시보드: http://127.0.0.1:$PORT  (로그인할 때마다 자동으로 켜져요)"
[ "${NO_OPEN:-}" = "1" ] || open "http://127.0.0.1:$PORT"
