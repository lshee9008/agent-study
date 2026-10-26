from datetime import datetime
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain.tools import tool
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, MessagesState, START, StateGraph
from langgraph.store.sqlite import SqliteStore
from langgraph.types import Command, interrupt


# 대화 목록과 데이터베이스 파일 경로입니다.
THREADS_FILE = Path("threads.json")
CHECKPOINT_DB = "agent_memory.sqlite"
PROFILE_DB = "agent_profile.sqlite"

# 이 학습용 예제는 로컬 사용자 한 명을 가정합니다.
USER_ID = "local-user"

# LangGraph Store에서 사용자 데이터를 분류할 namespace입니다.
PROFILE_NAMESPACE = (USER_ID, "profile")
MEMORIES_NAMESPACE = (USER_ID, "memories")
SETTINGS_NAMESPACE = (USER_ID, "settings")

# 기존 기억을 임베딩 인덱스에 등록했는지 확인하는 key입니다.
INDEX_MARKER_KEY = "gemini-embedding-001-indexed"


class RouteDecision(BaseModel):
    """Router가 반환해야 하는 분류 결과의 형식입니다."""

    category: Literal["time", "memory", "save_memory", "chat"] = Field(
        description=(
            "time은 현재 날짜나 시간 질문, "
            "memory는 프로필이나 저장한 기억 검색, "
            "save_memory는 새로운 기억 저장 요청, "
            "chat은 그 외 일반 대화"
        )
    )
    query: str = Field(
        description="전문가나 다음 노드가 처리할 핵심 요청"
    )


class AgentState(MessagesState, total=False):
    """대화 메시지와 Router의 분류 결과를 보관하는 그래프 상태입니다."""

    route: Literal["time", "memory", "save_memory", "chat"]
    route_query: str


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""

    # 현재 시스템의 로컬 시간대를 적용해 문자열로 반환합니다.
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_text(content) -> str:
    """LangChain 메시지 content에서 텍스트만 추출합니다."""

    # content가 문자열이면 그대로 사용합니다.
    if isinstance(content, str):
        return content

    # content가 여러 블록이면 text 유형 블록만 이어 붙입니다.
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )

    # 예상하지 못한 형식은 문자열로 바꿉니다.
    return str(content)


def load_thread_registry() -> dict:
    """대화 목록을 JSON 파일에서 불러옵니다."""

    if THREADS_FILE.exists():
        try:
            with THREADS_FILE.open("r", encoding="utf-8") as file:
                registry = json.load(file)

            # 필요한 데이터 구조가 있는지 확인합니다.
            if (
                isinstance(registry, dict)
                and isinstance(registry.get("threads"), dict)
                and registry["threads"]
            ):
                active_id = registry.get("active_thread_id")

                # 활성 대화 ID가 목록에 없으면 첫 대화를 선택합니다.
                if active_id not in registry["threads"]:
                    registry["active_thread_id"] = next(
                        iter(registry["threads"])
                    )

                return registry

        except (json.JSONDecodeError, OSError):
            print("대화 목록 파일을 읽을 수 없어 새 목록을 만들게요.")

    # 대화 목록이 없으면 첫 대화를 만듭니다.
    first_thread_id = str(uuid4())
    return {
        "active_thread_id": first_thread_id,
        "threads": {first_thread_id: "대화 1"},
    }


def save_thread_registry(registry: dict) -> None:
    """대화 목록을 JSON 파일에 저장합니다."""

    with THREADS_FILE.open("w", encoding="utf-8") as file:
        json.dump(registry, file, ensure_ascii=False, indent=2)


def print_threads(registry: dict) -> None:
    """대화 이름과 ID를 화면에 출력합니다."""

    active_id = registry["active_thread_id"]
    print("대화 목록:")

    for thread_id, title in registry["threads"].items():
        active_mark = " (현재 대화)" if thread_id == active_id else ""
        print(f"- {title}: {thread_id}{active_mark}")


def reindex_existing_memories(store) -> None:
    """기존 기억을 최초 한 번 임베딩 검색 인덱스에 등록합니다."""

    marker = store.get(SETTINGS_NAMESPACE, INDEX_MARKER_KEY)

    # 이미 인덱싱을 마쳤으면 반복하지 않습니다.
    if marker:
        return

    old_memories = store.search(MEMORIES_NAMESPACE, limit=1000)

    # 기존 각 기억의 text 필드를 검색 인덱스에 포함합니다.
    for item in old_memories:
        if item.value.get("text"):
            store.put(
                MEMORIES_NAMESPACE,
                item.key,
                item.value,
                index=["text"],
            )

    # 완료 표시를 저장해 다음 실행에서 다시 처리하지 않게 합니다.
    store.put(
        SETTINGS_NAMESPACE,
        INDEX_MARKER_KEY,
        {"done": True},
        index=False,
    )


