import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition


GRAPH_RECURSION_LIMIT = 25
THREAD_ID = "agent-study-default"


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


def build_graph(model, tools):
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

    return builder.compile


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

    # SQLite 파일에 그래프 상태를 저장한다.
    with SqliteSaver.from_conn_string("agent_memory.sqlite") as checkpointer:
        graph_builder_compile = build_graph(model, tools)
        agent = graph_builder_compile(checkpointer=checkpointer)

        # 같은 thread_id를 사용하면 이전 대화 상태를 이어간다.
        config = {
            "configurable": {
                "thread_id": THREAD_ID,
            },
            "recursion_limit": GRAPH_RECURSION_LIMIT,
        }

        print("LangGraph 에이전트 시작! 종료하려면 '종료'를 입력하세요.")

        while True:
            user_message = input("나: ").strip()

            if user_message.lower() in {"exit", "종료"}:
                print("에이전트: 다음에 또 만나요!")
                break

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