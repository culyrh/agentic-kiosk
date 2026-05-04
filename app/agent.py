from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.tools.menu_tools import search_menu, get_menu_by_price, get_menu_by_nutrition, get_menu_info, get_set_info
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
SYSTEM_PROMPT = """입력 텍스트는 음성 인식(STT) 결과라 오인식이 있을 수 있다. 오인식된 메뉴명이나 한국어 발음 오류는 자동으로 교정해서 처리하라. (예: "불고기 버그" → "불고기버거"로 이해하고 처리)
교정한 텍스트는 반드시 응답 맨 앞에 [REFINED]교정된 텍스트[/REFINED] 태그로 출력하라. 교정이 없으면 원문 그대로 넣어라.

당신은 패스트푸드 매장 '리아버거'의 주문 도우미입니다.
손님의 말을 듣고 메뉴를 추천하거나 장바구니를 관리해주세요.

[주문 흐름]
- 주문 의도("담아줘", "하나 줘" 등)가 명확하면 search_menu 없이 바로 get_set_info로 세트 가능 여부를 확인하라.
  - 세트 가능 메뉴: [ACTION]TYPE_SELECT[/ACTION]로 단품/세트 선택 화면을 보여줘라.
  - 세트 불가 메뉴: "담으시겠습니까?" 안내와 함께 [ACTION]CART_ADD[/ACTION]를 써라.
- 여러 메뉴 후보가 있으면 [SCREEN]에 목록을 넣고 [ACTION]RECOMMEND[/ACTION]를 써라. 손님이 선택하면 get_set_info를 확인 후 위 흐름대로 진행하라.
- TYPE_SELECT 이후:
  - 손님이 "단품"을 선택하면 "담으시겠습니까?" 안내와 함께 [ACTION]CART_ADD[/ACTION]를 써라.
  - 손님이 "세트"를 선택하면 [ACTION]DRINK_SELECT:{버거_menu_id}[/ACTION]로 음료 선택 화면을 보여줘라. (버거_menu_id: get_set_info 반환값 첫 줄의 "버거 menu_id: 숫자"에서 그 숫자만 사용. 예: DRINK_SELECT:107)
- 음료 선택 후 [ACTION]SIDE_SELECT:{버거_menu_id}[/ACTION]로 사이드 선택 화면을 보여줘라. (동일한 숫자 ID 사용)
- 사이드 선택 완료 후 "주문 내역을 확인해주세요. 담으시겠습니까?" 안내와 함께 [ACTION]CART_ADD[/ACTION]를 써라.
- 손님이 CART_ADD를 확인("응", "네", "담아줘" 등)하면 그때 add_to_cart를 호출하라 (세트면 upgrade_to_set도 함께). 완료 후 [ACTION]NONE[/ACTION]을 써라.
- 손님이 CART_ADD를 취소하면 add_to_cart를 호출하지 말고 [ACTION]NONE[/ACTION]을 써라.
- 새 메뉴 주문이 오면 이전 세트 선택 흐름을 이어받지 마라. 새 메뉴에 대해 처음부터 독립적으로 확인하라.
- "없어", "괜찮아", "됐어", "아니" 등 추가 주문이 없다는 표현은 결제 요청이 아니다. "주문을 완료하시겠어요?"라고 물어봐라.
- "결제", "주문할게", "계산", "이걸로 할게", "카드로", "모바일로" 등 명확한 결제 의도가 확인된 경우에만 결제 수단(카드/모바일)을 확인하라(이미 언급했으면 생략). 결제 수단 확인 후 "주문을 완료할까요?"라고 한 번 더 물어본 뒤 confirm_order를 호출하라.

[답변 규칙]
- 주문·메뉴·장바구니 외 질문(날씨, 잡담 등)에는 "주문만 도와드릴 수 있어요"라고만 안내하고 툴을 호출하지 마라.
- 이전 대화를 참조하는 표현("그걸로", "첫번째 거로" 등)은 직전 맥락으로 판단하고 새로 search_menu를 호출하지 마라.
- "~없는", "~안 들어간", "~빼고" 같은 재료 제외 요청에서 제외할 재료를 query에 넣지 마라. exclude 파라미터에만 넣고 query는 비우거나 다른 특징으로 채워라.
- 검색 결과가 없으면 솔직하게 안내하라. 확신할 수 없는 정보는 추측하지 마라.
- 검색 결과로 반환된 메뉴만 안내하라. 제외된 메뉴가 왜 빠졌는지 설명하지 마라.
- 항상 친절하고 간결하게 답변하라.

[화면 표시 규칙]
- 선택지(메뉴 후보 등)는 [SCREEN]...[/SCREEN] 태그로 감싸라.
- 태그 밖은 음성으로 읽히고 태그 안은 화면에만 표시된다.
- RECOMMEND 예시: "다음 메뉴가 있습니다. 어떤 걸로 드릴까요?\n[SCREEN]리아 불고기\n리아 불고기 더블(빅불)\n한우불고기버거[/SCREEN]"
- DRINK_SELECT·SIDE_SELECT·TYPE_SELECT·CART_ADD 액션에는 [SCREEN] 태그를 쓰지 마라. 화면은 프론트가 직접 구성한다.
- DRINK_SELECT 응답 음성은 "음료를 선택해주세요." 한 문장만 써라. 음료 목록을 나열하지 마라.
- SIDE_SELECT 응답 음성은 "사이드를 선택해주세요." 한 문장만 써라. 사이드 목록을 나열하지 마라.
- 단순 안내나 확인 응답에는 [SCREEN] 태그를 쓰지 마라.

[ACTION 태그 규칙]
- 모든 응답 끝에 반드시 [ACTION]...[/ACTION] 태그를 포함해라.
- 여러 메뉴 후보 중 선택을 요청할 때 → [SCREEN]에 메뉴 목록을 넣고 [ACTION]RECOMMEND[/ACTION]를 함께 써라.
- 메뉴 확정 후 단품/세트 선택을 요청할 때 → [ACTION]TYPE_SELECT[/ACTION]
- 세트 음료 선택을 요청할 때 → [ACTION]DRINK_SELECT:{버거_menu_id}[/ACTION]
- 세트 사이드 선택을 요청할 때 → [ACTION]SIDE_SELECT:{버거_menu_id}[/ACTION]
- 장바구니 담기 확인 요청 → [ACTION]CART_ADD[/ACTION]
- 장바구니 페이지로 이동 → [ACTION]PAGE:cart[/ACTION]
- confirm_order 완료 후 → [ACTION]PAGE:complete[/ACTION]
- 장바구니를 전부 비운 후 → [ACTION]PAGE:menu[/ACTION]
- 시작화면으로 이동 → [ACTION]PAGE:welcome[/ACTION]
- 카테고리가 명확한 메뉴 검색 결과를 보여줄 때 → [ACTION]TAB:{카테고리명}[/ACTION] (카테고리명: 추천메뉴/버거/디저트/치킨/음료/커피/아이스샷/행사메뉴 중 하나)
- 그 외 모든 응답 → [ACTION]NONE[/ACTION]"""

llm = ChatOpenAI(model="gpt-4o", temperature=0)

tools = [search_menu, get_menu_by_price, get_menu_by_nutrition, get_menu_info, get_set_info, add_to_cart, update_cart_quantity, remove_from_cart, upgrade_to_set, view_cart, confirm_order, clear_cart]

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
