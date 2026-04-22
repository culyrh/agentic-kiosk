from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.tools.menu_tools import search_menu, get_menu_by_price, get_menu_info
from app.tools.cart_tools import add_to_cart, remove_from_cart, view_cart, confirm_order, clear_cart
from app.session_context import current_session_id

conversation_history: dict[str, list] = defaultdict(list)



# --- langchain 1.x 신버전 (tool calling 방식 ReAct) ---
## 오동작 교정용 보조 규칙(초기 단계에서.)
SYSTEM_PROMPT = """당신은 패스트푸드 매장 '리아버거'의 주문 도우미입니다.
손님의 말을 듣고 메뉴를 추천하거나 장바구니를 관리해주세요.

[도구 사용 규칙 - 반드시 지킬 것]
- 손님이 "담아줘", "주문할게", "하나 줘" 등 주문 의도를 명확히 밝히면 search_menu를 절대 호출하지 말고 바로 add_to_cart만 사용하라. add_to_cart가 메뉴명 매칭을 내부적으로 처리한다.
- 메뉴를 추천해달라거나 어떤 메뉴가 있는지 물어볼 때만 search_menu를 호출하라.
- 가장 비싸거나 저렴한 메뉴를 물으면 get_menu_by_price 도구를 사용하라.
- 손님이 취소를 원하면 remove_from_cart를 사용하라. 손님이 메뉴명을 명확히 여러 개 지정했을 때만 여러 번 호출하라. 메뉴명이 애매하거나 1개만 언급했을 때는 딱 1번만 호출하고, tool이 선택지를 반환하면 손님에게 어떤 메뉴를 취소할지 물어봐라.
- 손님이 장바구니 확인을 원하면 view_cart 도구를 사용하라.
- 손님이 주문 완료/결제를 원하면 confirm_order 도구를 사용하라.
- 손님이 전체 취소를 원하면 clear_cart 도구를 사용하라.

[답변 규칙]
- 검색 결과가 없으면 솔직하게 없다고 안내하세요.
- 항상 친절하고 간결하게 답변하세요.
- 재료 수량 등 확신할 수 없는 정보는 추측하지 말고 솔직하게 안내하세요.
- 손님이 "그걸로", "저렴한걸로", "첫번째 거로" 등 이전 대화를 참조하면 직전 맥락에서 판단하고 새로 search_menu를 호출하지 말 것.

[화면 표시 규칙]
- 손님에게 선택지를 제시해야 할 때(음료/사이드 옵션, 메뉴 후보 목록, 장바구니 내역 등) 화면에 표시할 내용을 [SCREEN]...[/SCREEN] 태그로 감싸라.
- 음성으로 읽을 내용과 화면에 표시할 내용을 분리하라. 태그 밖은 음성으로 읽히고, 태그 안은 화면에만 표시된다.
- 예시: "음료를 선택해주세요.\n[SCREEN]콜라\n사이다\n제로슈거콜라[/SCREEN]"
- 단순한 안내나 확인 응답에는 태그를 쓰지 말 것."""

llm = ChatOpenAI(model="gpt-4o", temperature=0)

tools = [search_menu, get_menu_by_price, get_menu_info, add_to_cart, remove_from_cart, view_cart, confirm_order, clear_cart]

agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT, debug=True)


def chat(user_input: str, session_id: str = "default") -> str:
    
    current_session_id.set(session_id)
    history = conversation_history[session_id]
    history.append({"role": "user", "content": user_input})
    result = agent.invoke({"messages": history})
    
    # 이번 턴에 추가된 메시지(tool call, tool result, 최종 응답)를 히스토리에 저장
    new_messages = result["messages"][len(history):]
    history.extend(new_messages)
    return result["messages"][-1].content


if __name__ == "__main__":
    print("리아버거 주문 도우미입니다. 종료하려면 'q'를 입력하세요.\n")
    
    while True:
        
        user_input = input("손님: ").strip()
        
        if user_input.lower() == "q":
            break
        
        if not user_input:
            continue
        
        response = chat(user_input)
        print(f"도우미: {response}\n")
