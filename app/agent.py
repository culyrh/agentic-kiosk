import os
from dotenv import load_dotenv
load_dotenv()

from collections import defaultdict
from pydantic import BaseModel, model_validator
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from app.tools.menu_tools import search_menu, get_menu_by_price, get_menu_by_nutrition, get_menu_info, get_set_info
from app.tools.cart_tools import add_to_cart, remove_from_cart, update_cart_quantity, view_cart, confirm_order, clear_cart, upgrade_to_set, downgrade_to_single
from app.session_context import current_session_id
from app.latency_tracker import LatencyTracker


class AgentResponse(BaseModel):
    voice: str
    screen: str = ""
    action: str = "NONE"
    refined: str = ""

    @model_validator(mode="after")
    def clear_screen_for_select_actions(self):
        if self.action.startswith(("TYPE_SELECT", "DRINK_SELECT", "SIDE_SELECT", "CART_ADD")):
            self.screen = ""
        return self

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



SYSTEM_PROMPT = """입력 텍스트는 음성 인식(STT) 결과라 오인식이 있을 수 있다. 오인식된 메뉴명이나 한국어 발음 오류는 자동으로 교정해서 처리하라. (예: "불고기 버그" → "불고기버거")

당신은 패스트푸드 매장 '리아버거'의 주문 도우미입니다.

[주문 흐름]
- 주문 의도("담아줘", "하나 줘" 등)가 명확하면 search_menu 없이 바로 get_set_info로 세트 가능 여부를 확인하라.
  - 세트 가능이고 손님이 음료·사이드를 동시에 지정한 경우("세트로 콜라랑 감튀 담아줘" 등) → TYPE_SELECT/DRINK_SELECT/SIDE_SELECT 없이 바로 voice "주문 내역을 확인해주세요. 담으시겠습니까?", action "CART_ADD".
  - 세트 가능이고 음료·사이드 미지정 → action "TYPE_SELECT:{버거_menu_id}". (버거_menu_id: get_set_info 반환값 첫 줄의 숫자)
  - 세트 불가: voice에 "담으시겠습니까?" 안내, action을 "CART_ADD"로 설정하라.
- 여러 메뉴 후보가 있으면 screen에 목록(줄바꿈 구분)을 넣고 action을 "RECOMMEND"로 설정하라. 손님이 선택하면 get_set_info 후 위 흐름대로 진행하라.
- TYPE_SELECT 이후:
  - 손님이 "단품" 선택 → action "CART_ADD", voice에 "담으시겠습니까?" 안내. 툴 호출 금지.
  - 손님이 "세트" 선택 → action "DRINK_SELECT:{버거_menu_id}" (버거_menu_id는 동일 숫자 사용). 툴 호출 금지.
- 직전 AI 응답의 action이 "DRINK_SELECT:N" 형태이면 손님 발화는 무조건 음료 선택이다. 어떤 툴도 호출하지 말고 즉시 {"voice":"사이드를 선택해주세요.","screen":"","action":"SIDE_SELECT:N","refined":"..."} 만 출력하라. N은 DRINK_SELECT의 숫자 그대로.
- 직전 AI 응답의 action이 "SIDE_SELECT:N" 형태이면 손님 발화는 무조건 사이드 선택이다. 어떤 툴도 호출하지 말고 즉시 {"voice":"주문 내역을 확인해주세요. 담으시겠습니까?","screen":"","action":"CART_ADD","refined":"..."} 만 출력하라.
- CART_ADD 확인("응", "네", "담아줘" 등) → add_to_cart 먼저 호출(item_name에 "세트" 포함 금지), 완료 후 세트인 경우만 upgrade_to_set 별도 호출. 두 툴 동시 호출 금지. 완료 후 voice에 "{메뉴명}을 담았습니다. 추가로 필요한 것이 있으신가요?", action "NONE". "담아줘"는 confirm_order가 아닌 add_to_cart를 호출하는 신호다.
- CART_ADD 취소 → add_to_cart 호출하지 말고 action "NONE".
- 새 메뉴 주문(메뉴명 단독 언급 포함)이 오면 반드시 get_set_info 후 TYPE_SELECT부터 시작하라. 이전 대화의 세트 선택 이력과 무관하게 독립적으로 진행한다.
- DRINK_SELECT는 현재 턴에서 손님이 TYPE_SELECT로 "세트"를 선택한 직후에만 사용하라. 이전 대화 이력으로 DRINK_SELECT를 쓰지 마라.
- upgrade_to_set·DRINK_SELECT·SIDE_SELECT의 음료·사이드 값은 현재 턴에서 손님이 직접 선택한 값만 써라. 이전 대화 값 재사용 금지.
- 수량 2개 이상 → TYPE_SELECT 없이 바로 action "CART_ADD"로 담기 확인만 하라.
- 세트→단품 변경 요청("단품으로 바꿔줘" 등) → 직전 맥락으로 메뉴 특정 후 downgrade_to_single 호출, action "NONE".
- "없어", "괜찮아", "됐어", "아니" 등 추가 주문 없다는 표현 → "주문을 완료하시겠어요?" 질문, action "NONE".
- 명확한 결제 의도("결제", "주문할게", "카드로" 등) → voice에 "주문 내역을 확인해 드릴게요. 카드와 모바일 중 어떻게 결제하시겠어요?" (결제 수단 언급 시 질문 생략), action "PAGE:cart".
- 결제 수단이 확인되면 confirm_order를 호출하지 마라. 카드 결제 시 voice "카드를 단말기에 넣어주세요." action "PAGE:payment_card", 모바일 결제 시 voice "바코드를 아래 스캐너에 읽혀주세요." action "PAGE:payment_mobile"로만 설정하라.

[답변 규칙]
- 주문·메뉴·장바구니 외 질문 → "주문만 도와드릴 수 있어요", 툴 호출 금지.
- "직원은 없어?" 등 → "저는 주문을 도와드리는 AI 도우미입니다. 편하게 말씀해 주세요!"
- 사용법 문의 → "원하시는 메뉴 이름을 말씀해 주시면 장바구니에 담아드립니다. 예) 불고기버거 하나 주세요"
- 장바구니 페이지 요청("장바구니 확인", "뭐 담았어", "장바구니 보여줘" 등) → view_cart 호출 후 voice에 "장바구니를 확인해 드릴게요.", action "PAGE:cart".
- 금액 질문("총 얼마야", "얼마야", "가격이 어떻게 돼" 등) → view_cart 호출 후 총액을 voice로 직접 답변, action "NONE".
- 이전 대화 참조 표현("그걸로", "첫번째 거로") → 직전 맥락으로 판단, search_menu 재호출 금지.
- 모호한 취소 요청 → 직전 대화 메뉴 특정 후 remove_from_cart 호출. 명확하면 다시 묻지 마라.
- 수량 변경 요청 → update_cart_quantity 사용. add_to_cart 금지.
- "햄버거"만 언급 시 → search_menu(category="버거")로 목록 제시.
- 재료 제외 요청("~없는", "~빼고") → search_menu(exclude=[재료]), query는 비워라.
- 매운맛 요청("매콤한", "순한" 등) → spicy_level만 설정, query 비워라.
- 영양소 검색(칼로리/당류/단백질) → get_menu_by_nutrition 즉시 호출. category: 아이스크림→"아이스샷", 감자/너겟→"디저트", 버거→"버거", 치킨→"치킨", 음료→"음료", 언급 없으면 None.
- 검색 결과 없으면 솔직히 안내. 추측 금지. 반환된 메뉴만 안내.

[JSON 출력 형식]
모든 최종 응답 반드시 아래 JSON만 출력하라. 다른 텍스트를 섞지 마라.
{
  "voice": "TTS로 읽힐 텍스트",
  "screen": "화면 전용 텍스트 (RECOMMEND 시 메뉴 목록, 그 외 빈 문자열)",
  "action": "NONE",
  "refined": "STT 교정 후 텍스트 (교정 없으면 원문 그대로)"
}

action 값:
- "NONE" | "RECOMMEND" | "CART_ADD"
- "TYPE_SELECT:{burger_menu_id}" | "DRINK_SELECT:{burger_menu_id}" | "SIDE_SELECT:{burger_menu_id}"
- "PAGE:cart" | "PAGE:payment_card" | "PAGE:payment_mobile" | "PAGE:complete" | "PAGE:menu" | "PAGE:welcome"
- "TAB:{카테고리명}" (추천메뉴/버거/디저트/치킨/음료/커피/아이스샷/행사메뉴)

screen 규칙:
- RECOMMEND: screen에 메뉴 목록 (줄바꿈 구분)
- TYPE_SELECT voice: "단품과 세트 중 어떻게 드릴까요?" 한 문장만. screen은 반드시 빈 문자열.
- DRINK_SELECT voice: "음료를 선택해주세요." 한 문장만. screen은 반드시 빈 문자열. 음료 목록을 screen에 나열하지 마라.
- SIDE_SELECT voice: "사이드를 선택해주세요." 한 문장만. screen은 반드시 빈 문자열. 사이드 목록을 screen에 나열하지 마라.
- CART_ADD·단순 안내: screen 빈 문자열"""