def make_memory_search_tool(store):
    """기억 전문가가 사용할 Store 검색 도구를 만듭니다."""

    @tool
    def search_saved_memories(query: str) -> str:
        """사용자 프로필과 장기 기억에서 질문과 관련된 내용을 검색한다."""

        results = []

        # 이름 프로필이 저장되어 있으면 검색 결과에 함께 포함합니다.
        profile = store.get(PROFILE_NAMESPACE, "basic")
        if profile:
            name = profile.value.get("name")
            if name:
                results.append(f"사용자 이름: {name}")

        # 검색어와 의미가 가까운 기억을 최대 3개 찾습니다.
        memories = store.search(
            MEMORIES_NAMESPACE,
            query=query,
            limit=3,
        )

        for item in memories:
            text = item.value.get("text")
            if text:
                results.append(text)

        if not results:
            return "관련된 프로필이나 장기 기억을 찾지 못했습니다."

        # 도구 결과를 전문 에이전트가 읽을 문자열로 변환합니다.
        return "\n".join(f"- {item}" for item in results)

    return search_saved_memories


def make_router(model):
    """사용자 요청을 네 가지 처리 경로 중 하나로 분류하는 Router를 만듭니다."""

    return create_agent(
        model=model,
        tools=[],
        response_format=RouteDecision,
        system_prompt=(
            "사용자 요청의 의도를 분류해. "
            "현재 날짜나 시간이 궁금하면 time을 선택해. "
            "저장된 사용자 정보나 기억을 찾으면 memory를 선택해. "
            "새로운 정보를 기억해 달라는 요청이면 save_memory를 선택해. "
            "그 외에는 chat을 선택해. "
            "최근 대화의 대명사나 생략된 표현도 참고해서 query를 완성해."
        ),
    )


def make_specialist_agents(model, store):
    """시간 전문가와 기억 전문가 에이전트를 만듭니다."""

    # 시간 전문가에게는 현재 시간 도구만 제공합니다.
    time_expert = create_agent(
        model=model,
        tools=[get_current_time],
        system_prompt=(
            "너는 현재 날짜와 시간을 확인하는 전문가야. "
            "시간 질문에는 get_current_time 도구를 사용해. "
            "도구 결과를 바탕으로 짧게 답해."
        ),
    )

    # 기억 전문가에게는 Store 검색 도구만 제공합니다.
    memory_search_tool = make_memory_search_tool(store)

    memory_expert = create_agent(
        model=model,
        tools=[memory_search_tool],
        system_prompt=(
            "너는 사용자의 프로필과 장기 기억을 검색하는 전문가야. "
            "질문과 관련된 기억을 검색해. "
            "검색 결과에 없는 정보는 지어내지 말고, "
            "찾지 못했으면 찾지 못했다고 말해."
        ),
    )

    return time_expert, memory_expert


