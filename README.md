# hermes-velog-agent

GitHub 커밋·PR과 Notion 기록을 모아 개발일지를 쓰고 Velog에 **비공개로** 발행하는
셀프호스팅 에이전트. [Hermes Agent](https://github.com/NousResearch/hermes-agent) + NVIDIA API(오픈소스 모델).

```
[GitHub MCP] ─┐
[Notion MCP] ─┼─> Hermes (Docker) ──> [Velog MCP] ──> 비공개 글
              │        │
              │   NVIDIA API (build.nvidia.com, 오픈소스 모델)
              └── launchd (맥 켜져 있을 때만, 주기 도래 시)
```

## 대시보드 (가장 쉬운 사용법)
브라우저에서 **http://127.0.0.1:8765** 를 열면 전부 관리할 수 있습니다. (로그인하면 자동으로 켜짐)

- ▶ 지금 실행 / 실행 중 실시간 로그
- 자동 실행 켜기·끄기, 마지막 성공·다음 실행 일정
- 실행 기록, 실행별 로그, 발행된 Velog 글 링크
- 초안 미리보기
- 대상 레포 추가·삭제, 정리 기간, sources.yaml 편집
- 모델 변경, 토큰 상태(Velog 만료일), 토큰 교체, 점검

처음 한 번만 등록: `./scripts/install-dashboard.sh` (해제: `./scripts/install-dashboard.sh --uninstall`)
내 맥(127.0.0.1)에서만 열리고, 토큰 값은 화면에 표시되지 않습니다.

## 폴더 구조
| 경로 | 내용 |
|---|---|
| `docker-compose.yml` | Hermes 컨테이너 (gateway + dashboard) |
| `.env.example` | 모델·토큰 설정 템플릿 |
| `config/config.template.yaml` | Hermes 설정(모델, MCP 3종) 템플릿 |
| `scripts/doctor.sh` | 설치·토큰·NVIDIA 호출 점검 → `logs/doctor.txt` |
| `ollama/`, `scripts/setup-ollama.sh` | (미사용) 로컬 모델로 돌아갈 때만 |
| `scripts/render-config.sh` | `.env` → `hermes-data/config.yaml` 렌더링 + 스킬 복사 |
| `skills/velog-devlog/SKILL.md` | 수집→작성→발행 절차 (Hermes 스킬) |
| `workspace/sources.yaml` | 정리할 레포·노션 페이지 목록 |
| `prompts/weekly-devlog.md` | 실행 프롬프트 |
| `scripts/run-if-due.sh` | 조건 확인 후 일회성 실행 |
| `scripts/install-launchagent.sh` | 맥 자동 실행 등록 |
| `scripts/run-now.sh` | 즉시 1회 실행 |
| `dashboard/` | 로컬 관리 대시보드 (`server.py`, `index.html`) |
| `scripts/install-dashboard.sh` | 대시보드 로그인 시 자동 실행 등록 |
| `scripts/set-tokens.sh` | 토큰 붙여넣기 → .env 저장 |

## 시작하기

### 1. 토큰 준비
```bash
cp .env.example .env   # 값 채우기
```
- **GitHub**: Fine-grained PAT, 대상 레포 Read-only
- **Notion**: Internal integration 토큰 → 정리할 페이지에서 `연결`로 integration 추가
- **Velog**: 로그인 후 쿠키의 `access_token`, `refresh_token` (refresh 약 30일)

### 2. 모델 (NVIDIA API)
- build.nvidia.com 로그인 → API Keys → Generate API Key → `.env`의 `NVIDIA_API_KEY`
- 모델은 `.env`의 `NVIDIA_MODEL` (기본 `z-ai/glm-5.3-flash`). 툴 콜링되는 오픈소스 모델이어야 MCP를 호출할 수 있음
  - 대안(툴 콜링 확인): `deepseek-ai/deepseek-v4.1-flash`, `minimaxai/minimax-m3.1-flash`, `openai/gpt-oss-20b`
- 확인: `./scripts/doctor.sh` → "NVIDIA 키·모델 호출 성공"
- 무료 크레딧·분당 호출 제한이 있음. 주 1회 실행이면 충분

### 3. 설정 렌더링 + Node 확인
```bash
./scripts/render-config.sh
docker compose run --rm hermes chat -Q -q "which npx 결과만 알려줘"   # 동작 확인 겸
```
- MCP 서버(npx)가 안 뜨면 `Dockerfile.node` 사용 (compose의 `image:`를 `build:`로 교체)

### 4. 첫 실행 (수동)
```bash
./scripts/run-now.sh
```
`workspace/drafts/`에 초안이 생기고 Velog에 비공개 글이 올라가면 성공.

### 5. 자동 실행 — 맥이 켜져 있을 때만
```bash
./scripts/install-launchagent.sh     # 해제: ./scripts/uninstall-launchagent.sh
```
상시 서버를 띄우지 않습니다. 맥 로그인 시 + 1시간마다 `run-if-due.sh`가 깨어나서:

1. 마지막 성공 후 `RUN_INTERVAL_DAYS`(기본 7일)가 안 지났으면 → 바로 종료
2. 배터리 사용 중이면 → 다음 기회로 (`REQUIRE_AC_POWER`)
3. 인터넷(NVIDIA API) 확인, Docker가 꺼져 있으면 켜고
4. 일회성 컨테이너(`docker compose run --rm`)로 개발일지 작성·발행, 끝나면 컨테이너 삭제
5. 성공하면 기록 남기고 알림

맥이 며칠 꺼져 있었다면 다음에 켰을 때 밀린 한 번을 실행합니다. 실패하면 기록을 남기지 않아서 1시간 뒤 다시 시도해요.
로그: `logs/run-YYYYMMDD.log`

## 꼭 확인할 것
- **데이터 전송**: 커밋·PR·노션 내용이 NVIDIA API로 전송됨. 민감한 레포는 sources.yaml에 넣지 않기.
- **다른 클라우드로 새지 않는지**: `hermes-data/.env`에는 `NVIDIA_API_KEY`만 넣음 (OpenRouter 등 다른 키 없음).
- **Velog 토큰 만료**: 발행 실패 시 `.env` 갱신 → `./scripts/render-config.sh` → `docker compose restart`.
- **비공식 API**: Velog 내부 GraphQL 변경 시 깨질 수 있음. 과도한 자동 발행 금지.
