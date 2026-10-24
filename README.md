<<<<<<< HEAD
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
=======
# AI Agent 학습 기록

이 문서는 `agent-study`를 만들면서 실제로 작성하고 실행한 코드와, 각 단계에서 바뀐 점을 기록합니다. 계획이나 다음에 할 일 대신 지금까지 익힌 내용을 정리합니다.

## 개발 환경 구성

프로젝트는 `uv init --name agent-study`로 초기화했습니다. 프로젝트 디렉터리 안에서 초기화했으므로 별도의 `cd agent-study`는 필요하지 않았습니다.

```bash
uv run main.py
```

처음 `main.py`는 `Hello from agent-study!`를 출력하는 기본 프로그램이었습니다. `uv run`은 프로젝트 가상환경에서 Python 파일을 실행합니다.

사용한 패키지:

```bash
uv add langchain langchain-google-genai python-dotenv langgraph
```

## 1. 규칙 기반 응답에서 도구 실행으로

처음에는 입력 문장에 특정 단어가 있는지 확인해 응답을 골랐습니다. `get_current_time()`과 `say_hello()`를 만들고 `run_agent()`에서 호출했습니다.

```python
from datetime import datetime


def get_current_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def say_hello() -> str:
    return "안녕하세요! 어떤 걸 도와드릴까요?"


def run_agent(user_message: str) -> str:
    if "시간" in user_message:
        return get_current_time()
    if "안녕" in user_message:
        return say_hello()
    return "아직 그 요청을 처리하는 방법을 몰라요."
```

이 단계에서 `run_agent()`는 입력을 판단하고, 별도의 함수는 실제 동작을 수행한다는 구조를 익혔습니다.

## 2. 반복 입력과 종료

한 번 입력하고 끝나는 대신 `while`문으로 대화를 반복했습니다. `strip()`은 입력 앞뒤 공백을 제거하고, `break`는 종료 조건이 맞으면 반복문을 끝냅니다.

```python
while True:
    user_message = input("나: ").strip()

    if user_message.lower() in {"exit", "종료"}:
        print("에이전트: 다음에 또 만나요!")
        break

    print(f"에이전트: {run_agent(user_message)}")
```

## 3. 도구 목록, 키워드 탐색, 함수 분리

도구가 늘어날 때마다 `if`문을 추가하는 대신 `TOOLS` 목록에 도구 정보를 모았습니다.

```python
TOOLS = [
    {"name": "time", "keywords": ["시간"], "function": get_current_time},
    {"name": "hello", "keywords": ["안녕"], "function": say_hello},
]


def find_tool(user_message: str) -> dict | None:
    for tool in TOOLS:
        if any(keyword in user_message for keyword in tool["keywords"]):
            return tool
    return None


def run_agent(user_message: str) -> str:
    tool = find_tool(user_message)
    if tool is None:
        return "아직 그 요청을 처리하는 방법을 몰라요."

    result = tool["function"]()
    return f"[{tool['name']} 도구 실행] {result}"
```

`any(keyword in user_message for keyword in tool["keywords"])`는 키워드를 하나씩 검사해, 하나라도 입력에 포함되어 있으면 참을 반환합니다. 기본 응답은 모든 도구를 확인한 뒤 반환해야 하므로 `for`문 바깥에 둡니다.

도구에 `description`을 추가하고 `도움말` 명령에서 도구 이름과 설명을 출력하는 기능도 만들었습니다. 도구 설명은 나중에 모델이 도구 용도를 판단하는 데 쓰입니다.

## 4. 대화 기록을 메모리와 JSON 파일에 저장

사용자 입력과 응답을 리스트에 쌍으로 저장했습니다.

```python
conversation_history.append({
    "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
    "user": user_message,
    "assistant": answer,
})
```

JSON으로 저장하고 불러오는 핵심 코드입니다.

```python
import json
from pathlib import Path

HISTORY_FILE = Path("conversation.json")


def load_history() -> list[dict[str, str]]:
    if not HISTORY_FILE.exists():
        return []
    with HISTORY_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history: list[dict[str, str]]) -> None:
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)
```

`ensure_ascii=False`는 한글을 그대로 저장하고, `indent=2`는 JSON을 읽기 좋게 정리합니다. 기록을 불러온 뒤 새 항목을 추가해 저장하면 실행이 바뀌어도 기록이 이어집니다. 타임스탬프는 각 항목이 만들어진 시각을 기록합니다.

추가로 `/history`는 최근 대화를 보여주고, `/clear`는 사용자의 확인을 받은 뒤 기록을 비우게 했습니다. JSON 파싱 오류와 파일 읽기 오류를 처리하는 방법, 도구 함수 오류를 잡아 대화를 계속하는 방법도 다뤘습니다.

