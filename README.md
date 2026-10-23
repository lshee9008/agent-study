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
uv add langchain langchain-google-genai python-dotenv
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
