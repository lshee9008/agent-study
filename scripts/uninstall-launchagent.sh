#!/usr/bin/env bash
LABEL=com.seungko.hermes-velog
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "✅ 자동 실행 해제"
