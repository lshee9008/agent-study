#!/usr/bin/env bash
# [맥 터미널에서 실행] 설치·설정 상태를 점검해 logs/doctor.txt 에 기록 (토큰 값은 출력하지 않음)
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
OUT=logs/doctor.txt; mkdir -p logs; : > "$OUT"
ok(){ echo "✅ $*" | tee -a "$OUT"; }
ng(){ echo "❌ $*" | tee -a "$OUT"; }
info(){ echo "ℹ️  $*" | tee -a "$OUT"; }

echo "== 시스템 ==" | tee -a "$OUT"
info "macOS $(sw_vers -productVersion), $(uname -m)"
info "칩: $(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
[ "$(sysctl -n sysctl.proc_translated 2>/dev/null)" = "1" ] && ng "이 터미널은 Rosetta(인텔 모드)로 실행 중" || ok "터미널 네이티브(arm64)"
info "디스크 여유: $(df -h ~ | awk 'NR==2{print $4}')"

echo "== 필수 프로그램 ==" | tee -a "$OUT"
command -v brew >/dev/null && ok "Homebrew $(brew --version | head -1)" || ng "Homebrew 없음"
curl -s -o /dev/null -m 10 https://integrate.api.nvidia.com/v1/models && ok "NVIDIA API 연결됨" || ng "NVIDIA API 연결 안 됨 (인터넷 확인)"
if command -v docker >/dev/null; then
  ok "Docker CLI $(docker --version)"
  docker info >/dev/null 2>&1 && ok "Docker 엔진 실행 중" || ng "Docker 엔진 꺼져 있음 (Docker Desktop 실행 필요)"
  docker compose version >/dev/null 2>&1 && ok "docker compose $(docker compose version --short)" || ng "docker compose 없음"
else ng "Docker 없음"; fi
command -v envsubst >/dev/null && ok "envsubst 있음" || ng "envsubst 없음 (brew install gettext)"
echo "== .env ==" | tee -a "$OUT"
if [ -f .env ]; then
  set -a; source .env; set +a
  for k in NVIDIA_API_KEY NVIDIA_MODEL GITHUB_PAT NOTION_TOKEN VELOG_ACCESS_TOKEN VELOG_REFRESH_TOKEN; do
    v="${!k}"; [ -n "$v" ] && ok "$k 입력됨 (${#v}자)" || ng "$k 비어 있음"
  done
  info "현재 NVIDIA_MODEL=$NVIDIA_MODEL"
  if [ -n "${NVIDIA_API_KEY:-}" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -m 60 https://integrate.api.nvidia.com/v1/chat/completions \
      -H "Authorization: Bearer $NVIDIA_API_KEY" -H 'Content-Type: application/json' \
      -d "{\"model\":\"$NVIDIA_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}")
    [ "$code" = 200 ] && ok "NVIDIA 키·모델 호출 성공" || ng "NVIDIA 호출 실패 (HTTP $code: 401=키 오류, 404=모델 ID 오류)"
  fi
else ng ".env 없음"; fi

echo "== 대상 ==" | tee -a "$OUT"
n=$(grep -cE '^\s+- name:' workspace/sources.yaml); p=$(grep -cE '^\s+- title:' workspace/sources.yaml)
(( n > 0 )) && ok "GitHub 레포 ${n}개" || ng "sources.yaml 에 레포 없음"
info "Notion 페이지 ${p}개"
echo; echo "결과 저장: $OUT  → Claude에게 '점검 끝' 이라고 알려주세요"