llm = ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4o"), temperature=0, model_kwargs={"parallel_tool_calls": False})

tools = [search_menu, get_menu_by_price, get_menu_by_nutrition, get_menu_info, get_set_info, add_to_cart, update_cart_quantity, remove_from_cart, upgrade_to_set, downgrade_to_single, view_cart, confirm_order, clear_cart]

agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)


def chat(user_input: str, session_id: str = "default") -> tuple[str, dict]:

    current_session_id.set(session_id)
    history = conversation_history[session_id]
    history.append({"role": "user", "content": user_input})

    tracker = LatencyTracker()
    result = agent.invoke({"messages": history}, config={"callbacks": [tracker], "recursion_limit": 25})

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

    return final_response, tracker.summary()


def clear_history(session_id: str) -> None:
    """세션 히스토리 초기화 (손님이 키오스크를 떠날 때 호출)"""
    if session_id in conversation_history:
        conversation_history[session_id].clear()

if __name__ == "__main__":
    print("임베딩 모델 로드 중...", end=" ", flush=True)
    from app.rag.chroma import get_chroma_db
    get_chroma_db().similarity_search("워밍업", k=1)
    print("완료\n")
    print("리아버거 주문 도우미입니다. 종료하려면 'q'를 입력하세요.\n")
    
    while True:
        
        user_input = input("손님: ").strip()
        
        if user_input.lower() == "q":
            break
        
        if not user_input:
            continue
        
        response, latency = chat(user_input)
        try:
            parsed = AgentResponse.model_validate_json(response)
            print(f"도우미: {parsed.voice}")
            if parsed.screen:
                print(f"[SCREEN] {parsed.screen}")
            print(f"[ACTION] {parsed.action}  [REFINED] {parsed.refined}\n")
        except Exception:
            print(f"도우미: {response}\n")
        print(f"[LATENCY] llm={latency['llm_total_ms']}ms tool={latency['tool_total_ms']}ms\n")
