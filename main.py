import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition


DATABASE_FILE = "agent_memory.sqlite"
THREADS_FILE = Path("threads.json")
DEFAULT_THREAD_ID = "agent-study-default"
GRAPH_RECURSION_LIMIT = 25


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


@tool
def say_hello() -> str:
    """사용자가 인사하면 친근하게 인사로 답한다."""
    return "안녕하세요! 어떤 걸 도와드릴까요?"


def get_text(content) -> str:
    """모델 응답에서 텍스트만 꺼낸다."""
    if isinstance(content, str):
        return content

    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def load_registry() -> dict:
    """저장된 대화 목록을 불러온다."""
    default_registry = {
        "active_thread_id": DEFAULT_THREAD_ID,
        "threads": {
            DEFAULT_THREAD_ID: "기본 대화",
        },
    }

    if not THREADS_FILE.exists():
        return default_registry

    try:
        with THREADS_FILE.open("r", encoding="utf-8") as file:
            registry = json.load(file)

        if (
            not isinstance(registry, dict)
            or not isinstance(registry.get("threads"), dict)
            or registry.get("active_thread_id") not in registry["threads"]
        ):
            print("대화 목록 형식이 올바르지 않아 기본 대화로 시작합니다.")
            return default_registry

        return registry

    except (OSError, json.JSONDecodeError):
        print("대화 목록을 읽을 수 없어 기본 대화로 시작합니다.")
        return default_registry


def save_registry(registry: dict) -> None:
    """현재 대화 ID와 대화 목록을 JSON 파일에 저장한다."""
    with THREADS_FILE.open("w", encoding="utf-8") as file:
        json.dump(registry, file, ensure_ascii=False, indent=2)


def build_graph(model, tools, checkpointer):
    """모델 노드와 도구 노드를 연결해 LangGraph를 만든다."""
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState):
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)


def main():
    load_dotenv()

    if not os.getenv("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY를 찾을 수 없습니다. .env 파일을 확인해 주세요.")
        return

    try:
        model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    except Exception as error:
        print(f"[Gemini 초기화 오류] {type(error).__name__}: {error}")
        return

    tools = [get_current_time, say_hello]
    registry = load_registry()

    # SQLite 체크포인터가 대화별 그래프 상태를 저장한다.
    with SqliteSaver.from_conn_string(DATABASE_FILE) as checkpointer:
        agent = build_graph(model, tools, checkpointer)

        print("LangGraph 에이전트 시작!")
        print("명령: /new, /threads, /thread, /use <ID>, 종료")

        while True:
            user_message = input("나: ").strip()

            if user_message.lower() in {"exit", "종료"}:
                print("에이전트: 다음에 또 만나요!")
                break

            if user_message == "/thread":
                active_id = registry["active_thread_id"]
                print(f"현재 대화 ID: {active_id} ({registry['threads'][active_id]})")
                continue

            if user_message == "/threads":
                print("저장된 대화 목록:")
                for thread_id, title in registry["threads"].items():
                    marker = " ← 현재" if thread_id == registry["active_thread_id"] else ""
                    print(f"- {thread_id}: {title}{marker}")
                continue

            if user_message == "/new":
                new_id = str(uuid4())
                title = f"대화 {len(registry['threads']) + 1}"

                registry["threads"][new_id] = title
                registry["active_thread_id"] = new_id
                save_registry(registry)

                print(f"새 대화를 시작합니다: {new_id}")
                continue

            if user_message.startswith("/use "):
                requested_id = user_message.removeprefix("/use ").strip()

                if requested_id not in registry["threads"]:
                    print("목록에 없는 ID예요. /threads로 대화 ID를 확인해 주세요.")
                else:
                    registry["active_thread_id"] = requested_id
                    save_registry(registry)
                    print(f"대화를 전환했습니다: {requested_id}")

                continue

            if user_message.startswith("/"):
                print("명령: /new, /threads, /thread, /use <ID>, 종료")
                continue

            config = {
                "configurable": {
                    "thread_id": registry["active_thread_id"],
                },
                "recursion_limit": GRAPH_RECURSION_LIMIT,
            }

            try:
                result = agent.invoke(
                    {"messages": [HumanMessage(content=user_message)]},
                    config=config,
                )
                final_message = result["messages"][-1]
                print(f"에이전트: {get_text(final_message.content)}")

            except Exception as error:
                print(f"[에이전트 실행 오류] {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()