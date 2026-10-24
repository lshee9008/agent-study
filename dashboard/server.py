#!/usr/bin/python3
"""Hermes 개발일지 대시보드 — 로컬 전용 관리 서버 (파이썬 표준 라이브러리만 사용)

    /usr/bin/python3 dashboard/server.py        → http://127.0.0.1:8765

- 127.0.0.1 에만 열림. 모든 /api 요청은 서버 시작 때 만든 키(X-Dash-Key)가 있어야 함
  (다른 웹사이트가 몰래 실행·설정 변경을 못 하게)
- 토큰 값은 절대 화면으로 내보내지 않음 (길이·만료일만)
"""
import base64
import json
import os
import re
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("DASHBOARD_PORT", "8765"))
KEY = secrets.token_urlsafe(24)
LABEL = "com.seungko.hermes-velog"
ENV_FILE = ROOT / ".env"
SOURCES = ROOT / "workspace" / "sources.yaml"
DRAFTS = ROOT / "workspace" / "drafts"
STAMP = ROOT / "workspace" / ".last_success"
LOGS = ROOT / "logs"
RUNS_DIR = LOGS / "runs"
LEDGER = LOGS / "runs.jsonl"
LOCK = LOGS / ".lock"
CURRENT = LOGS / ".current"
PATH = "/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# 2026-10-24 이 계정에서 툴 호출을 직접 확인한 모델
MODELS = [
    {"id": "z-ai/glm-5.3-flash", "note": "툴 호출 성공 · 1.9초"},
    {"id": "minimaxai/minimax-m3.1-flash", "note": "툴 호출 성공 · 2.8초"},
    {"id": "openai/gpt-oss-20b", "note": "툴 호출 성공 · 3.1초"},
    {"id": "deepseek-ai/deepseek-v4.1-flash", "note": "툴 호출 성공 · 느림(52초)"},
]
TOKEN_KEYS = ["NVIDIA_API_KEY", "GITHUB_PAT", "NOTION_TOKEN", "VELOG_ACCESS_TOKEN", "VELOG_REFRESH_TOKEN"]
NOISE = re.compile(
    r"s6-rc:|cont-init:|reconcile:|\[supervise-perms\]|/package/admin/s6|\[stage2\]|Syncing bundled skills|^Done: \d+ new|"
    r"^\s+\+ \S+$|^ ?Container |^ ?Volume |gateway\.run: Shutdown context|Gateway Starting|"
    r"Messaging platforms|Press Ctrl\+C|^[┌├└│]|\[config-migrate\]|^Config version"
)

_lock = threading.Lock()
_docker_cache = {"t": 0.0, "ok": False}


# ---------- helpers ----------
def sh(args, timeout=60, input_text=None):
    env = dict(os.environ, PATH=PATH)
    try:
        p = subprocess.run(args, cwd=str(ROOT), env=env, input=input_text, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "시간 초과"


def read_env():
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            m = re.match(r"^([A-Z_]+)=(.*)$", line)
            if m:
                out[m.group(1)] = re.sub(r"\s+#.*$", "", m.group(2)).strip()
    return out


def set_env_value(key, value):
    t = ENV_FILE.read_text()
    if re.search(rf"^{key}=", t, re.M):
        t = re.sub(rf"^{key}=.*$", lambda m: f"{key}={value}", t, flags=re.M)
    else:
        t += f"\n{key}={value}\n"
    ENV_FILE.write_text(t)
    os.chmod(ENV_FILE, 0o600)


def jwt_exp(tok):
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return int(json.loads(base64.urlsafe_b64decode(p)).get("exp"))
    except Exception:
        return None


def docker_state():
    """on / sleeping(Docker Desktop 절전 모드: 첫 요청 때 ~20초 걸려 깨어남) / off"""
    if time.time() - _docker_cache["t"] > 20:
        code, _ = sh(["pgrep", "-f", "com.docker.backend"], timeout=5)
        if code != 0:
            st = "off"
        else:
            sock = str(Path.home() / ".docker" / "run" / "docker.sock")
            c, out = sh(["/usr/bin/curl", "-s", "-m", "3", "--unix-socket", sock, "http://localhost/_ping"], timeout=6)
            st = "on" if c == 0 and "OK" in out else "sleeping"
        _docker_cache.update(t=time.time(), state=st)
    return _docker_cache["state"]


def autorun_on():
    code, _ = sh(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], timeout=5)
    return code == 0


def on_ac_power():
    _, out = sh(["pmset", "-g", "batt"], timeout=5)
    return "AC Power" in out


def running_id():
    if LOCK.exists():
        return CURRENT.read_text().strip() if CURRENT.exists() else "starting"
    return None


def read_ledger():
    rows = []
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return list(reversed(rows))


