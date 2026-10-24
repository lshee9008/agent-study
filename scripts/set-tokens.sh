#!/usr/bin/env bash
# 토큰들을 한꺼번에 붙여넣으면 종류를 알아서 구분해 .env 에 저장 (입력값은 화면에 안 보임)
#   nvapi-...        → NVIDIA_API_KEY
#   github_pat_...   → GITHUB_PAT
#   ntn_... / secret_ → NOTION_TOKEN
#   eyJ... (JWT)     → 내용의 sub 값으로 Velog access / refresh 구분
# 일부만 붙여넣으면 그것만 바뀌고 나머지는 기존 값 유지.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
chmod 600 .env

echo "토큰을 아무 형식으로나 붙여넣은 뒤, 새 줄에서 Ctrl-D 를 누르세요. (화면엔 안 보여요)"
stty -echo 2>/dev/null || true
INPUT=$(cat)
stty echo 2>/dev/null || true
echo

INPUT="$INPUT" python3 -I - <<'PY'
import os, re, base64, json
text = os.environ["INPUT"]
found = {}
def put(k, v):
    if k in found and found[k] != v:
        print(f"⚠️  {k} 후보가 여러 개 → 마지막 값 사용")
    found[k] = v
for v in re.findall(r"nvapi-[A-Za-z0-9_\-]+", text): put("NVIDIA_API_KEY", v)
for v in re.findall(r"github_pat_[A-Za-z0-9_]+", text): put("GITHUB_PAT", v)
for v in re.findall(r"\b(?:ntn_|secret_)[A-Za-z0-9]+", text): put("NOTION_TOKEN", v)
for v in re.findall(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", text):
    try:
        p = v.split(".")[1]; p += "=" * (-len(p) % 4)
        sub = json.loads(base64.urlsafe_b64decode(p)).get("sub", "")
    except Exception:
        sub = ""
    if sub == "access_token": put("VELOG_ACCESS_TOKEN", v)
    elif sub == "refresh_token": put("VELOG_REFRESH_TOKEN", v)
    else: print("⚠️  종류를 알 수 없는 eyJ... 토큰 1개는 무시")
if not found:
    print("❌ 알아볼 수 있는 토큰이 없어요. 다시 실행해 주세요."); raise SystemExit(1)
t = open(".env").read()
for k, v in found.items():
    if re.search(rf"^{k}=", t, re.M):
        t = re.sub(rf"^{k}=.*$", lambda m: f"{k}={v}", t, flags=re.M)
    else:
        t += f"\n{k}={v}\n"
    print(f"✅ {k} 저장 ({len(v)}자)")
open(".env", "w").write(t)
PY

echo; ./scripts/render-config.sh && ./scripts/doctor.sh | sed -n '/== .env ==/,$p'