## 5. Gemini API 키 설정과 LangChain 모델 호출

API 키를 코드에 직접 적지 않고 `.env` 파일에 보관했습니다.

```env
GOOGLE_API_KEY=실제_Gemini_API_키
```

`.gitignore`에는 키와 로컬 Python 파일을 추가했습니다.

```gitignore
.env
.env.*
.venv/
__pycache__/
*.py[cod]
*.sqlite
*.db
threads.json
.DS_Store
```

`python-dotenv`의 `load_dotenv()`가 `.env`의 변수를 환경에 불러오고, `ChatGoogleGenerativeAI`가 Gemini 모델을 생성합니다.

```python
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
response = model.invoke("파이썬에서 에이전트란 뭐야?")
print(response.content)
```

이때부터 정해진 키워드 응답 대신 모델이 자연어 요청에 답하게 됐습니다.

## 6. LangChain 도구 등록과 Gemini 도구 호출

`@tool`은 Python 함수를 LangChain 도구로 등록합니다. 함수 이름, 인자 타입, 문서 문자열이 도구의 용도와 입력 정보를 설명합니다.

```python
from datetime import datetime
from langchain.tools import tool


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
```

`bind_tools()`로 모델에 도구를 알려주면, 모델 응답의 `tool_calls`에 선택된 도구 호출 요청이 담길 수 있습니다. 모델이 도구를 선택하는 것과 Python 함수를 실제 실행하는 것은 별도 단계입니다.

```python
model_with_tools = model.bind_tools([get_current_time])
response = model_with_tools.invoke("지금 몇 시야?")

if response.tool_calls:
    for tool_call in response.tool_calls:
        tool_result = get_current_time.invoke(tool_call)
        print(tool_result.content)
```

모델이 도구를 선택했다는 사실만으로 함수가 자동 실행되는 것은 아닙니다. 애플리케이션 코드가 호출을 확인하고 실행해야 합니다.

## 7. 도구 결과를 메시지 흐름에 연결

도구 결과를 새 프롬프트 문자열로만 보내는 대신, 모델의 도구 호출 메시지와 도구 결과 메시지를 대화에 함께 기록하는 흐름을 실습했습니다.

```python
from langchain.messages import HumanMessage

messages = [HumanMessage(content=user_message)]
response = model_with_tools.invoke(messages)

if response.tool_calls:
    messages.append(response)  # 모델의 도구 호출 요청

    for tool_call in response.tool_calls:
        tool_result = get_current_time.invoke(tool_call)
        messages.append(tool_result)  # ToolMessage 결과

    final_response = model_with_tools.invoke(messages)
    print(final_response.content)
```

흐름은 `사용자 메시지 → 모델의 도구 호출 요청 → 도구 실행 결과 → 모델의 최종 답변`입니다. 도구 결과 메시지는 해당 도구 호출의 결과임을 모델에 알려줍니다.

## 8. 대화 문맥 유지

매 입력마다 새 메시지 목록을 만들면 이전 대화가 모델에 전달되지 않습니다. `messages`를 입력 반복문 바깥에서 한 번 만들고, 사용자 메시지와 모델 응답을 계속 추가하면 같은 실행 중 문맥을 이어갈 수 있습니다.

```python
messages = []  # 반복문 바깥에서 한 번만 만든다

while True:
    user_message = input("나: ").strip()
    messages.append(HumanMessage(content=user_message))

    response = model_with_tools.invoke(messages)
    # 일반 답변이면 AI 응답도 기록
    messages.append(response)
```

도구를 호출한 경우에는 모델의 도구 호출 응답과 도구 결과를 모두 추가한 뒤 다시 모델을 호출하고, 최종 AI 응답도 `messages`에 추가합니다. 이렇게 유지되는 메시지는 현재 프로그램 실행 중의 메모리이며, 종료 후에도 유지하려면 별도의 파일 또는 데이터베이스 저장이 필요합니다.

## 9. 도구 이름으로 함수를 찾아 실행

처음에는 도구 호출이 발생하면 시간 도구를 직접 실행했습니다. 도구가 여럿이면 모델이 요청한 도구 이름에 맞는 함수를 찾아야 하므로, 도구 이름을 키로 사용하는 딕셔너리를 만들었습니다.

```python
tools_by_name = {
    get_current_time.name: get_current_time,
}

for tool_call in response.tool_calls:
    tool_name = tool_call["name"]
    selected_tool = tools_by_name.get(tool_name)

    if selected_tool is None:
        print(f"등록되지 않은 도구 요청: {tool_name}")
        continue

    tool_result = selected_tool.invoke(tool_call)
    messages.append(tool_result)
```

