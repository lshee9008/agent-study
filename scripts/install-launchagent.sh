#!/usr/bin/env bash
# 로그인 시 + 1시간마다 run-if-due.sh 를 호출하도록 등록 (맥이 켜져 있을 때만 동작)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LABEL=com.seungko.hermes-velog
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>$ROOT/scripts/run-if-due.sh</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>3600</integer>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✅ 등록 완료: 로그인 시 + 1시간마다 실행 조건을 확인합니다."
echo "   지금 바로 확인: launchctl kickstart gui/$(id -u)/$LABEL"
