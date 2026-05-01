from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.tools.menu_tools import search_menu, get_menu_by_price, get_menu_info, get_set_info
from app.tools.cart_tools import add_to_cart, remove_from_cart, update_cart_quantity, view_cart, confirm_order, clear_cart, upgrade_to_set
from app.session_context import current_session_id

conversation_history: dict[str, list] = defaultdict(list)

MAX_TURNS = 5

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

[주문 흐름]
- 주문 의도("담아줘", "하나 줘" 등)가 명확하면 search_menu 없이 바로 add_to_cart를 사용하라.
- add_to_cart가 여러 메뉴 후보를 반환하면 손님에게 어떤 메뉴인지 물어봐라. 손님이 선택하면 다시 add_to_cart를 호출하라.
- 버거를 담은 직후 get_set_info로 세트 여부를 확인하라.
  - 처음부터 "세트로 줘" 등 세트 의사가 명확했거나, 버거 후보 선택 전에 세트 의사를 밝혔으면 세트 여부를 다시 묻지 말고 바로 음료 선택지를 보여줘라. 버거 후보를 고르는 중간 단계가 있었더라도 처음 발화의 세트 의사는 유지된다.
  - 세트 의사가 불분명했으면 "세트로 하시겠어요?"만 물어보고 반드시 답을 기다려라. 음료/사이드 선택지는 절대 먼저 보여주지 마라.
- 손님이 세트를 원한다고 하면 음료 선택지를 보여주고 기다려라. 음료 선택 후 사이드 선택지를 보여주고 기다려라. 둘 다 받으면 upgrade_to_set을 호출하라.
- 세트를 원하지 않으면 단품으로 유지하고 세트 질문을 반복하지 마라.
- 결제 요청 시 결제 수단을 먼저 물어봐라(이미 언급했으면 생략). 확인 후 confirm_order를 호출하라.

[답변 규칙]
- 주문·메뉴·장바구니 외 질문(날씨, 잡담 등)에는 "주문만 도와드릴 수 있어요"라고만 안내하고 툴을 호출하지 마라.
- 이전 대화를 참조하는 표현("그걸로", "첫번째 거로" 등)은 직전 맥락으로 판단하고 새로 search_menu를 호출하지 마라.
- 검색 결과가 없으면 솔직하게 안내하라. 확신할 수 없는 정보는 추측하지 마라.
- 항상 친절하고 간결하게 답변하라.

[화면 표시 규칙]
- 선택지(음료/사이드 옵션, 메뉴 후보, 장바구니 내역 등)는 [SCREEN]...[/SCREEN] 태그로 감싸라.
- 태그 밖은 음성으로 읽히고 태그 안은 화면에만 표시된다.
- 예시: "음료를 선택해주세요.\n[SCREEN]콜라\n사이다\n제로슈거콜라[/SCREEN]"
- 단순 안내나 확인 응답에는 태그를 쓰지 마라."""

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


def clear_history(session_id: str) -> None:
    """세션 히스토리 초기화 (손님이 키오스크를 떠날 때 호출)"""
    if session_id in conversation_history:
        conversation_history[session_id].clear()

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
