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
        # any(...)는 여러 조건 중 하나라도 참이면 True를 돌려줌
        # for keyword in tool["keywords"]가 키워드를 하나씩 꺼냄
        # any(...)가 결과 중 하나라도 True인지 판단
        # 참이면 if 안의 도구 실행 코드로 돌아감
        if any(keyword in user_message for keyword in tool["keywords"]):
            result = tool["function"]()
            return f"[{tool['name']} 도구 실행] {result}"
        
        return "아직 그 요청을 처리하는 방법을 몰라요"
    
def main():
    print("에이전트 시작! 종료하려면 '종료'를 입력하세요")
    
    while True:
        user_message = input("나: ").strip()
        
        if user_message.lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        print(f"에이전트: {run_agent(user_message)}")
        
if __name__ == "__main__":
    main()