from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import HumanMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI


@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

def get_text(content) -> str:
    """모델 응답에서 텍스트만 꺼낸다."""
    if isinstance(content, str):
        return content

    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )

def main():
    load_dotenv()

    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    model_with_tools = model.bind_tools([get_current_time])

    # 실행 중 대화 문맥을 유지할 메시지 목록
    messages = []

    # 도구 이름으로 실제 도구를 찾기 위한 딕셔너리
    tools_by_name = {
        get_current_time.name: get_current_time,
    }

    print("Gemini 에이전트 시작! 종료하려면 '종료'를 입력하세요.")

    while True:
        user_message = input("나: ").strip()

        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        messages.append(HumanMessage(content=user_message))
        response = model_with_tools.invoke(messages)

        if response.tool_calls:
            # Gemini의 도구 호출 요청을 대화에 추가
            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                selected_tool = tools_by_name.get(tool_name)

                if selected_tool is None:
                    print(f"등록되지 않은 도구 요청: {tool_name}")
                    continue

                print(f"[도구 호출: {tool_name}]")
                tool_result = selected_tool.invoke(tool_call)
                messages.append(tool_result)
                print(f"[도구 결과: {tool_result.content}]")

            # 도구 결과를 보고 Gemini가 최종 답변을 생성
            final_response = model_with_tools.invoke(messages)
            messages.append(final_response)
            print(f"에이전트: {get_text(final_response.content)}")

        else:
            # 도구 없이 답한 경우에도 응답을 기록해 문맥 유지
            messages.append(response)
            print(f"에이전트: {get_text(response.content)}")


if __name__ == "__main__":
    main()