def parse_repos(text):
    repos, in_repos = [], False
    for line in text.splitlines():
        if re.match(r"^\s{2}repos:\s*$", line):
            in_repos = True
            continue
        if in_repos:
            if re.match(r"^\S", line) or re.match(r"^\s{2}\S", line):
                break
            m = re.match(r"^\s{4}- name:\s*(\S+)", line)
            if m:
                repos.append({"name": m.group(1), "series": None})
                continue
            m = re.match(r"^\s{6}series:\s*(.+?)\s*(#.*)?$", line)
            if m and repos:
                repos[-1]["series"] = m.group(1)
    return repos


def safe_name(name):
    return bool(re.match(r"^[A-Za-z0-9._-]{1,100}$", name or ""))


# ---------- views ----------
def api_status():
    env = read_env()
    interval = int(re.sub(r"\D", "", env.get("RUN_INTERVAL_DAYS", "7")) or 7)
    last = int(STAMP.read_text().strip()) if STAMP.exists() else None
    tokens = []
    now = time.time()
    for k in TOKEN_KEYS:
        v = env.get(k, "")
        item = {"key": k, "set": bool(v), "length": len(v)}
        if k.startswith("VELOG_") and v:
            exp = jwt_exp(v)
            if exp:
                item["expires"] = exp
                item["days_left"] = round((exp - now) / 86400, 1)
        tokens.append(item)
    return {
        "autorun": autorun_on(),
        "running": running_id(),
        "last_success": last,
        "next_due": (last + interval * 86400) if last else None,
        "interval_days": interval,
        "require_ac": env.get("REQUIRE_AC_POWER", "true").startswith("true"),
        "on_ac": on_ac_power(),
        "docker": docker_state(),
        "model": env.get("NVIDIA_MODEL", ""),
        "models": MODELS,
        "tokens": tokens,
    }


def api_runs():
    rows = read_ledger()
    cur = running_id()
    return {"running": cur, "runs": rows[:50]}


def api_run_log(run_id, raw=False):
    if not re.match(r"^\d{8}-\d{6}$", run_id):
        return None
    f = RUNS_DIR / f"{run_id}.log"
    if not f.exists():
        return {"text": "", "exists": False}
    lines = f.read_text(errors="replace").splitlines()
    if not raw:
        lines = [l for l in lines if not NOISE.search(l)]
        out, blank = [], False
        for l in lines:
            if not l.strip():
                if blank:
                    continue
                blank = True
            else:
                blank = False
            out.append(l)
        lines = out
    return {"text": "\n".join(lines[-600:]), "exists": True}