`dict.get()`은 키가 없을 때 예외 대신 `None`을 돌려줍니다. 따라서 등록되지 않은 도구 요청을 확인하고 안전하게 건너뛸 수 있습니다. 도구를 추가할 때는 `model.bind_tools([...])`와 `tools_by_name` 양쪽에 등록해야 합니다.

## 10. Gemini 응답에서 텍스트만 출력

Gemini 연동 결과의 `response.content`는 항상 단순한 문자열인 것은 아닙니다. 텍스트와 서명 같은 메타데이터가 들어 있는 콘텐츠 블록 목록으로 반환될 수 있습니다. 전체 객체를 출력하면 텍스트 외 정보까지 터미널에 나타납니다.

```python
def get_text(content) -> str:
    """모델 응답 콘텐츠에서 텍스트 블록만 추출한다."""
    if isinstance(content, str):
        return content

    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
```

응답 출력 때는 `response.content` 대신 다음처럼 사용합니다.

```python
print(f"에이전트: {get_text(response.content)}")
```

문자열 응답이면 그대로 반환하고, 콘텐츠 블록 목록이면 `type`이 `text`인 블록의 `text`만 이어 붙입니다. 이 실습에서는 일반 응답과 도구 실행 후 최종 응답 양쪽에 적용했습니다.

## 11. 도구를 여러 번 부르는 루프와 제한

Gemini가 도구를 요청하고, 도구 결과를 받은 뒤 다시 다른 도구를 요청할 수 있습니다. 이때 `while response.tool_calls`로 도구 요청이 끝날 때까지 반복했습니다.

```python
tool_rounds = 0

while response.tool_calls and tool_rounds < MAX_TOOL_ROUNDS:
    tool_rounds += 1
    messages.append(response)

    for tool_call in response.tool_calls:
        selected_tool = tools_by_name.get(tool_call["name"])
        # 도구를 찾아 실행하고 ToolMessage를 messages에 추가

    response = model_with_tools.invoke(messages)
```

`MAX_TOOL_ROUNDS`는 한 사용자 요청에서 모델과 도구가 왕복하는 최대 횟수입니다. 한 라운드에서 여러 도구가 병렬이 아닌 순차로 실행될 수 있으므로, 이것은 개별 도구 호출 개수와는 다른 제한입니다. 제한에 도달하면 이번 요청을 중단하고 안내 메시지를 남깁니다.

## 12. 모델 호출과 도구 오류 처리

도구 함수의 실패는 `try/except`로 잡고, 오류도 해당 도구 호출에 연결된 `ToolMessage`로 돌려줍니다. Gemini 호출 실패는 별도로 처리해 프로그램이 입력 루프를 계속할 수 있게 했습니다.

```python
try:
    tool_result = selected_tool.invoke(tool_call)
except Exception as error:
    tool_result = ToolMessage(
        content=f"도구 실행 중 오류가 발생했습니다: {error}",
        tool_call_id=tool_call["id"],
    )

messages.append(tool_result)
```

모델 호출도 안전 호출 함수로 감쌌습니다.

```python
def invoke_model_safely(model, messages):
    try:
        return model.invoke(messages)
    except Exception as error:
        print(f"[Gemini 호출 오류] {type(error).__name__}: {error}")
        return None
```

이렇게 하면 API 요청 오류가 발생했을 때 오류를 사용자에게 알리고 다음 입력을 받을 수 있습니다. 자동 재시도는 구현하지 않았습니다.

## 13. 최근 대화 턴만 유지

대화가 길어질수록 전체 메시지를 매번 모델에 보내는 비용과 문맥 크기가 커집니다. `HumanMessage`가 시작하는 턴을 기준으로 최근 대화만 남겼습니다.

```python
def keep_recent_turns(messages, max_turns=5):
    human_indices = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, HumanMessage)
    ]

    if len(human_indices) <= max_turns:
        return messages

    return messages[human_indices[-max_turns]:]
```

사용자 메시지 뒤에 연결된 AI 도구 요청, 도구 결과, 최종 답변을 한 턴으로 보고 보존합니다. 목록의 끝에서 메시지 몇 개만 자르는 방식은 도구 요청과 결과를 분리할 수 있어 사용하지 않았습니다. 이 히스토리는 실행 중 메모리일 뿐, 프로그램을 종료하면 사라집니다.

## 14. LangGraph로 에이전트 흐름 구성

