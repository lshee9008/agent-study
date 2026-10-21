from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def main():
    load_dotenv()

    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    model_with_tools = model.bind_tools([get_current_time])

    # 대화가 진행되는 동안 메시지를 계속 보관해 문맥을 유지한다.
    messages = []

    print("Gemini 에이전트 시작! 종료하려면 '종료'를 입력하세요.")

    while True:
        user_message = input("나: ").strip()

        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        messages.append(HumanMessage(content=user_message))
        response = model_with_tools.invoke(messages)

        if response.tool_calls:
            # Gemini의 도구 호출 요청을 대화에 추가한다.
            messages.append(response)

            for tool_call in response.tool_calls:
                print(f"[도구 호출: {tool_call['name']}]")

                if tool_call["name"] == "get_current_time":
                    tool_result = get_current_time.invoke(tool_call)
                    messages.append(tool_result)
                    print(f"[도구 결과: {tool_result.content}]")

            # 도구 결과를 포함한 대화 문맥으로 최종 답변을 받는다.
            final_response = model_with_tools.invoke(messages)
            messages.append(final_response)
            print(f"에이전트: {final_response.content}")
        else:
            messages.append(response)
            print(f"에이전트: {response.content}")


if __name__ == "__main__":
    main()