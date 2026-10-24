from datetime import datetime
import json
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings,
)
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.sqlite import SqliteStore
from langgraph.types import Command, interrupt


# 대화 목록과 저장소 파일 경로
THREADS_FILE = Path("threads.json")
CHECKPOINT_DB = "agent_memory.sqlite"
PROFILE_DB = "agent_profile.sqlite"

# 로컬 사용자 한 명을 가정합니다.
USER_ID = "local-user"

# Store에서 사용할 사용자별 데이터 공간
PROFILE_NAMESPACE = (USER_ID, "profile")
MEMORIES_NAMESPACE = (USER_ID, "memories")
SETTINGS_NAMESPACE = (USER_ID, "settings")
INDEX_MARKER_KEY = "gemini-embedding-001-indexed"


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def make_save_memory_tool(store):
    """승인을 받은 뒤 장기 기억을 저장하는 도구를 만듭니다."""

    @tool
    def save_memory(text: str) -> str:
        """사용자가 기억해 달라고 한 정보를 승인받은 뒤 장기 기억에 저장한다."""

        # 저장 전에 그래프를 멈추고 사용자에게 승인 정보를 전달합니다.
        decision = interrupt(
            {
                "action": "save_memory",
                "text": text,
                "message": "이 내용을 장기 기억에 저장할까요?",
            }
        )

        # 승인하지 않았다면 Store를 수정하지 않습니다.
        if decision.get("action") != "approve":
            return "사용자가 기억 저장을 취소했습니다."

        # 사용자가 수정해서 승인한 내용이 있으면 수정본을 사용합니다.
        approved_text = decision.get("text", text).strip()

        if not approved_text:
            return "저장할 내용이 비어 있어 저장하지 않았습니다."

        # 각 기억을 구분할 ID를 만들고 Store에 저장합니다.
        memory_id = str(uuid4())
        store.put(
            MEMORIES_NAMESPACE,
            memory_id,
            {"text": approved_text},
            index=["text"],
        )

        return f"기억을 저장했습니다. 기억 ID: {memory_id}"

    return save_memory


def make_memory_search_tool(store):
    """사용자 프로필과 장기 기억을 검색하는 도구를 만듭니다."""

    @tool
    def search_saved_memories(query: str) -> str:
        """사용자의 프로필과 장기 기억에서 질문과 관련된 정보를 찾는다."""

        results = []

        # 이름 프로필이 있으면 검색 결과에 포함합니다.
        profile = store.get(PROFILE_NAMESPACE, "basic")
        if profile:
            name = profile.value.get("name")
            if name:
                results.append(f"사용자 이름: {name}")

        # 입력한 문장과 의미가 가까운 기억을 검색합니다.
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

        # 검색 결과만 전문 에이전트에게 반환합니다.
        return "\n".join(f"- {item}" for item in results)

    return search_saved_memories


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
                    registry["active_thread_id"] = next(
                        iter(registry["threads"])
                    )

                return registry

        except (json.JSONDecodeError, OSError):
            print("대화 목록 파일을 읽을 수 없어 새 목록을 만들게요.")

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
    """대화 목록과 현재 선택된 대화를 출력합니다."""

    active_id = registry["active_thread_id"]
    print("대화 목록:")

    for thread_id, title in registry["threads"].items():
        active_mark = " (현재 대화)" if thread_id == active_id else ""
        print(f"- {title}: {thread_id}{active_mark}")


def reindex_existing_memories(store) -> None:
    """기존 기억을 최초 한 번 임베딩 검색 인덱스에 등록합니다."""

    marker = store.get(SETTINGS_NAMESPACE, INDEX_MARKER_KEY)

    # 이미 인덱싱한 경우 다시 처리하지 않습니다.
    if marker:
        return

    old_memories = store.search(MEMORIES_NAMESPACE, limit=1000)

    for item in old_memories:
        if item.value.get("text"):
            store.put(
                MEMORIES_NAMESPACE,
                item.key,
                item.value,
                index=["text"],
            )

    # 완료 여부를 기록해 다음 실행 때 반복하지 않게 합니다.
    store.put(
        SETTINGS_NAMESPACE,
        INDEX_MARKER_KEY,
        {"done": True},
        index=False,
    )


