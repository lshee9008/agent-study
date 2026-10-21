from datetime import datetime

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

@tool
def get_current_time() -> str:
    """사용자가 현재 날짜가 시간을 물으면 현재 날짜와 시간을 알려준다."""
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

def main():
    load_dotenv()
    
    model = ChatGoogleGenerativeAI(model="gemini-3.7-flash")
    model_with_tools = model.bind_tools([get_current_time])
    
    print("Gemini 에이전트 시작! 종료하려면 '종료'를 입력하세요.")
    
    while True:
        user_message = input("나: ").strip()
        
        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        response = model_with_tools.invoke(user_message)
        
        if response.tool_calls:
            for tool_call in response.tool_calls:
                print(f"[도구 호출: {tool_call['name']}]")
                tool_result = get_current_time.invoke(tool_call)
                print(f"[도구 결과: {tool_result}]")
                
            # 도구 결과를 바탕으로 Gemini가 답변을 작성
            final_response = model.invoke(
                f"사용자 요청: {user_message}\n"
                f"도구 결과: {tool_result}\n"
                "도구 결과를 바탕으로 한국어로 답변해줘."
            )
            print(f"에이전트: {final_response.content}")
        else:
            print(f"에이전트: {response.content}")
            
            
if __name__ == "__main__":
    main()