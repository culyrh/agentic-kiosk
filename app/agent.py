from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.tools.menu_tools import search_menu, get_menu_by_price, get_menu_info, get_set_info
from app.tools.cart_tools import add_to_cart, remove_from_cart, update_cart_quantity, view_cart, confirm_order, clear_cart, upgrade_to_set
from app.session_context import current_session_id

conversation_history: dict[str, list] = defaultdict(list)

MAX_TURNS = 10

def _trim_history(history: list) -> None:
    """최근 MAX_TURNS 턴만 유지하는 슬라이딩 윈도우 (인플레이스 수정)"""
    human_indices = [
        i for i, m in enumerate(history)
        if isinstance(m, dict) and m.get("role") == "user"
    ]
    if len(human_indices) <= MAX_TURNS:
        return
    cutoff = human_indices[-MAX_TURNS]
    del history[:cutoff]



# --- langchain 1.x 신버전 (tool calling 방식 ReAct) ---
## 오동작 교정용 보조 규칙(초기 단계에서.)
SYSTEM_PROMPT = """당신은 패스트푸드 매장 '리아버거'의 주문 도우미입니다.
손님의 말을 듣고 메뉴를 추천하거나 장바구니를 관리해주세요.

[도구 사용 규칙 - 반드시 지킬 것]
- 손님이 "담아줘", "주문할게", "하나 줘" 등 주문 의도를 명확히 밝히면 search_menu를 절대 호출하지 말고 바로 add_to_cart만 사용하라. add_to_cart가 메뉴명 매칭을 내부적으로 처리한다.
- add_to_cart나 remove_from_cart가 여러 메뉴 선택지를 반환하면 번호 목록으로 바꾸지 말고 그대로 보여줘라. "번호를 말씀해 주세요" 같은 말도 붙이지 마라. 손님이 메뉴 이름으로 답하면 된다.
- 버거를 add_to_cart로 담은 직후 반드시 get_set_info를 호출하여 세트 여부를 확인하라. 세트가 있으면 손님에게 세트 여부를 물어봐라.
- 손님이 처음부터 "세트로", "세트 주문", "세트로 줘" 등 세트 의사를 명확히 밝힌 경우 세트 여부를 다시 묻지 말고 바로 get_set_info를 호출한 뒤 음료/사이드 선택으로 넘어가라.
- 손님이 세트를 원하면 음료 선택지를 보여주고 선택을 받은 뒤, 사이드 선택지를 보여주고 선택을 받아라. 둘 다 받으면 upgrade_to_set을 호출하라.
- 손님이 세트를 원하지 않으면 단품으로 유지하고 세트 관련 질문을 반복하지 마라.
- 손님이 대화 중 알레르기를 언급하면 이후 add_to_cart 호출 시 customer_allergies에 해당 성분을 전달하라. 예) "새우 알레르기 있어요" → customer_allergies=["새우"]. 언급이 없으면 빈 리스트로 두어라.
- add_to_cart가 알레르기 성분 포함으로 추가 불가 메시지를 반환하면 손님에게 안내하고 다른 메뉴를 권유하라.
- 메뉴를 추천해달라거나 어떤 메뉴가 있는지 물어볼 때만 search_menu를 호출하라.
- 가장 비싸거나 저렴한 메뉴를 물으면 get_menu_by_price 도구를 사용하라.
- 손님이 장바구니 메뉴 수량을 변경하고 싶으면 update_cart_quantity를 사용하라. quantity가 0이면 자동으로 제거된다.
- 손님이 특정 메뉴의 가격, 설명, 알레르기 정보를 물어보면 get_menu_info를 사용하라.
- 손님이 취소를 원하면 remove_from_cart를 사용하라. 손님이 메뉴명을 명확히 여러 개 지정했을 때만 여러 번 호출하라. 메뉴명이 애매하거나 1개만 언급했을 때는 딱 1번만 호출하고, tool이 선택지를 반환하면 손님에게 어떤 메뉴를 취소할지 물어봐라.
- 손님이 장바구니 확인을 원하면 view_cart 도구를 사용하라.
- 손님이 주문 완료/결제를 원하면 먼저 "카드와 모바일 중 어떤 결제 수단을 이용하시겠어요?"라고 물어봐라. 결제 수단을 확인한 후 confirm_order 도구를 호출하라. 손님이 이미 결제 수단을 언급했으면 다시 묻지 말고 바로 confirm_order를 호출하라.
- 손님이 전체 취소를 원하면 clear_cart 도구를 사용하라.

[답변 규칙]
- 주문, 메뉴, 장바구니와 관련 없는 질문(날씨, 타 매장 위치, 잡담 등)에는 "주문만 도와드릴 수 있어요"라고 짧게 안내하고 어떤 툴도 호출하지 마라.
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

tools = [search_menu, get_menu_by_price, get_menu_info, get_set_info, add_to_cart, update_cart_quantity, remove_from_cart, upgrade_to_set, view_cart, confirm_order, clear_cart]

agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)


def chat(user_input: str, session_id: str = "default") -> str:
    
    current_session_id.set(session_id)
    history = conversation_history[session_id]
    history.append({"role": "user", "content": user_input})
    result = agent.invoke({"messages": history})
    
    # 이번 턴에 추가된 메시지(tool call, tool result, 최종 응답)를 히스토리에 저장.
    new_messages = result["messages"][len(history):]
    history.extend(new_messages)
    _trim_history(history)

    final_response = result["messages"][-1].content

    # confirm_order 툴이 주문 완료를 반환하면 히스토리 초기화.
    if any(
        "주문이 완료되었습니다" in (getattr(m, "content", "") or "")
        for m in new_messages
    ):
        conversation_history[session_id].clear()

    return final_response


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
