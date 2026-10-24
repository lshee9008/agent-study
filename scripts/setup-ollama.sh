#!/usr/bin/env bash
# [맥 호스트에서 실행] 모델 pull + 64K 컨텍스트 파생 모델 생성 + Ollama 환경변수 설정
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo ".env 가 없습니다. cp .env.example .env 후 값을 채우세요."; exit 1; }
set -a; source .env; set +a

command -v ollama >/dev/null || { echo "Ollama 미설치: brew install ollama 또는 ollama.com 에서 설치"; exit 1; }

if ollama list | awk 'NR>1{print $1}' | grep -qx "$OLLAMA_BASE_MODEL"; then
  echo "▶ $OLLAMA_BASE_MODEL 이미 있음 (다운로드 생략)"
else
  echo "▶ pull $OLLAMA_BASE_MODEL"; ollama pull "$OLLAMA_BASE_MODEL"
fi

CAPS=$(ollama show "$OLLAMA_BASE_MODEL" | awk '/Capabilities/{f=1;next} f&&NF==0{exit} f{print $1}' | tr '\n' ' ')
echo "   capabilities: $CAPS"
if echo "$CAPS" | grep -qw "tools"; then
  echo "✅ $OLLAMA_BASE_MODEL 툴 콜링 지원"
else
  echo "❌ $OLLAMA_BASE_MODEL 은 툴 콜링 미지원 → .env 의 OLLAMA_BASE_MODEL 을 qwen3:8b 로 바꾸고 다시 실행하세요"; exit 1
fi

TMP=$(mktemp)
sed "s|__BASE_MODEL__|$OLLAMA_BASE_MODEL|" ollama/Modelfile.template > "$TMP"
echo "▶ create $OLLAMA_MODEL (num_ctx 65536)"
ollama create "$OLLAMA_MODEL" -f "$TMP"

# Ollama 맥 앱이 읽는 환경변수 (앱 재시작 필요)
launchctl setenv OLLAMA_CONTEXT_LENGTH 65536
launchctl setenv OLLAMA_HOST 0.0.0.0:11434   # 도커 컨테이너에서 접근 허용
launchctl setenv OLLAMA_FLASH_ATTENTION 1     # 긴 컨텍스트 메모리 절약
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0    # KV 캐시 절반 크기 (16GB 맥 대응)

echo "✅ 완료. 메뉴바에서 Ollama 를 종료 후 다시 실행하세요."
echo "   확인: curl http://localhost:11434/api/tags"