def api_drafts():
    items = []
    for p in sorted(DRAFTS.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
        items.append({"name": p.name, "raw": p.name.startswith("_raw"), "size": p.stat().st_size,
                      "mtime": int(p.stat().st_mtime)})
    return {"drafts": items}


def api_draft(name):
    if not re.match(r"^[\w.\-]+\.md$", name):
        return None
    p = DRAFTS / name
    if not p.exists():
        return None
    return {"name": name, "text": p.read_text(errors="replace")}


def api_sources():
    text = SOURCES.read_text()
    m = re.search(r"^lookback_days:\s*(\d+)", text, re.M)
    return {"text": text, "repos": parse_repos(text), "lookback_days": int(m.group(1)) if m else 7}


def start_run():
    with _lock:
        if running_id():
            return {"ok": False, "message": "이미 실행 중이에요."}
        env = dict(os.environ, PATH=PATH, FORCE_RUN="true")
        subprocess.Popen(["/bin/bash", str(ROOT / "scripts" / "run-if-due.sh")], cwd=str(ROOT), env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(30):  # 잠금이 잡힐 때까지 잠깐 대기
            if LOCK.exists():
                break
            time.sleep(0.2)
        return {"ok": True, "message": "실행을 시작했어요."}


def set_autorun(on):
    script = "install-launchagent.sh" if on else "uninstall-launchagent.sh"
    code, out = sh(["/bin/bash", f"scripts/{script}"], timeout=30)
    return {"ok": code == 0, "message": out.strip().splitlines()[0] if out.strip() else ""}


def set_model(model):
    if model not in [m["id"] for m in MODELS] and not re.match(r"^[\w.-]+/[\w.:-]+$", model or ""):
        return {"ok": False, "message": "모델 ID 형식이 아니에요."}
    set_env_value("NVIDIA_MODEL", model)
    code, out = sh(["/bin/bash", "scripts/render-config.sh"], timeout=30)
    return {"ok": code == 0, "message": f"모델을 {model}(으)로 바꿨어요."}


def add_repo(name, series):
    if not safe_name(name):
        return {"ok": False, "message": "레포 이름은 영문·숫자·.-_ 만 쓸 수 있어요."}
    text = SOURCES.read_text()
    if name in [r["name"] for r in parse_repos(text)]:
        return {"ok": False, "message": "이미 있는 레포예요."}
    entry = f"    - name: {name}\n"
    if series:
        series = series.replace('"', "").replace("\n", " ").strip()[:80]
        entry += f'      series: "{series}"\n'
    new, n = re.subn(r"^(\s{2}repos:[^\n]*\n)", lambda m: m.group(1) + entry, text, count=1, flags=re.M)
    if not n:
        return {"ok": False, "message": "sources.yaml 에서 repos: 를 찾지 못했어요."}
    SOURCES.write_text(new)
    return {"ok": True, "message": f"{name} 추가"}


def remove_repo(name):
    if not safe_name(name):
        return {"ok": False, "message": "잘못된 이름"}
    lines = SOURCES.read_text().splitlines(keepends=True)
    out, skip = [], False
    for line in lines:
        if re.match(rf"^\s{{4}}- name:\s*{re.escape(name)}\s*$", line):
            skip = True
            continue
        if skip and re.match(r"^\s{6}\S", line):
            continue
        skip = False
        out.append(line)
    SOURCES.write_text("".join(out))
    return {"ok": True, "message": f"{name} 제거"}


def set_lookback(days):
    try:
        days = int(days)
    except (TypeError, ValueError):
        return {"ok": False, "message": "숫자를 입력하세요."}
    if not 1 <= days <= 60:
        return {"ok": False, "message": "1~60일 사이로 입력하세요."}
    text = re.sub(r"^lookback_days:\s*\d+", f"lookback_days: {days}", SOURCES.read_text(), flags=re.M)
    SOURCES.write_text(text)
    return {"ok": True, "message": f"최근 {days}일치를 정리해요."}


def save_sources(text):
    if "repos:" not in text or "publish_private:" not in text:
        return {"ok": False, "message": "repos: 와 publish_private: 항목은 지우면 안 돼요."}
    if re.search(r"^publish_private:\s*false", text, re.M):
        return {"ok": False, "message": "공개 발행(publish_private: false)은 대시보드에서 허용하지 않아요."}
    SOURCES.write_text(text if text.endswith("\n") else text + "\n")
    return {"ok": True, "message": "저장했어요."}


def save_tokens(text):
    if not text or not text.strip():
        return {"ok": False, "message": "붙여넣은 내용이 없어요."}
    code, out = sh(["/bin/bash", "scripts/set-tokens.sh"], timeout=120, input_text=text)
    saved = [l.strip() for l in out.splitlines() if "저장 (" in l or l.startswith("❌") or l.startswith("⚠️")]
    return {"ok": code == 0, "message": "\n".join(saved) or out.strip()[-400:]}


def run_check():
    code, out = sh(["/bin/bash", "scripts/doctor.sh"], timeout=120)
    out = out.replace("결과 저장: logs/doctor.txt  → Claude에게 '점검 끝' 이라고 알려주세요", "").strip()
    return {"ok": code == 0, "text": out}


# ---------- http ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "HermesDashboard/1"

    def log_message(self, fmt, *args):
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def _auth_ok(self):
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            return False
        return secrets.compare_digest(self.headers.get("X-Dash-Key", ""), KEY)

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 200_000:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {"error": "forbidden host"})
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            html = (ROOT / "dashboard" / "index.html").read_text().replace("__DASH_KEY__", KEY)
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if not path.startswith("/api/"):
            return self._send(404, {"error": "not found"})
        if not self._auth_ok():
            return self._send(401, {"error": "unauthorized"})
        q = urlparse(self.path).query
        if path == "/api/status":
            return self._send(200, api_status())
        if path == "/api/runs":
            return self._send(200, api_runs())
        m = re.match(r"^/api/runs/([\d-]+)/log$", path)
        if m:
            res = api_run_log(m.group(1), raw="raw=1" in q)
            return self._send(200 if res else 404, res or {"error": "not found"})
        if path == "/api/drafts":
            return self._send(200, api_drafts())
        m = re.match(r"^/api/drafts/(.+)$", path)
        if m:
            res = api_draft(unquote(m.group(1)))
            return self._send(200 if res else 404, res or {"error": "not found"})
        if path == "/api/sources":
            return self._send(200, api_sources())
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok() or not self._auth_ok():
            return self._send(401, {"error": "unauthorized"})
        path = urlparse(self.path).path
        b = self._body()
        routes = {
            "/api/run": lambda: start_run(),
            "/api/autorun": lambda: set_autorun(bool(b.get("on"))),
            "/api/model": lambda: set_model(str(b.get("model", ""))),
            "/api/repos/add": lambda: add_repo(str(b.get("name", "")).strip(), str(b.get("series", "")).strip()),
            "/api/repos/remove": lambda: remove_repo(str(b.get("name", "")).strip()),
            "/api/lookback": lambda: set_lookback(b.get("days")),
            "/api/sources": lambda: save_sources(str(b.get("text", ""))),
            "/api/tokens": lambda: save_tokens(str(b.get("text", ""))),
            "/api/check": lambda: run_check(),
        }
        fn = routes.get(path)
        if not fn:
            return self._send(404, {"error": "not found"})
        try:
            return self._send(200, fn())
        except Exception as e:  # 화면에 원인을 보여주되 서버는 계속 동작
            return self._send(500, {"ok": False, "message": f"오류: {e}"})


if __name__ == "__main__":
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"대시보드: http://127.0.0.1:{PORT}", flush=True)
    srv.serve_forever()
