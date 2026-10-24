import os
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

    # 최근 max_turns개의 사용자 입력부터 이후 메시지를 보존한다.
    start_index = human_indices[-max_turns]
    return messages[start_index:]


def invoke_model_safely(model, messages):
    """Gemini 호출 오류를 출력하고, 실패하면 None을 반환한다."""
    try:
        return model.invoke(messages)
    except Exception as error:
        print(f"[Gemini 호출 오류] {type(error).__name__}: {error}")
        return None


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
        response = invoke_model_safely(model_with_tools, messages)

        if response is None:
            failure_response = AIMessage(
                content="Gemini 호출에 실패했습니다. 잠시 후 다시 시도해 주세요."
            )
            messages.append(failure_response)
            print(f"에이전트: {failure_response.content}")
            messages = keep_recent_turns(messages)
            continue

        tool_rounds = 0

        # 모델이 도구를 더 요청하는 동안 반복한다.
        while response.tool_calls and tool_rounds < MAX_TOOL_ROUNDS:
            tool_rounds += 1

            # 모델의 도구 호출 요청을 대화 기록에 추가한다.
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
                        print(f"[도구 오류: {tool_name}] {type(error).__name__}: {error}")
                        tool_result = ToolMessage(
                            content=f"도구 실행 중 오류가 발생했습니다: {error}",
                            tool_call_id=tool_call["id"],
                        )

                messages.append(tool_result)
                print(f"[도구 결과: {get_text(tool_result.content)}]")

            # 도구 결과를 보고 Gemini가 최종 답변 또는 다음 도구 요청을 만든다.
            next_response = invoke_model_safely(model_with_tools, messages)

            if next_response is None:
                response = AIMessage(
                    content="Gemini 호출에 실패해 이번 요청을 중단했습니다."
                )
                break

            response = next_response

        if response.tool_calls:
            # 최대 도구 호출 라운드에 도달한 경우
            notice = "도구 호출 최대 횟수에 도달해 이번 요청을 중단했습니다."
            response = AIMessage(content=notice)

        messages.append(response)
        print(f"에이전트: {get_text(response.content)}")

        # 완료된 최근 대화만 다음 요청의 문맥으로 보존한다.
        messages = keep_recent_turns(messages)


if __name__ == "__main__":
    main()