def build_graph(model, store, checkpointer):
    """Router, 전문가 에이전트, 승인 노드를 하나의 그래프로 연결합니다."""

    # Router는 분류 결과를 구조화된 Pydantic 객체로 반환합니다.
    router = make_router(model)

    # 각 전문 에이전트는 자기 역할에 맞는 도구만 가집니다.
    time_expert, memory_expert = make_specialist_agents(model, store)

    def classify_request(state: AgentState):
        """최근 대화 내용을 보고 요청 종류와 처리 문장을 분류합니다."""

        # 최근 대화 몇 개를 Router에 전달해 생략 표현을 해석하도록 합니다.
        recent_messages = state["messages"][-8:]

        route_result = router.invoke(
            {"messages": recent_messages}
        )

        decision = route_result["structured_response"]

        # 구조화된 분류 결과를 그래프 상태에 기록합니다.
        return {
            "route": decision.category,
            "route_query": decision.query,
        }

    def run_time_expert(state: AgentState):
        """시간 전문가를 실행하고 결과를 부모 그래프 메시지에 추가합니다."""

        result = time_expert.invoke(
            {
                "messages": [
                    HumanMessage(content=state["route_query"])
                ]
            }
        )

        answer = get_text(result["messages"][-1].content)

        # 전문가의 최종 답변을 메인 대화 상태에 기록합니다.
        return {"messages": [AIMessage(content=answer)]}

    def run_memory_expert(state: AgentState):
        """기억 전문가를 실행하고 결과를 메인 대화에 추가합니다."""

        result = memory_expert.invoke(
            {
                "messages": [
                    HumanMessage(content=state["route_query"])
                ]
            }
        )

        answer = get_text(result["messages"][-1].content)

        return {"messages": [AIMessage(content=answer)]}

    def save_memory_with_approval(state: AgentState):
        """기억 저장 전에 멈춰서 사용자 승인을 받습니다."""

        requested_text = state["route_query"].strip()

        # 사용자가 저장하려는 내용을 확인할 수 있도록 그래프를 중지합니다.
        decision = interrupt(
            {
                "action": "save_memory",
                "text": requested_text,
                "message": "이 내용을 장기 기억에 저장할까요?",
            }
        )

        if decision.get("action") != "approve":
            answer = "알겠습니다. 이 내용은 장기 기억에 저장하지 않았습니다."
            return {"messages": [AIMessage(content=answer)]}

        # 승인하면서 내용을 수정했다면 수정된 값을 사용합니다.
        approved_text = decision.get("text", requested_text).strip()

        if not approved_text:
            answer = "저장할 내용이 비어 있어 저장하지 않았습니다."
            return {"messages": [AIMessage(content=answer)]}

        memory_id = str(uuid4())

        # 승인된 내용만 Store에 기록하고 임베딩 검색 대상으로 지정합니다.
        store.put(
            MEMORIES_NAMESPACE,
            memory_id,
            {"text": approved_text},
            index=["text"],
        )

        answer = f"기억을 저장했어요. 기억 ID: {memory_id}"
        return {"messages": [AIMessage(content=answer)]}

    def answer_general_chat(state: AgentState):
        """일반 대화 경로에서 Gemini가 답변을 만듭니다."""

        response = model.invoke(
            [
                SystemMessage(
                    content="너는 한국어로 답하는 친절한 AI 에이전트야."
                ),
                *state["messages"],
            ]
        )

        return {"messages": [response]}

    # 각 분류 결과를 어느 그래프 노드로 보낼지 정합니다.
    route_map = {
        "time": "time_expert",
        "memory": "memory_expert",
        "save_memory": "save_memory",
        "chat": "chat",
    }

    builder = StateGraph(AgentState)

    # 그래프의 각 작업을 노드로 등록합니다.
    builder.add_node("classify", classify_request)
    builder.add_node("time_expert", run_time_expert)
    builder.add_node("memory_expert", run_memory_expert)
    builder.add_node("save_memory", save_memory_with_approval)
    builder.add_node("chat", answer_general_chat)

    # 새 입력은 먼저 Router로 보냅니다.
    builder.add_edge(START, "classify")

    # Router 결과를 보고 Python 코드가 분기 경로를 선택합니다.
    builder.add_conditional_edges(
        "classify",
        lambda state: state["route"],
        route_map,
    )

    # 각 작업이 끝나면 그래프를 종료합니다.
    builder.add_edge("time_expert", END)
    builder.add_edge("memory_expert", END)
    builder.add_edge("save_memory", END)
    builder.add_edge("chat", END)

    # 체크포인터를 연결해 thread별 대화 상태를 저장합니다.
    return builder.compile(checkpointer=checkpointer)


