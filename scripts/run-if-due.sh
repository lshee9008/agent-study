#!/usr/bin/env bash
# 맥이 켜져 있을 때 launchd가 1시간마다 호출합니다.
# 조건이 맞을 때만 개발일지를 작성·발행하고, 아니면 조용히 종료합니다.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
cd "$(dirname "$0")/.."
ROOT=$(pwd)
LOG="$ROOT/logs/run-$(date +%Y%m%d).log"
STAMP="$ROOT/workspace/.last_success"
LOCK="$ROOT/logs/.lock"
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
notify(){ osascript -e "display notification \"$1\" with title \"Velog 개발일지\"" >/dev/null 2>&1 || true; }

FORCE=${FORCE_RUN:-false}   # run-now.sh 에서 true
[ -f .env ] || exit 0
set -a; source .env; set +a
INTERVAL=${RUN_INTERVAL_DAYS:-7}

# ① 아직 때가 안 됐으면 종료
if [ "$FORCE" != "true" ] && [ -f "$STAMP" ]; then
  last=$(cat "$STAMP"); now=$(date +%s)
  (( now - last < INTERVAL*86400 )) && exit 0
fi

# ② 배터리 상태면 다음 기회로
if [ "$FORCE" != "true" ] && [ "${REQUIRE_AC_POWER:-true}" = "true" ] && ! pmset -g batt | grep -q "AC Power"; then
  log "배터리 사용 중 → 건너뜀"; exit 0
fi

# ③ 중복 실행 방지
mkdir "$LOCK" 2>/dev/null || { log "이미 실행 중 → 건너뜀"; exit 0; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# ④ 인터넷(NVIDIA API) 확인, Docker 가 꺼져 있으면 켜기
curl -s -o /dev/null -m 10 https://integrate.api.nvidia.com/v1/models || { log "NVIDIA API 연결 안 됨 → 다음 기회로"; exit 0; }

if ! docker info >/dev/null 2>&1; then
  log "Docker 시작"; open -ga Docker
  for i in {1..60}; do docker info >/dev/null 2>&1 && break; sleep 3; done
fi
docker info >/dev/null 2>&1 || { log "Docker 응답 없음 → 중단"; exit 0; }

# ⑤ 실행 (caffeinate: 도중에 잠들지 않게)
RUN_ID=$(date +%Y%m%d-%H%M%S)
RUN_LOG="$ROOT/logs/runs/$RUN_ID.log"      # 실행 1회분 전체 출력 (대시보드에서 보기)
LEDGER="$ROOT/logs/runs.jsonl"             # 실행 기록 한 줄씩 (대시보드 목록)
mkdir -p "$ROOT/logs/runs"
START=$(date +%s)
TRIGGER=$([ "$FORCE" = "true" ] && echo manual || echo auto)
echo "$RUN_ID" > "$ROOT/logs/.current"

log "개발일지 작성 시작 (model=$NVIDIA_MODEL, run=$RUN_ID)"
notify "개발일지 작성을 시작해요"
PROMPT=$(cat prompts/weekly-devlog.md)
if caffeinate -i docker compose run --rm -T hermes \
     chat -Q -s velog-devlog --max-turns 80 --run-budget 1800 -q "$PROMPT" > "$RUN_LOG" 2>&1; then
  STATUS=success
  date +%s > "$STAMP"
  log "완료"; notify "비공개 글 발행 완료 — 대시보드에서 확인하세요"
else
  STATUS=failed
  log "실패 (다음 실행 때 재시도)"; notify "실패했어요. 대시보드에서 로그를 확인하세요"
fi
rm -f "$ROOT/logs/.current"

# 실행 기록 남기기 (발행된 Velog 주소는 출력에서 추출)
RUN_ID="$RUN_ID" STATUS="$STATUS" START="$START" TRIGGER="$TRIGGER" MODEL="$NVIDIA_MODEL" \
RUN_LOG="$RUN_LOG" LEDGER="$LEDGER" /usr/bin/python3 -I - <<'PY' || true
import json, os, re, time
text = open(os.environ["RUN_LOG"], errors="replace").read()
urls = sorted(set(re.findall(r"https://velog\.io/@[\w.-]+/[^\s)\]>\"'`*]+", text)))
rec = {"id": os.environ["RUN_ID"], "status": os.environ["STATUS"], "trigger": os.environ["TRIGGER"],
       "model": os.environ["MODEL"], "start": int(os.environ["START"]), "end": int(time.time()), "posts": urls}
with open(os.environ["LEDGER"], "a") as f:
    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
PY
