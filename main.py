import json
from datetime import datetime
from pathlib import Path


HISTORY_FILE = Path("conversation.json")


def get_current_time() -> str:
    """현재 시간을 반환하는 도구."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def say_hello() -> str:
    """인사 도구."""
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
    },
]


def load_history() -> list[dict[str, str]]:
    """저장된 대화 기록을 불러온다. 파일이 없으면 빈 기록을 반환한다."""
    if not HISTORY_FILE.exists():
        return []

    with HISTORY_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_history(history: list[dict[str, str]]) -> None:
    """대화 기록 전체를 JSON 파일에 저장한다."""
    with HISTORY_FILE.open("w", encoding="utf-8") as file:
        json.dump(history, file, ensure_ascii=False, indent=2)


def run_agent(user_message: str) -> str:
    for tool in TOOLS:
        if any(keyword in user_message for keyword in tool["keywords"]):
            result = tool["function"]()
            return f"[{tool['name']} 도구 실행] {result}"

    return "아직 그 요청을 처리하는 방법을 몰라요."


def main():
    conversation_history = load_history()
    print(f"이전 대화 {len(conversation_history)}개를 불러왔어요.")
    print("에이전트 시작! 종료하려면 '종료'를 입력하세요.")

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

        save_history(conversation_history)
        print(f"에이전트: {answer}")

    print(f"전체 대화 {len(conversation_history)}개를 {HISTORY_FILE}에 저장했어요.")


if __name__ == "__main__":
    main()