def build_supervisor(model, store, save_memory_tool, checkpointer):
    """시간·기억 전문 에이전트를 만들고 Supervisor에 연결합니다."""

    # 기억 전문가가 사용할 검색 도구를 만듭니다.
    memory_search_tool = make_memory_search_tool(store)

    # 시간 전문가: 현재 시간 도구만 사용합니다.
    time_expert = create_agent(
        model=model,
        tools=[get_current_time],
        system_prompt=(
            "너는 현재 날짜와 시간을 확인하는 전문가야. "
            "시간 질문에는 get_current_time 도구를 사용해. "
            "도구 결과를 바탕으로 짧게 답해."
        ),
    )

    # 기억 전문가: 사용자 기억 검색 도구만 사용합니다.
    memory_expert = create_agent(
        model=model,
        tools=[memory_search_tool],
        system_prompt=(
            "너는 사용자의 장기 기억을 검색하는 전문가야. "
            "질문과 관련된 기억을 검색하고, 검색 결과에 없는 내용은 "
            "지어내지 마. 검색 결과를 간결하게 보고해."
        ),
    )

    # Supervisor가 시간 전문가를 도구처럼 부를 수 있게 감쌉니다.
    @tool
    def ask_time_expert(question: str) -> str:
        """현재 날짜나 시간에 관한 질문을 시간 전문가에게 맡긴다."""

        result = time_expert.invoke(
            {"messages": [HumanMessage(content=question)]}
        )

        return get_text(result["messages"][-1].content)

    # Supervisor가 기억 전문가를 도구처럼 부를 수 있게 감쌉니다.
    @tool
    def ask_memory_expert(question: str) -> str:
        """사용자 프로필이나 장기 기억에 관한 질문을 기억 전문가에게 맡긴다."""

        result = memory_expert.invoke(
            {"messages": [HumanMessage(content=question)]}
        )

        return get_text(result["messages"][-1].content)

    # Supervisor는 요청을 직접 처리하거나 적절한 전문가에게 위임합니다.
    supervisor = create_agent(
        model=model,
        tools=[
            ask_time_expert,
            ask_memory_expert,
            save_memory_tool,
        ],
        system_prompt=(
            "너는 한국어로 답하는 친절한 Supervisor야. "
            "현재 날짜나 시간 질문은 ask_time_expert에 맡겨. "
            "사용자의 이름이나 장기 기억에 관한 질문은 "
            "ask_memory_expert에 맡겨. "
            "사용자가 명시적으로 기억해 달라고 요청하면 save_memory를 사용해. "
            "간단한 인사나 일반 질문은 직접 답해. "
            "전문가가 돌려준 결과를 바탕으로 사용자에게 최종 답변을 해."
        ),
        checkpointer=checkpointer,
    )

    return supervisor


def main():
    """모델과 저장소를 준비하고 대화형 에이전트를 실행합니다."""

    load_dotenv()

    # Gemini 대화 모델과 임베딩 모델을 준비합니다.
    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    embeddings = GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001",
    )

    # 대화 이름과 현재 대화 ID를 불러옵니다.
    registry = load_thread_registry()

    print("Gemini 멀티 에이전트 시작")
    print("종료하려면 '종료'를 입력하세요.")
    print("대화: /new, /threads, /thread, /use 대화ID")
    print("프로필: /remember-name 이름, /profile")
    print("기억: /remember-fact 내용, /memories, /search-fact 검색어")
    print("기억 수정/삭제: /update-fact 기억ID 새내용, /forget 기억ID")
    print("일반 대화에서 기억 저장을 요청하면 승인을 받습니다.")

    # 장기 기억 Store를 엽니다.
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

        # 승인 절차가 포함된 기억 저장 도구를 만듭니다.
        save_memory_tool = make_save_memory_tool(store)

        # 대화 상태를 저장하는 체크포인터를 엽니다.
        with SqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
            # Supervisor와 전문 에이전트를 만듭니다.
            supervisor = build_supervisor(
                model=model,
                store=store,
                save_memory_tool=save_memory_tool,
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

                # 새 대화를 만들고 활성 대화로 지정합니다.
                if user_message == "/new":
                    new_thread_id = str(uuid4())
                    title = f"대화 {len(registry['threads']) + 1}"

                    registry["threads"][new_thread_id] = title
                    registry["active_thread_id"] = new_thread_id
                    save_thread_registry(registry)

                    print(f"새 대화를 시작했어요: {new_thread_id}")
                    continue

                # 등록된 대화를 모두 보여줍니다.
                if user_message == "/threads":
                    print_threads(registry)
                    continue

                # 현재 선택된 대화 ID를 보여줍니다.
                if user_message == "/thread":
                    print(f"현재 대화 ID: {registry['active_thread_id']}")
                    continue

                # 지정한 ID의 대화로 전환합니다.
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

                # 기억 검색 명령은 모델에 보내지 않고 Python에서 처리합니다.
                if user_message.startswith("/search-fact"):
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

                # 사용자 이름을 프로필에 저장합니다.
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
                    print(f"이름 '{name}'을 장기 기억에 저장했어요.")
                    continue

                # 저장된 프로필을 확인합니다.
                if user_message == "/profile":
                    profile = store.get(PROFILE_NAMESPACE, "basic")

                    if profile:
                        print(f"저장된 프로필: {profile.value}")
                    else:
                        print("저장된 프로필이 없어요.")
                    continue

                # 기억을 직접 추가합니다. 이 명령은 명시적 요청이므로 바로 저장합니다.
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

                # 저장된 기억 전체를 확인합니다.
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

                # 기억 내용을 수정합니다.
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

                # 현재 대화의 체크포인터 ID를 지정합니다.
                active_thread_id = registry["active_thread_id"]
                config = {
                    "configurable": {"thread_id": active_thread_id},
                    "recursion_limit": 25,
                }

                try:
                    # 명령이 아닌 사용자 입력은 Supervisor에게 보냅니다.
                    result = supervisor.invoke(
                        {"messages": [HumanMessage(content=user_message)]},
                        config=config,
                    )

                    # 기억 저장 도구가 승인을 요청하면 입력을 받아 그래프를 재개합니다.
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

                        result = supervisor.invoke(
                            Command(resume=resume_value),
                            config=config,
                        )

                    # 그래프 결과에서 텍스트 답변을 꺼냅니다.
                    answer = get_text(result["messages"][-1].content)
                    print(f"에이전트: {answer}")

                except Exception as error:
                    print(f"에이전트 실행 중 오류가 발생했어요: {error}")


if __name__ == "__main__":
    main()