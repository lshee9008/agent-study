from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import AIMessage, HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI


MAX_TOOL_ROUNDS = 5
MAX_HISTORY_TURNS = 5


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
    """완료된 최근 대화 턴만 남긴다."""
    if max_turns < 1:
        raise ValueError("max_turns는 1 이상이어야 합니다.")

    human_indices = [
        index
        for index, message in enumerate(messages)
        if isinstance(message, HumanMessage)
    ]

    if len(human_indices) <= max_turns:
        return messages

    # 최근 max_turns개의 사용자 입력부터 메시지를 보존한다.
    start_index = human_indices[-max_turns]
    return messages[start_index:]


def main():
    load_dotenv()

    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")

    available_tools = [
        get_current_time,
        say_hello,
    ]
    model_with_tools = model.bind_tools(available_tools)

    # 현재 실행 중의 대화 문맥을 저장한다.
    messages = []

    # 모델이 요청한 도구 이름으로 함수를 찾는다.
    tools_by_name = {
        tool.name: tool
        for tool in available_tools
    }

    print("Gemini 에이전트 시작! 종료하려면 '종료'를 입력하세요.")

    while True:
        user_message = input("나: ").strip()

        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        messages.append(HumanMessage(content=user_message))
        response = model_with_tools.invoke(messages)
        tool_rounds = 0

        # 도구 요청이 남아 있고 최대 반복 횟수에 도달하지 않은 동안 실행한다.
        while response.tool_calls and tool_rounds < MAX_TOOL_ROUNDS:
            tool_rounds += 1

            # 모델의 도구 요청 메시지를 대화 기록에 추가한다.
            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                selected_tool = tools_by_name.get(tool_name)

                if selected_tool is None:
                    print(f"등록되지 않은 도구 요청: {tool_name}")
                    tool_result = ToolMessage(
                        content=f"'{tool_name}' 도구는 등록되어 있지 않습니다.",
                        tool_call_id=tool_call["id"],
                    )
                else:
                    print(f"[도구 호출: {tool_name}]")

                    try:
                        tool_result = selected_tool.invoke(tool_call)
                    except Exception as error:
                        print(f"[도구 오류: {tool_name}] {error}")
                        tool_result = ToolMessage(
                            content=f"도구 실행 중 오류가 발생했습니다: {error}",
                            tool_call_id=tool_call["id"],
                        )

                messages.append(tool_result)
                print(f"[도구 결과: {get_text(tool_result.content)}]")

            # 결과를 받은 Gemini가 최종 답변을 만들거나 다음 도구를 요청한다.
            response = model_with_tools.invoke(messages)

        if response.tool_calls:
            # 제한 횟수에 도달하면 미처리 도구 요청을 기록하지 않고 이번 턴을 마친다.
            notice = "도구 호출 최대 횟수에 도달해 이번 요청을 중단했습니다."
            print(f"에이전트: {notice}")
            messages.append(AIMessage(content=notice))
        else:
            messages.append(response)
            print(f"에이전트: {get_text(response.content)}")

        # 대화가 길어지면 완료된 최근 대화만 남긴다.
        messages = keep_recent_turns(messages, max_turns=MAX_HISTORY_TURNS)


if __name__ == "__main__":
    main()