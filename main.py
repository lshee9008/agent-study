import os
from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import AIMessage, HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition


MAX_HISTORY_TURNS = 5
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


def keep_recent_turns(messages, max_turns: int = MAX_HISTORY_TURNS):
    """최근 사용자 대화와 그에 딸린 메시지를 보존한다."""
    human_indices = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, HumanMessage)
    ]

    if len(human_indices) <= max_turns:
        return messages

    return messages[human_indices[-max_turns]:]


def main():
    load_dotenv()

    if not os.getenv("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY를 찾을 수 없습니다. .env 파일을 확인해 주세요.")
        return

    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")

    tools = [get_current_time, say_hello]
    model_with_tools = model.bind_tools(tools)

    # 노드 1: 현재 대화 상태를 Gemini에 보내 응답을 받는다.
    def call_model(state: MessagesState):
        response = model_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # 그래프를 만들고 모델/도구 노드를 등록한다.
    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))

    # 시작하면 모델부터 실행한다.
    builder.add_edge(START, "agent")

    # 모델이 도구를 요청하면 tools로, 일반 답변이면 그래프 종료로 이동한다.
    builder.add_conditional_edges("agent", tools_condition)

    # 도구 실행 후에는 다시 모델로 돌아가 결과를 해석한다.
    builder.add_edge("tools", "agent")

    agent = builder.compile()

    messages = []

    print("LangGraph Gemini 에이전트 시작! 종료하려면 '종료'를 입력하세요.")

    while True:
        user_message = input("나: ").strip()

        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        messages.append(HumanMessage(content=user_message))

        try:
            result = agent.invoke(
                {"messages": messages},
                config={"recursion_limit": GRAPH_RECURSION_LIMIT},
            )
            messages = result["messages"]
            print(f"에이전트: {get_text(messages[-1].content)}")

        except Exception as error:
            print(f"[에이전트 실행 오류] {type(error).__name__}: {error}")
            messages.append(
                AIMessage(content="요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")
            )

        messages = keep_recent_turns(messages)


if __name__ == "__main__":
    main()