def main():
    """모델과 저장소를 준비하고 대화형 에이전트를 실행합니다."""

    load_dotenv()

    # Gemini 대화 모델과 임베딩 모델을 준비합니다.
    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001",
    )

    # 저장된 대화 목록을 불러옵니다.
    registry = load_thread_registry()

    print("Gemini 구조화 라우터 에이전트")
    print("종료하려면 '종료'를 입력하세요.")
    print("대화: /new, /threads, /thread, /use 대화ID")
    print("프로필: /remember-name 이름, /profile")
    print("기억: /remember-fact 내용, /memories, /search-fact 검색어")
    print("기억 수정/삭제: /update-fact 기억ID 새내용, /forget 기억ID")

    # 장기 기억과 사용자 프로필 Store를 엽니다.
    with SqliteStore.from_conn_string(
        PROFILE_DB,
        index={
            "embed": embeddings,
            "dims": 3072,
            "fields": ["text"],
        },
    ) as store:
        store.setup()
        reindex_existing_memories(store)

        # 대화 체크포인터를 엽니다.
        with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            graph = build_graph(
                model=model,
                store=store,
                checkpointer=checkpointer,
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

                # 새 대화를 만들어 현재 thread로 선택합니다.
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

                # 기존 대화로 전환합니다.
                if user_message.startswith("/use "):
                    requested_id = user_message.removeprefix("/use ").strip()

                    if requested_id in registry["threads"]:
                        registry["active_thread_id"] = requested_id
                        save_thread_registry(registry)
                        print(
                            "대화를 전환했어요: "
                            f"{registry['threads'][requested_id]}"
                        )
                    else:
                        print("대화 ID를 찾을 수 없어요. /threads로 확인해 주세요.")
                    continue

                # 사용자 이름을 프로필 Store에 저장합니다.
                if user_message.startswith("/remember-name"):
                    name = user_message.removeprefix("/remember-name").strip()

                    if not name:
                        print("사용법: /remember-name 이름")
                        continue

                    store.put(
                        PROFILE_NAMESPACE,
                        "basic",
                        {"name": name},
                        index=False,
                    )
                    print(f"이름 '{name}'을 저장했어요.")
                    continue

                # 프로필 이름을 확인합니다.
                if user_message == "/profile":
                    profile = store.get(PROFILE_NAMESPACE, "basic")

                    if profile:
                        print(f"저장된 프로필: {profile.value}")
                    else:
                        print("저장된 프로필이 없어요.")
                    continue

                # 기억을 직접 추가합니다.
                if user_message.startswith("/remember-fact "):
                    text = user_message.removeprefix("/remember-fact ").strip()

                    if not text:
                        print("사용법: /remember-fact 기억할 내용")
                        continue

                    memory_id = str(uuid4())
                    store.put(
                        MEMORIES_NAMESPACE,
                        memory_id,
                        {"text": text},
                        index=["text"],
                    )
                    print(f"기억을 저장했어요. ID: {memory_id}")
                    continue

                # 저장된 기억 전체를 조회합니다.
                if user_message == "/memories":
                    items = store.search(MEMORIES_NAMESPACE, limit=50)

                    if not items:
                        print("저장된 기억이 없어요.")
                    else:
                        for item in items:
                            print(
                                f"- ID: {item.key} | "
                                f"내용: {item.value.get('text', '')}"
                            )
                    continue

                # 기억 검색 명령을 직접 처리합니다.
                if user_message == "/search-fact" or user_message.startswith(
                    "/search-fact "
                ):
                    query = user_message.removeprefix("/search-fact").strip()

                    if not query:
                        print("사용법: /search-fact 검색할 내용")
                        continue

                    matches = store.search(
                        MEMORIES_NAMESPACE,
                        query=query,
                        limit=5,
                    )

                    if not matches:
                        print("관련 기억을 찾지 못했어요.")
                    else:
                        for item in matches:
                            print(
                                f"- ID: {item.key} | "
                                f"내용: {item.value.get('text', '')}"
                            )
                    continue

                # 지정한 기억의 내용을 수정합니다.
                if user_message.startswith("/update-fact "):
                    parts = user_message.split(maxsplit=2)

                    if len(parts) < 3:
                        print("사용법: /update-fact 기억ID 새 내용")
                        continue

                    _, memory_id, new_text = parts
                    existing = store.get(MEMORIES_NAMESPACE, memory_id)

                    if existing is None:
                        print("기억 ID를 찾을 수 없어요. /memories로 확인해 주세요.")
                    else:
                        store.put(
                            MEMORIES_NAMESPACE,
                            memory_id,
                            {"text": new_text},
                            index=["text"],
                        )
                        print("기억을 수정했어요.")
                    continue

                # 지정한 기억을 삭제합니다.
                if user_message.startswith("/forget "):
                    memory_id = user_message.removeprefix("/forget ").strip()

                    if not memory_id:
                        print("사용법: /forget 기억ID")
                        continue

                    existing = store.get(MEMORIES_NAMESPACE, memory_id)

                    if existing is None:
                        print("기억 ID를 찾을 수 없어요. /memories로 확인해 주세요.")
                    else:
                        store.delete(MEMORIES_NAMESPACE, memory_id)
                        print("기억을 삭제했어요.")
                    continue

                # 현재 대화 ID가 체크포인터의 thread_id가 됩니다.
                active_thread_id = registry["active_thread_id"]
                config = {
                    "configurable": {"thread_id": active_thread_id},
                    "recursion_limit": 25,
                }

                try:
                    # 일반 사용자 입력을 그래프에 전달합니다.
                    result = graph.invoke(
                        {"messages": [HumanMessage(content=user_message)]},
                        config=config,
                    )

                    # 기억 저장 노드가 승인을 기다리면 사용자에게 확인합니다.
                    while result.get("__interrupt__"):
                        pending = result["__interrupt__"][0].value

                        print("\n[장기 기억 저장 승인 요청]")
                        print(f"저장할 내용: {pending['text']}")
                        choice = input("저장할까요? (y/n): ").strip().lower()

                        if choice in {"y", "yes", "예"}:
                            edited_text = input(
                                "내용을 수정하려면 입력하세요 "
                                "(그대로 저장하려면 Enter): "
                            ).strip()

                            resume_value = {
                                "action": "approve",
                                "text": edited_text or pending["text"],
                            }
                        else:
                            resume_value = {"action": "reject"}

                        # 같은 thread의 중단된 그래프를 재개합니다.
                        result = graph.invoke(
                            Command(resume=resume_value),
                            config=config,
                        )

                    # 그래프의 마지막 메시지를 사용자에게 출력합니다.
                    answer = get_text(result["messages"][-1].content)
                    print(f"에이전트: {answer}")

                except Exception as error:
                    print(f"에이전트 실행 중 오류가 발생했어요: {error}")


if __name__ == "__main__":
    main()