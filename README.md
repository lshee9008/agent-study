# AI Agent 학습 기록

Python으로 간단한 규칙 기반 에이전트를 만들고, LangChain과 Gemini를 연결하는 과정을 실습합니다.

## 학습 목표

- Python 함수와 반복문으로 에이전트의 기본 흐름 이해하기
- 도구를 등록하고 사용자 요청에 따라 실행하기
- 대화 기록을 JSON 파일에 저장하고 불러오기
- LangChain과 Gemini로 자연어 요청 처리하기
- 이후 LangGraph, OpenClaw, Hermes Agent로 확장하기

## 준비 환경

- Python 3.10 이상
- [uv](https://docs.astral.sh/uv/)
- Gemini API 키
- LangChain, Gemini 연동 패키지

프로젝트는 `uv init --name agent-study`로 초기화했습니다.

```bash
uv add langchain langchain-google-genai python-dotenv
```

## 실습 과정

### 1. Python 프로그램 실행

기본 `main.py`에서 `Hello from agent-study!`를 출력하며 프로젝트 실행을 확인했습니다.

```bash
uv run main.py
```

### 2. 규칙 기반 에이전트

사용자 입력에 `시간`이 포함되면 현재 시간을 반환하고, `안녕`이 포함되면 인사하는 기능을 만들었습니다.

- `get_current_time()`: 현재 시간 반환
- `say_hello()`: 인사 응답
- `run_agent()`: 사용자 입력을 확인하고 적절한 응답 선택

### 3. 도구 목록과 도구 선택

도구 정보를 `TOOLS` 리스트에 모았습니다. 각 도구는 이름, 키워드, 실행 함수를 가집니다.

```python
TOOLS = [
    {
        "name": "time",
        "keywords": ["시간"],
        "function": get_current_time,
    },
    {
        "name": "hello",
        "keywords": ["안녕"],
        "function": say_hello,
    },
]
```

`any(keyword in user_message for keyword in tool["keywords"])`는 도구 키워드 중 하나라도 사용자 입력에 들어 있는지 확인합니다.

도구 탐색과 실행은 `find_tool()`과 `run_agent()`로 분리했습니다.

### 4. 대화 반복과 종료

`while` 반복문으로 여러 입력을 처리하고, `종료` 또는 `exit`를 입력하면 프로그램을 마치게 했습니다.

### 5. 대화 기록과 JSON 저장

사용자 입력과 에이전트 응답을 `conversation_history` 리스트에 추가하고, `conversation.json` 파일로 저장했습니다.

JSON 파일을 다시 불러와 기존 기록 뒤에 새 대화를 이어 저장하도록 확장했습니다. 각 대화에 타임스탬프도 추가했습니다.

### 6. 추가 명령

- `/history`: 최근 대화 확인
- `/clear`: 확인 절차를 거쳐 대화 기록 초기화
- `도움말`: 사용 가능한 도구 목록 확인

잘못된 JSON 파일이나 도구 실행 오류에 대응하는 예외 처리도 실습했습니다.

### 7. Gemini와 LangChain 연결

`.env` 파일에서 API 키를 읽도록 구성했습니다.

```env
GOOGLE_API_KEY=여기에_Gemini_API_키
```

`.gitignore`에는 비밀 키와 Python 환경 파일을 추가했습니다.

```gitignore
.env
.env.*
.venv/
__pycache__/
*.py[cod]
.DS_Store
```

LangChain의 `ChatGoogleGenerativeAI`로 Gemini에 질문을 보내고 응답을 출력하는 코드를 작성했습니다.

### 8. LangChain 도구 호출

`@tool`로 Python 함수를 LangChain 도구로 등록하고, `bind_tools()`를 통해 Gemini에 도구 정보를 전달하는 방식을 학습 중입니다.

```python
@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
```

## 중요한 개념

- **도구(tool)**: 에이전트가 호출할 수 있도록 등록한 함수
- **도구 설명(description)**: 도구의 기능을 모델에 알려주는 설명
- **도구 호출(tool calling)**: 모델이 요청에 맞는 도구와 입력값을 선택하는 과정
- **대화 기록(history)**: 사용자 입력과 에이전트 응답을 저장한 데이터
- **환경 변수**: API 키와 같은 설정값을 코드와 분리해 관리하는 방법

## 다음 학습 계획

1. Gemini의 도구 호출 결과를 실제 도구 실행과 연결하기
2. 기존 JSON 대화 기록 기능을 Gemini 에이전트에 결합하기
3. LangGraph로 상태, 분기, 도구 실행 흐름 구성하기
4. OpenClaw와 Hermes Agent의 구조와 실행 방법 비교하기
5. 작은 개인용 AI 에이전트 프로젝트 완성하기

## 보안 주의

- API 키를 코드, README, Git 커밋, 채팅에 올리지 않습니다.
- `.env` 파일은 `.gitignore`에 포함합니다.
- API 키가 실수로 공개됐다면 해당 키를 폐기하고 새 키를 발급합니다.