직접 작성한 `while response.tool_calls` 반복을 LangGraph의 그래프로 옮겼습니다. LangGraph 그래프는 공유 **상태(State)**, 작업을 수행하는 **노드(Node)**, 다음 노드를 정하는 **엣지(Edge)** 로 구성됩니다. `StateGraph`로 그래프를 만들고 `compile()`한 뒤 `invoke()`로 실행합니다. [공식 Graph API 문서](https://docs.langchain.com/oss/python/langgraph/graph-api)

```bash
uv add langgraph
```

그래프 상태로는 LangGraph가 제공하는 `MessagesState`를 사용합니다. 이 상태에는 메시지 목록이 있으며, 노드가 반환하는 새 메시지가 목록에 누적됩니다.

```python
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition


def call_model(state: MessagesState):
    response = model_with_tools.invoke(state["messages"])
    return {"messages": [response]}
```

`call_model`은 모델 노드입니다. 도구 실행을 포함한 전체 흐름을 그래프로 연결합니다.

```python
builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")

agent = builder.compile()
```

- `START → agent`: 사용자 입력을 받아 모델 노드부터 실행합니다.
- `tools_condition`: 모델 응답에 `tool_calls`가 있으면 `tools` 노드로 보내고, 없으면 실행을 끝냅니다.
- `tools → agent`: 도구 실행 결과를 다시 모델에 전달합니다. 모델이 최종 답변을 만들거나 추가 도구를 요청할 수 있습니다.
- `compile()`: 그래프 구성을 점검하고 실행 가능한 그래프로 만듭니다.
- `agent.invoke(...)`: 그래프 실행을 시작합니다.

```python
result = agent.invoke(
    {"messages": messages},
    config={"recursion_limit": 25},
)
messages = result["messages"]
```

`recursion_limit`은 반복되는 그래프 실행 단계를 제한합니다. 이전의 `MAX_TOOL_ROUNDS`와 비슷한 안전장치지만, 도구 왕복 횟수와 그래프 단계 수는 정확히 같은 개념이 아닙니다. 그래프 구성과 조건 분기 흐름은 [공식 LangGraph Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)를 참고했습니다.

### 직접 작성한 루프와 LangGraph 비교

| 직접 작성한 에이전트 | LangGraph 방식 |
| --- | --- |
| `messages` 리스트 | `MessagesState` |
| `model.invoke(...)` | 모델 노드 `call_model` |
| Python 도구 실행 `for`문 | `ToolNode` |
| `while response.tool_calls` | 조건 엣지 `tools_condition`와 `tools → agent` 연결 |
| 수동 호출 횟수 카운터 | 그래프 `recursion_limit` 설정 |

## 지금까지의 구조 변화

```text
키워드 if문
  → 도구 목록과 키워드 탐색
  → 대화 반복과 JSON 기록
  → Gemini 자연어 응답
  → Gemini의 도구 선택과 실제 함수 실행
  → 도구 결과를 메시지로 연결
  → 실행 중 대화 문맥 유지
  → 도구 이름으로 실행 함수 탐색
  → 응답 콘텐츠에서 텍스트만 출력
  → 다중 도구 호출 반복 및 제한
  → 모델/API 및 도구 오류 처리
  → 최근 대화 턴 유지
  → LangGraph StateGraph로 흐름 표현
```

## 기록해둔 주요 Git 커밋 메시지

- `feat: 규칙 기반 에이전트 대화 루프 추가`
- `refactor: 키워드 기반 도구 선택 구조화`
- `feat: 대화 기록을 JSON 파일로 저장`
- `feat: 대화 기록을 불러와 이어서 저장`
- `refactor: 도구 탐색과 실행 로직 분리`
- `feat: 도구 설명과 도움말 출력 추가`
- `feat: 대화 기록에 타임스탬프 추가`
- `feat: 최근 대화 조회 명령 추가`
- `feat: 확인 절차를 포함한 대화 기록 초기화 추가`
- `feat: LangChain에 Gemini 모델 연결`
- `feat: Gemini 도구 호출로 현재 시간 응답`
- `refactor: 도구 실행 결과를 LangChain 메시지 흐름에 연결`
- `feat: 대화 메시지 히스토리로 문맥 유지`
- `refactor: 도구 호출 이름에 따라 실행 함수 선택`
- `feat: Gemini 응답에서 텍스트만 출력`
- `feat: Gemini 도구 호출 반복 처리 추가`
- `fix: 도구 실행 오류를 처리해 대화 유지`
- `feat: 도구 호출 제한과 최근 대화 히스토리 관리 추가`
- `fix: Gemini 모델 호출 오류 처리 추가`
- `feat: LangGraph로 Gemini 도구 에이전트 구성`
- `feat: SQLite 체크포인터로 대화 상태 저장`

## 15. SQLite 체크포인터로 실행 후에도 대화 이어가기

앞선 LangGraph 실습에서는 `messages` 리스트가 프로그램 실행 중에만 남았습니다. 그래프를 체크포인터와 함께 컴파일하면 LangGraph가 그래프 상태를 `thread_id`별 체크포인트로 저장하고, 다음 실행에서 불러올 수 있습니다. 체크포인트는 대화 스레드의 단기 문맥과 실행 상태를 복원하는 용도입니다. 사용자 선호도처럼 여러 대화 스레드에 걸쳐 공유할 장기 정보는 별도의 Store 개념으로 다룹니다. [공식 Persistence 문서](https://docs.langchain.com/oss/python/langgraph/persistence)

SQLite 체크포인터 패키지를 추가합니다.

```bash
uv add langgraph-checkpoint-sqlite
```

```python
from langgraph.checkpoint.sqlite import SqliteSaver

with SqliteSaver.from_conn_string("agent_memory.sqlite") as checkpointer:
    agent = builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "agent-study-default"}}

    result = agent.invoke(
        {"messages": [HumanMessage(content=user_message)]},
        config=config,
    )
```

- `SqliteSaver`는 그래프 상태를 로컬 SQLite 파일에 저장합니다.
- `thread_id`는 어떤 대화의 상태를 불러오고 저장할지 식별합니다. 같은 ID로 다시 실행하면 해당 대화가 이어집니다. 다른 ID를 사용하면 별도의 대화 스레드가 됩니다.
- 체크포인터를 쓰면 매번 전체 `messages` 목록을 직접 전달하거나 자체 JSON 히스토리를 관리할 필요가 줄어듭니다. 새 사용자 메시지만 입력하고 체크포인터가 이전 상태를 복원합니다.
- SQLite 파일에는 사용자 대화가 들어갈 수 있으므로 `.gitignore`에 `*.sqlite`와 `*.db`를 추가해 로컬 기록이 Git에 올라가지 않도록 합니다.
- 로컬 SQLite는 학습과 개발에 적합합니다. 여러 서버에서 함께 쓰는 운영 환경에는 PostgreSQL 같은 영속 저장소를 고려합니다.

체크포인터 저장은 대화 문맥을 프로그램 재시작 이후까지 이어주는 기능이며, 사용자 프로필 같은 장기 기억 저장소와는 구분됩니다. 체크포인터 개념과 `thread_id`는 [공식 Checkpointers 문서](https://docs.langchain.com/oss/python/langgraph/checkpointers), SQLite saver 사용법은 [공식 LangGraph SQLite 구현 문서](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-sqlite/langgraph/checkpoint/sqlite/__init__.py)에 설명되어 있습니다.

## 16. 여러 대화 스레드 만들기와 전환

하나의 고정 `thread_id`만 사용하면 실행을 다시 시작해도 늘 같은 대화로 돌아갑니다. `thread_id`를 대화마다 다르게 지정하면 체크포인터가 각 대화 상태를 별도로 저장합니다. `/new`, `/threads`, `/use <ID>`, `/thread` 명령으로 대화를 만들고 전환할 수 있습니다.

```python
from uuid import uuid4

active_thread_id = registry["active_thread_id"]

if user_message == "/new":
    active_thread_id = str(uuid4())
    registry["threads"][active_thread_id] = f"대화 {len(registry['threads']) + 1}"
    registry["active_thread_id"] = active_thread_id
    save_registry(registry)

config = {
    "configurable": {"thread_id": active_thread_id},
    "recursion_limit": 25,
}
result = agent.invoke(
    {"messages": [HumanMessage(content=user_message)]},
    config=config,
)
```

- `/new`: UUID를 새 thread ID로 만들어 별도 대화를 시작합니다.
- `/threads`: 로컬 인덱스에 등록된 대화 ID 목록을 보여줍니다.
- `/use <ID>`: 기존 ID를 선택해 해당 대화를 재개합니다.
- `/thread`: 현재 활성 대화 ID를 표시합니다.
- `threads.json`은 대화 목록과 현재 선택을, `agent_memory.sqlite`는 각 대화의 메시지 상태를 저장합니다.

같은 ID로 그래프를 호출해야 같은 상태가 복원됩니다. 체크포인터는 메시지 상태를 저장하고, JSON 인덱스는 앱이 대화 목록과 현재 선택을 기억하게 합니다. 두 파일은 로컬 대화 정보를 담으므로 Git에서 제외합니다.
>>>>>>> 05c308eb88c78b30daffc17c105956f9f51b27cf
