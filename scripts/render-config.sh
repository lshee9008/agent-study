#!/usr/bin/env bash
# .env → hermes-data/config.yaml, .env 렌더링 + 스킬 복사
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env 가 없습니다."; exit 1; }
set -a; source .env; set +a
command -v envsubst >/dev/null || { echo "envsubst 필요: brew install gettext"; exit 1; }

VARS='${NVIDIA_MODEL} ${GITHUB_PAT} ${NOTION_TOKEN} ${VELOG_ACCESS_TOKEN} ${VELOG_REFRESH_TOKEN}'
envsubst "$VARS" < config/config.template.yaml > hermes-data/config.yaml

# Hermes 런타임 환경변수 (모델 API 키는 여기에만, 600 권한)
cat > hermes-data/.env <<ENV
HERMES_API_TIMEOUT=600
NVIDIA_API_KEY=${NVIDIA_API_KEY}
ENV

chmod 600 hermes-data/config.yaml hermes-data/.env
echo "✅ hermes-data/config.yaml 렌더링 완료. 변경 반영: docker compose restart"
