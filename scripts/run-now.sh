#!/usr/bin/env bash
# 주기·전원 조건과 상관없이 지금 바로 한 번 실행
cd "$(dirname "$0")/.."
FORCE_RUN=true ./scripts/run-if-due.sh
tail -n 30 "logs/run-$(date +%Y%m%d).log"
