from datetime import datetime

from dotenv import load_dotenv
from langchain.messages import HumanMessage, ToolMessage
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

@tool
def get_current_time() -> str:
    """사용자가 현재 날짜나 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

@tool
def say_hello() -> str:
    """사용자가 인사하면 친근하게 인사로 답한다."""
    return "안녕하세요! 어떤 걸 도와드릴까요?"

def get_text(content) -> str:
    """모델 응답에서 텍스트만 추출한다."""
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
    available_tools = [get_current_time, say_hello]
    model_with_tools = model.bind_tools(available_tools)
    
    # 대화 중 문맥을 유지할 메시지 목록
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
        
        # 모델이 추가 도구를 요청하는 동안 반복한다.
        while response.tool_calls:
            # 모델의 도구 요청하는 동안 반복한다
            messages.append(response)
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                selected_tool = tools_by_name.get(tool_name)
                
                if selected_tool is None:
                    print(f"등록되지 않은 도구 요청: {tool_name}")
                    
                    # 해당 요청에 오류 결과를 연결해 기록한다.
                    messages.append(
                        ToolMessage(
                            content=f"'{tool_name}' 도구는 등록되어 있지 않습니다.",
                            tool_call_id=tool_call["id"],
                        )
                    )
                    continue

                print(f"[도구 호출: {tool_name}]")
                tool_result = selected_tool.invoke(tool_call)
                messages.append(tool_result)
                print(f"[도구 결과: {get_text(tool_result.content)}]")
                
                
                
            # 도구 결과를 바탕으로 모델이 답하거나 다음 도구를 요청한다.
            response = model_with_tools.invoke(messages)
            
        # 더 이상 도구 요청이 없으면 최종 응답을 저장하고 출력한다
        messages.append(response)
        print(f"에이전트: {get_text(response.content)}")

if __name__ == "__main__":
    main()
                