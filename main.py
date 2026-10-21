import json
from datetime import datetime

def get_current_time() -> str:
    """현재 시간을 반환하는 도구"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def say_hello() -> str:
    """인사 도구"""
    return "안녕하세요! 어떤 걸 도와드릴까요?"

TOOLS = [
    {
        "name": "time",
        "keywords": ["시간"],
        "function": get_current_time,
    },
    {
        "name": "hello",
        "keywords": ["안녕"],
        "function": say_hello,
    }
]

def run_agent(user_message: str) -> str:
    for tool in TOOLS:
        if any(keyword in user_message for keyword in tool["keywords"]):
            result = tool["function"]()
            return f"[{tool['name']} 도구 실행] {result}"

    # 모든 도구를 확인했는데도 일치하는 게 없을 때 반환
    return "아직 그 요청을 처리하는 방법을 몰라요."
    
def main():
    print("에이전트 시작! 종료하려면 '종료'를 입력하세요")
    conversation_history = []
    
    while True:
        user_message = input("나: ").strip()
        
        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break
        
        answer = run_agent(user_message)
        
        conversation_history.append({
            "user": user_message,
            "assistant": answer,
        })

        print(f"에이전트: {answer}")
    
    with open("conversation.json", "w", encoding="utf-8") as file:
        json.dump(conversation_history, file, ensure_ascii=False, indent=2)
        
    print("대화 기록을 conversation.json에 저장했어요.")
    
    # 이번 실행의 대화 기록 출력
    print("\n이번 대화 기록:")
    for turn in conversation_history:
        print(f"나: {turn['user']}")
        print(f"에이전트: {turn['assistant']}")
        
        
        
if __name__ == "__main__":
    main()