from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain.messages import HumanMessage, SystemMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime
from langgraph.store.sqlite import SqliteStore


# 로컬 저장 파일
THREADS_FILE = Path("threads.json")
CHECKPOINT_DB = "agent_memory.sqlite"
PROFILE_DB = "agent_profile.sqlite"

# 이 예제는 한 명의 로컬 사용자가 쓴다고 가정합니다.
USER_ID = "local-user"
PROFILE_NAMESPACE = (USER_ID, "profile")


@dataclass
class Context:
    """그래프 실행에 필요한 사용자 정보를 전달합니다."""

    user_id: str


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_text(content) -> str:
    """모델 응답에서 텍스트만 꺼냅니다."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    return str(content)


def load_thread_registry() -> dict:
    """대화 목록과 현재 선택된 대화 ID를 불러옵니다."""
    if THREADS_FILE.exists():
        try:
            with THREADS_FILE.open("r", encoding="utf-8") as file:
                registry = json.load(file)

            if (
                isinstance(registry, dict)
                and isinstance(registry.get("threads"), dict)
                and registry["threads"]
            ):
                active_id = registry.get("active_thread_id")
                if active_id not in registry["threads"]:
                    registry["active_thread_id"] = next(iter(registry["threads"]))
                return registry
        except (json.JSONDecodeError, OSError):
            print("대화 목록 파일을 읽을 수 없어 새 목록을 만들게요.")

    first_thread_id = str(uuid4())
    return {
        "active_thread_id": first_thread_id,
        "threads": {first_thread_id: "대화 1"},
    }


def save_thread_registry(registry: dict) -> None:
    """대화 목록과 현재 선택된 대화 ID를 저장합니다."""
    with THREADS_FILE.open("w", encoding="utf-8") as file:
        json.dump(registry, file, ensure_ascii=False, indent=2)


def build_graph(model, tools):
    """모델 노드와 도구 노드를 연결한 LangGraph를 만듭니다."""
    model_with_tools = model.bind_tools(tools)

    def call_model(state: MessagesState, runtime: Runtime[Context]):
        # 사용자별 Store에서 프로필을 읽습니다.
        namespace = (runtime.context.user_id, "profile")
        profile_item = runtime.store.get(namespace, "basic")

        system_prompt = "너는 한국어로 답하는 친절한 AI 에이전트야."
        if profile_item:
            name = profile_item.value.get("name")
            if name:
                system_prompt += (
                    f" 사용자가 알려준 이름은 {name}이야."
                    " 대화에 자연스럽게 참고하되, 필요할 때만 사용해."
                )

        # 프로필을 시스템 메시지로 추가해 모델이 참고하게 합니다.
        messages = [
            SystemMessage(content=system_prompt),
            *state["messages"],
        ]

        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    builder = StateGraph(MessagesState, context_schema=Context)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder


def print_threads(registry: dict) -> None:
    """등록된 대화 목록을 출력합니다."""
    active_id = registry["active_thread_id"]

    print("대화 목록:")
    for thread_id, title in registry["threads"].items():
        active_mark = " (현재 대화)" if thread_id == active_id else ""
        print(f"- {title}: {thread_id}{active_mark}")


def main():
    load_dotenv()

    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    tools = [get_current_time]
    registry = load_thread_registry()

    print("Gemini LangGraph 에이전트")
    print("종료하려면 '종료'를 입력하세요.")
    print("명령어: /new, /threads, /thread, /use 대화ID")
    print("장기 기억 저장: /remember-name 이름")
    print("프로필 확인: /profile")

    # Store와 체크포인터를 각각 SQLite 파일에 연결합니다.
    with SqliteStore.from_conn_string(PROFILE_DB) as store:
        store.setup()

        with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            builder = build_graph(model, tools)
            agent = builder.compile(
                checkpointer=checkpointer,
                store=store,
            )

            while True:
                try:
                    user_message = input("나: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n에이전트: 다음에 또 만나요!")
                    break

                if not user_message:
                    continue

                if user_message.lower() in {"exit", "종료"}:
                    print("에이전트: 다음에 또 만나요!")
                    break

                # 새 대화를 시작합니다.
                if user_message == "/new":
                    new_thread_id = str(uuid4())
                    title = f"대화 {len(registry['threads']) + 1}"

                    registry["threads"][new_thread_id] = title
                    registry["active_thread_id"] = new_thread_id
                    save_thread_registry(registry)

                    print(f"새 대화를 시작했어요: {new_thread_id}")
                    continue

                # 대화 목록을 출력합니다.
                if user_message == "/threads":
                    print_threads(registry)
                    continue

                # 현재 대화 ID를 출력합니다.
                if user_message == "/thread":
                    print(f"현재 대화 ID: {registry['active_thread_id']}")
                    continue

                # 지정한 ID의 대화를 다시 엽니다.
                if user_message.startswith("/use "):
                    requested_id = user_message.removeprefix("/use ").strip()

                    if requested_id in registry["threads"]:
                        registry["active_thread_id"] = requested_id
                        save_thread_registry(registry)
                        print(f"대화를 전환했어요: {registry['threads'][requested_id]}")
                    else:
                        print("해당 ID의 대화를 찾을 수 없어요. /threads로 확인해 주세요.")
                    continue

                # 사용자 이름을 Store에 명시적으로 저장합니다.
                if user_message.startswith("/remember-name"):
                    name = user_message.removeprefix("/remember-name").strip()

                    if not name:
                        print("사용법: /remember-name 이름")
                        continue

                    store.put(
                        PROFILE_NAMESPACE,
                        "basic",
                        {"name": name},
                    )
                    print(f"에이전트: 이름 '{name}'을 장기 기억에 저장했어요.")
                    continue

                # 저장된 프로필을 확인합니다.
                if user_message == "/profile":
                    profile_item = store.get(PROFILE_NAMESPACE, "basic")

                    if profile_item:
                        print(f"저장된 프로필: {profile_item.value}")
                    else:
                        print("저장된 프로필이 없어요.")
                    continue

                # 현재 thread_id로 체크포인터 대화를 이어갑니다.
                active_thread_id = registry["active_thread_id"]
                config = {
                    "configurable": {"thread_id": active_thread_id},
                    "recursion_limit": 25,
                }

                try:
                    result = agent.invoke(
                        {"messages": [HumanMessage(content=user_message)]},
                        config=config,
                        context=Context(user_id=USER_ID),
                    )

                    answer = get_text(result["messages"][-1].content)
                    print(f"에이전트: {answer}")

                except Exception as error:
                    print(f"에이전트 실행 중 오류가 발생했어요: {error}")


if __name__ == "__main__":
    main()