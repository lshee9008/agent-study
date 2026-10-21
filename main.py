def get_current_time() -> str:
    """현재 시간을 알려주는 도구."""
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def run_agent(user_message: str) -> str:
    """사용자 요청에 맞는 도구를 선택하고 실행한다."""
  
    if "시간" in user_message:
        return f"현재 시간은 {get_current_time()}입니다."
    
    if "안녕" in user_message:
        return "안녕하세요! 어떤걸 도와드릴까요?"
    
    return "아직 그 요청을 처리하는 방법을 몰라요."


def main():
    print("에이전트 시작! 종료하려면 '종료'를 입력하세요.")
    
    while True:
        user_message = input("나: ")
        
        if user_message.strip().lower() in {"exit", "종료"}:
            print("에이전트: 다음에 또 만나요!")
            break

        answer = run_agent(user_message)
        
        print(f"에이전트: {answer}")
        
        
if __name__ == "__main__":
    main()