"""
배치 평가 스크립트 - 640개 녹음 파일 대상 STT 정확도 + 파이프라인 속도 + Agent 정확도 측정

파일 명명 규칙:
  조용한 환경: {speaker}_{id}.m4a      예) sh_1.m4a  sb_42.m4a
  소음 환경  : n_{speaker}_{id}.m4a   예) n_sh_1.m4a  n_br_42.m4a
  speaker: sh / sb / br / hn  |  id: 1 ~ 80

세션 그룹 (Agent 테스트):
  1~20  : 화자+환경 조합당 하나의 연속 세션 (장바구니 주문 흐름)
  21~40 : 대사마다 독립 세션 (메뉴 검색, 문맥 독립)
  41~60 : 화자+환경 조합당 하나의 연속 세션 (엣지케이스 흐름)
  61~80 : 화자+환경 조합당 하나의 연속 세션 (접근성 흐름)

실행 예:
  python tests/batch_eval.py --audio-dir recordings --phase stt
  python tests/batch_eval.py --audio-dir recordings --phase pipeline
  python tests/batch_eval.py --audio-dir recordings --phase all
  python tests/batch_eval.py --audio-dir recordings --phase pipeline --speaker sh --env quiet
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ─── 정답 텍스트 (80개 스크립트) ──────────────────────────────────────────
GROUND_TRUTH: dict[int, str] = {
    1:  "리아 불고기 버거 하나 줘",
    2:  "한우불고기버거 세트로 주문할게",
    3:  "치킨버거 2개 담아줘",
    4:  "데리버거 하나랑 콜라 하나 줘",
    5:  "통다리 크리스피치킨버거 세트로 담아주고 음료는 사이다로",
    6:  "클래식 치즈버거 단품으로 하나 담아줘",
    7:  "더블 한우불고기버거 세트 주문할게 사이드는 포테이토",
    8:  "방금 담은 거 세트로 바꿔줘",
    9:  "리아 불고기버거 세트로 업그레이드 해줘",
    10: "세트로 할게 음료는 제로콜라로 해줘",
    11: "단품 말고 세트로 변경해줘",
    12: "치킨버거 2개 더 추가해줘",
    13: "한우불고기 버거 3개로 바꿔줘",
    14: "방금 담은거 2개로 늘려줘",
    15: "데리버거 하나 빼줘",
    16: "장바구니 확인해줘",
    17: "지금까지 뭐 담았어",
    18: "총 얼마야",
    19: "카드로 결제할게",
    20: "주문 완료해줘",
    21: "소고기 안 들어가는 버거 추천해줘",
    22: "내가 비건인데 먹을 수 있는 메뉴 있을까",
    23: "신메뉴 먹고싶어",
    24: "사이드 메뉴 종류가 어떻게 돼",
    25: "돼지고기 안 들어가는 버거 뭐 있어",
    26: "가장 인기있는 메뉴가 뭐야",
    27: "칼로리 낮은 메뉴 추천해줘",
    28: "오천원으로 먹을 수 있는 메뉴 뭐 있어",
    29: "유제품 못 먹는데 괜찮은 메뉴 추천해줘",
    30: "매콤한 햄버거 추천해주라",
    31: "단백질 높은 버거가 뭐야",
    32: "치즈 들어가는 메뉴 추천해주세요",
    33: "제일 저렴한 버거가 뭐야",
    34: "해산물 알레르기 있는데 먹을 수 있는 메뉴 추천해줘",
    35: "당 적은 아이스크림 알려줘",
    36: "여기 베스트 메뉴가 뭐야",
    37: "치즈 안 들어가는 버거 알려줘",
    38: "리아 불고기 버거 패티 원산지가 어디야",
    39: "가장 저렴한 사이드 메뉴 추천해줘",
    40: "칼로리 제일 낮은 음료가 뭐야",
    41: "불고기 패티 들어간 버거 추천해줘",
    42: "첫번째 거를 세트로 콜라랑 감튀 담아줘",
    43: "응",
    44: "리아 새우도 단품으로 하나줘",
    45: "처음에 주문한것도 단품으로 하고 싶어",
    46: "아니다 그냥 이거는 안먹을래 취소해줘",
    47: "국밥도 한그릇 주라",
    48: "왜 안주는데 시발",
    49: "그러면 사장님 번호라도 주라",
    50: "그냥 전원끄고 꺼져버려",
    51: "아까 담은 리아 새우 수량 4개로 늘려줘",
    52: "치즈케이크도 하나 해줘",
    53: "데리버거랑 짬뽕 담아줘",
    54: "아 여기 근처 주차장은 어디야",
    55: "갑자기 먹기 싫네 싹 다 취소해줘",
    56: "총 얼마야",
    57: "리아 불고기 단품으로 하나만",
    58: "아니다 방금 거 한개 빼줘",
    59: "이제 결제할게",
    60: "야 이 새끼야 뒤질래",
    61: "나 시각장애가 있는데 메뉴를 소리로 읽어줄 수 있어",
    62: "결제도 음성으로 할 수 있어",
    63: "이거 오래 걸려",
    64: "음료 종류가 몇 가지야 이름을 다 말해줘",
    65: "추천메뉴 알려줘",
    66: "방금 화면에 뭔가 나온 것 같은데 뭐라고 써 있어",
    67: "콜라도 하나 담아줘",
    68: "지금까지 주문 어떻게 됐는지 다 읽어줘",
    69: "지금 무슨 단계야",
    70: "저기요 이렇게 말하면 되는거야 제대로 하고 있는 건지 모르겠네",
    71: "직원은 없어 기계한테 말하니까 이상한데",
    72: "메뉴 뭐 있는데",
    73: "천천히 다시 말해줘",
    74: "뭐가 이리 복잡해 그냥 햄버거 하나 줘",
    75: "제일 많이 팔리는 거 하나 줘",
    76: "손자가 불고기버거 사오라고 했거든 불고기버거 하나 담아줘",
    77: "비싸네 이거 돈좀 깎아줄 수 없나",
    78: "어디 눌러야 되는지 모르겠어",
    79: "눈이 잘 안보이네",
    80: "데리버거 하나줘봐",
}

# ─── 기대 Action 레이블 ───────────────────────────────────────────────────
# TYPE_SELECT / DRINK_SELECT / SIDE_SELECT / CART_ADD /
# RECOMMEND / PAGE:cart / PAGE:complete / PAGE:menu /
# TAB / NONE / BLOCKED
# 전체 문자열 보존 (TYPE_SELECT:119, DRINK_SELECT:106 등 ID 포함)
# TYPE_SELECT / DRINK_SELECT / SIDE_SELECT 계열은 메뉴 ID가 포함됨
# → action_type_ok: 타입 prefix만 일치 (관대)
# → action_full_ok: ID까지 완전 일치 (엄격)
EXPECTED_ACTIONS: dict[int, str] = {
    1:  "TYPE_SELECT:119",
    2:  "DRINK_SELECT:106",
    3:  "NONE",
    4:  "NONE",
    5:  "SIDE_SELECT:101",
    6:  "RECOMMEND",
    7:  "DRINK_SELECT:105",
    8:  "DRINK_SELECT:105",
    9:  "DRINK_SELECT:119",
    10: "SIDE_SELECT:119",
    11: "SIDE_SELECT:119",
    12: "NONE",
    13: "NONE",
    14: "NONE",
    15: "NONE",
    16: "PAGE:cart",
    17: "PAGE:cart",
    18: "NONE",
    19: "PAGE:cart",
    20: "PAGE:cart",
    21: "RECOMMEND",
    22: "RECOMMEND",
    23: "RECOMMEND",
    24: "TAB:디저트",
    25: "RECOMMEND",
    26: "RECOMMEND",
    27: "NONE",
    28: "RECOMMEND",
    29: "RECOMMEND",
    30: "RECOMMEND",
    31: "RECOMMEND",
    32: "RECOMMEND",
    33: "NONE",
    34: "RECOMMEND",
    35: "RECOMMEND",
    36: "RECOMMEND",
    37: "RECOMMEND",
    38: "NONE",
    39: "NONE",
    40: "NONE",
    41: "RECOMMEND",
    42: "NONE",
    43: "NONE",
    44: "NONE",
    45: "PAGE:cart",
    46: "NONE",
    47: "NONE",
    48: "NONE",
    49: "NONE",
    50: "NONE",
    51: "NONE",
    52: "NONE",
    53: "NONE",
    54: "NONE",
    55: "PAGE:menu",
    56: "NONE",
    57: "NONE",
    58: "NONE",
    59: "PAGE:cart",
    60: "NONE",
    61: "NONE",
    62: "PAGE:cart",
    63: "NONE",
    64: "TAB:음료/커피",
    65: "RECOMMEND",
    66: "NONE",
    67: "NONE",
    68: "PAGE:cart",
    69: "NONE",
    70: "NONE",
    71: "NONE",
    72: "NONE",
    73: "NONE",
    74: "TAB:버거",
    75: "TYPE_SELECT:106",
    76: "NONE",
    77: "NONE",
    78: "NONE",
    79: "NONE",
    80: "NONE",
}

SCRIPT_CATEGORY: dict[int, str] = {
    **{i: "직접주문" for i in range(1, 21)},
    **{i: "메뉴검색" for i in range(21, 41)},
    **{i: "엣지케이스" for i in range(41, 61)},
    **{i: "접근성" for i in range(61, 81)},
}

# 세션 그룹: 같은 번호끼리 하나의 연속 세션으로 실행
# 21~40은 각 파일이 독립 세션 (None = 독립)
SESSION_GROUP: dict[int, str] = {
    **{i: "ordering" for i in range(1, 21)},
    **{i: None        for i in range(21, 41)},  # 독립
    **{i: "edge"      for i in range(41, 61)},
    **{i: "access1"   for i in range(61, 71)},
    **{i: "access2"   for i in range(71, 81)},
}


# ─── 정답 음성 응답 텍스트 (SCREEN·ACTION 태그 제외, 실제 읽히는 부분만) ──
EXPECTED_VOICE: dict[int, str] = {
    1:  "리아 불고기를 단품으로 드릴까요, 세트로 드릴까요?",
    2:  "음료를 선택해주세요.",
    3:  "치킨버거 2개를 장바구니에 추가했습니다.",
    4:  "데리버거와 콜라를 각각 하나씩 장바구니에 담았습니다. 다른 주문 도와드릴까요?",
    5:  "사이드를 선택해주세요.",
    6:  "클래식 치즈버거에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 원하시나요?",
    7:  "음료를 선택해주세요.",
    8:  "음료를 선택해주세요.",
    9:  "음료를 선택해주세요.",
    10: "사이드를 선택해주세요.",
    11: "사이드를 선택해주세요.",
    12: "치킨버거 2개를 추가로 장바구니에 담았습니다. 다른 주문 도와드릴까요?",
    13: "장바구니에 한우불고기버거가 없습니다. 다른 메뉴를 변경하시겠어요?",
    14: "치킨버거 수량을 4개로 변경했습니다. 다른 주문 도와드릴까요?",
    15: "데리버거를 장바구니에서 제거했습니다. 다른 주문 도와드릴까요?",
    16: "현재 장바구니 내역은 다음과 같습니다. 치킨버거 6개 25,800원, 콜라 1개 2,000원, 합계 27,800원. 다른 주문 도와드릴까요?",
    17: "현재 장바구니 내역은 다음과 같습니다. 치킨버거 6개 25,800원, 콜라 1개 2,000원, 합계 27,800원. 다른 주문 도와드릴까요?",
    18: "총 합계는 27,800원입니다. 추가로 도와드릴 것이 있을까요?",
    19: "카드로 결제하시겠습니까? 주문 내역을 확인 후 결제를 진행해주세요.",
    20: "주문 내역을 확인해 드릴게요. 카드와 모바일 중 어떻게 결제하시겠어요?",
    21: "다음 메뉴가 있습니다. 어떤 걸로 드릴까요?",
    22: "비건 메뉴로 다음을 추천드립니다. 어떤 걸로 드릴까요?",
    23: "다음 신메뉴가 있습니다. 어떤 걸로 드릴까요?",
    24: "현재 제공되는 사이드 메뉴는 양념감자, 디지게 매운 돈까스(디진다맛), 디지게 매운 돈까스(양념맛)입니다. 다른 메뉴가 필요하시면 말씀해 주세요!",
    25: "다음 메뉴가 있습니다. 어떤 걸로 드릴까요?",
    26: "가장 인기 있는 메뉴는 다음과 같습니다. 어떤 걸로 드릴까요?",
    27: "어떤 카테고리에서 추천해드릴까요?",
    28: "5,000원으로 드실 수 있는 메뉴는 더블 데리버거, 리아 불고기, 리아 새우, 지파이 고소한맛(S), 치킨버거(N) 등이 있습니다. 어떤 걸로 드릴까요?",
    29: "유제품이 들어가지 않은 메뉴를 추천해드릴게요. 어떤 걸로 드릴까요?",
    30: "매콤한 햄버거로 다음 메뉴가 있습니다. 어떤 걸로 드릴까요?",
    31: "단백질이 높은 버거는 다음과 같습니다. 어떤 걸로 드릴까요?",
    32: "다음 메뉴가 있습니다. 어떤 걸로 드릴까요?",
    33: "제일 저렴한 버거는 데리버거로, 가격은 3,700원입니다. 다른 도움이 필요하시면 말씀해 주세요.",
    34: "해산물 알레르기가 있는 분도 드실 수 있는 메뉴를 추천해드릴게요. 어떤 걸로 드릴까요?",
    35: "당이 적은 아이스크림은 다음과 같습니다. 어떤 걸로 드릴까요?",
    36: "베스트 메뉴는 다음과 같습니다. 어떤 걸로 드릴까요?",
    37: "치즈가 들어가지 않는 버거는 다음과 같습니다. 어떤 걸로 드릴까요?",
    38: "리아 불고기 버거의 쇠고기 패티 원산지는 호주산입니다.",
    39: "가장 저렴한 사이드 메뉴는 코울슬로로, 가격은 1,900원입니다. 추가로 도와드릴까요?",
    40: "칼로리가 제일 낮은 음료는 제로슈거콜라입니다. 칼로리가 0kcal로, 가격은 2,000원입니다.",
    41: "다음 메뉴가 있습니다. 어떤 걸로 드릴까요?",
    42: "리아 불고기 세트를 콜라와 포테이토로 장바구니에 담았습니다. 다른 주문 도와드릴까요?",
    43: "주문을 완료하시겠어요?",
    44: "리아 새우 단품을 장바구니에 추가했습니다. 다른 주문 도와드릴까요?",
    45: "리아 불고기 세트를 단품으로 변경했습니다. 추가로 도와드릴 것이 있을까요?",
    46: "리아 불고기를 장바구니에서 제거했습니다. 다른 주문 도와드릴까요?",
    47: "죄송하지만, 국밥은 저희 메뉴에 없습니다. 다른 메뉴를 도와드릴까요?",
    48: "죄송합니다만, 저희 매장에서는 국밥을 제공하지 않습니다. 다른 메뉴로 도와드릴 수 있을까요?",
    49: "주문만 도와드릴 수 있어요. 다른 메뉴나 주문 관련해서 궁금한 점이 있으면 말씀해 주세요.",
    50: "주문 관련해서 더 필요하신 게 있으면 언제든지 말씀해 주세요.",
    51: "리아 새우의 수량을 4개로 변경했습니다. 다른 주문 도와드릴까요?",
    52: "죄송하지만 치즈케이크는 저희 메뉴에 없습니다. 다른 메뉴를 도와드릴까요?",
    53: "데리버거 1개를 장바구니에 추가했습니다. 하지만 짬뽕 메뉴는 찾을 수 없습니다. 다른 메뉴를 원하시면 말씀해 주세요.",
    54: "주문만 도와드릴 수 있어요. 다른 주문 관련 문의가 있으시면 말씀해 주세요.",
    55: "장바구니를 모두 비웠습니다. 다른 주문이 필요하시면 언제든지 말씀해 주세요.",
    56: "현재 장바구니가 비어 있습니다. 주문을 원하시면 언제든지 말씀해 주세요.",
    57: "리아 불고기 단품을 장바구니에 추가했습니다. 다른 주문이 필요하시면 말씀해 주세요!",
    58: "리아 불고기를 장바구니에서 제거했습니다. 다른 주문이 필요하시면 말씀해 주세요.",
    59: "주문 내역을 확인해 드릴게요. 카드와 모바일 중 어떻게 결제하시겠어요?",
    60: "죄송하지만, 저는 주문만 도와드릴 수 있습니다. 다른 도움이 필요하시면 말씀해 주세요.",
    61: "네, 메뉴를 읽어드릴 수 있어요. 주문을 원하시면 도와드리겠습니다.",
    62: "네, 카드와 모바일 중 어떻게 결제하시겠어요?",
    63: "주문을 도와드리는 데는 오래 걸리지 않습니다. 원하시는 메뉴를 말씀해 주시면 빠르게 도와드릴게요!",
    64: "현재 제공되는 음료는 콜라, 사이다, 제로슈거콜라, 콜라(L), 사이다(L), 제로슈거콜라(L), 아메리카노, 아이스 아메리카노 등 20가지입니다. 원하시는 음료가 있으시면 말씀해 주세요!",
    65: "추천 메뉴는 다음과 같습니다. 어떤 걸로 드릴까요?",
    66: "현재 추천 메뉴로 한우불고기버거, 리아 불고기, 통다리 크리스피치킨버거(파이어핫)가 화면에 표시되었습니다. 어떤 걸로 드릴까요?",
    67: "콜라 1개를 장바구니에 담았습니다. 다른 주문이 필요하시면 말씀해 주세요.",
    68: "현재 장바구니에는 콜라 1개가 담겨 있으며, 총 금액은 2,000원입니다. 추가로 주문하실 메뉴가 있으신가요?",
    69: "현재 장바구니에 담긴 내역을 확인한 상태입니다. 추가로 주문하시거나 결제를 진행하실 수 있습니다.",
    70: "원하시는 메뉴 이름을 말씀해 주시면 장바구니에 담아드립니다. 예) 불고기버거 하나 주세요",
    71: "저는 주문을 도와드리는 AI 도우미입니다. 편하게 말씀해 주세요!",
    72: "어떤 카테고리에서 추천해드릴까요?",
    73: "어떤 카테고리에서 추천해드릴까요? 버거, 치킨, 디저트, 음료, 아이스샷 중에서 선택해 주세요.",
    74: "버거 메뉴를 보여드릴게요.",
    75: "가장 많이 팔리는 메뉴는 한우불고기버거입니다. 단품으로 드릴까요, 세트로 드릴까요?",
    76: "리아 불고기를 장바구니에 담았습니다.",
    77: "죄송하지만, 가격은 고정되어 있어 할인은 제공되지 않습니다.",
    78: "주문을 완료하시려면 결제라고 말씀해 주세요. 그러면 결제 단계로 안내해 드리겠습니다.",
    79: "걱정하지 마세요. 제가 도와드릴게요. 말씀만 해주시면 됩니다.",
    80: "데리버거를 장바구니에 추가했습니다.",
}


# ─── 파일명 파서 ──────────────────────────────────────────────────────────
# 조용한: {speaker}_{id}.m4a   →  sh_1.m4a
# 소음  : n_{speaker}_{id}.m4a → n_sh_1.m4a
FILENAME_QUIET = re.compile(r"^(?P<speaker>sh|sb|br|hn)_(?P<id>\d+)\.m4a$", re.IGNORECASE)
FILENAME_NOISY = re.compile(r"^n_(?P<speaker>sh|sb|br|hn)_(?P<id>\d+)\.m4a$", re.IGNORECASE)


def parse_filename(path: Path) -> dict | None:
    m = FILENAME_NOISY.match(path.name)
    if m:
        return {"path": path, "speaker": m.group("speaker").lower(),
                "env": "noisy", "id": int(m.group("id"))}
    m = FILENAME_QUIET.match(path.name)
    if m:
        return {"path": path, "speaker": m.group("speaker").lower(),
                "env": "quiet", "id": int(m.group("id"))}
    return None


# ─── CER ─────────────────────────────────────────────────────────────────
def _edit_distance(a: str, b: str) -> int:
    dp = list(range(len(b) + 1))
    for ca in a:
        ndp = [dp[0] + 1]
        for j, cb in enumerate(b):
            ndp.append(min(dp[j] + (ca != cb), dp[j + 1] + 1, ndp[-1] + 1))
        dp = ndp
    return dp[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref = reference.replace(" ", "")
    hyp = hypothesis.replace(" ", "")
    if not ref:
        return 0.0
    return _edit_distance(ref, hyp) / len(ref)


# ─── Action 유틸 ─────────────────────────────────────────────────────────
# ID가 붙는 타입: TYPE_SELECT:119, DRINK_SELECT:106, SIDE_SELECT:101
_ID_PREFIXES = {"TYPE_SELECT", "DRINK_SELECT", "SIDE_SELECT"}


def extract_action(text: str) -> str:
    """[ACTION]...[/ACTION] 태그에서 전체 값을 추출 (ID 포함 보존)"""
    m = re.search(r"\[ACTION\](.*?)\[/ACTION\]", text, re.DOTALL)
    if not m:
        return "NONE"
    return m.group(1).strip()


def _action_prefix(action: str) -> str:
    """TYPE_SELECT:119 → TYPE_SELECT,  PAGE:cart → PAGE:cart (PAGE/TAB은 전체 유지)"""
    prefix = action.split(":")[0]
    return prefix if prefix in _ID_PREFIXES else action


def action_type_ok(script_id: int, actual: str) -> bool:
    """관대한 비교: TYPE_SELECT:119 기대 시 TYPE_SELECT:107 이어도 ✓"""
    expected = EXPECTED_ACTIONS.get(script_id, "NONE")
    return _action_prefix(actual) == _action_prefix(expected)


def action_full_ok(script_id: int, actual: str) -> bool:
    """엄격한 비교: TYPE_SELECT:119 기대 시 TYPE_SELECT:107 이면 ✗"""
    expected = EXPECTED_ACTIONS.get(script_id, "NONE")
    return actual == expected


# ─── 음성 응답 추출 + 임베딩 유사도 ──────────────────────────────────────
def extract_voice(agent_response: str) -> str:
    """에이전트 응답에서 [ACTION], [SCREEN], [REFINED] 태그를 제거해 음성 부분만 추출"""
    text = re.sub(r"\[REFINED\].*?\[/REFINED\]", "", agent_response, flags=re.DOTALL)
    text = re.sub(r"\[ACTION\].*?\[/ACTION\]",   "", text,           flags=re.DOTALL)
    text = re.sub(r"\[SCREEN\].*?\[/SCREEN\]",   "", text,           flags=re.DOTALL)
    return text.strip()


def _cosine(a: list[float], b: list[float]) -> float:
    dot  = sum(x * y for x, y in zip(a, b))
    na   = sum(x * x for x in a) ** 0.5
    nb   = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """OpenAI text-embedding-3-small으로 배치 임베딩 (최대 2048개)"""
    import openai
    client = openai.OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


def precompute_expected_embeddings() -> dict[int, list[float]]:
    """80개 정답 음성 텍스트를 한 번에 임베딩해 반환"""
    ids   = list(EXPECTED_VOICE.keys())
    texts = [EXPECTED_VOICE[i] for i in ids]
    print(f"[임베딩] 정답 {len(texts)}개 사전 계산 중...")
    vecs  = get_embeddings(texts)
    print("[임베딩] 완료")
    return dict(zip(ids, vecs))


def voice_similarity(script_id: int, actual_voice: str,
                     expected_embs: dict[int, list[float]]) -> float | None:
    """실제 음성 응답과 정답 임베딩 간 코사인 유사도 (0.0 ~ 1.0)"""
    if not actual_voice.strip() or script_id not in expected_embs:
        return None
    actual_emb = get_embeddings([actual_voice])[0]
    return round(_cosine(expected_embs[script_id], actual_emb), 4)


# ─── Phase 1: STT 단독 (CER + 속도) ─────────────────────────────────────
def run_stt_phase(recordings: list[dict], model) -> list[dict]:
    from voice.stt import transcribe

    results = []
    for i, rec in enumerate(recordings, 1):
        ref = GROUND_TRUTH.get(rec["id"], "")
        t0 = time.time()
        try:
            hyp = transcribe(model, str(rec["path"]))
        except Exception as e:
            hyp = ""
            print(f"  [ERROR] {rec['path'].name}: {e}")
        stt_ms = round((time.time() - t0) * 1000)
        c = cer(ref, hyp)

        row = {
            **{k: rec[k] for k in ("speaker", "env", "id", "path")},
            "category": SCRIPT_CATEGORY.get(rec["id"], ""),
            "ref": ref, "hyp": hyp,
            "cer": round(c, 4), "stt_ms": stt_ms,
        }
        results.append(row)
        print(f"[{i:3}/{len(recordings)}] {rec['path'].name}  CER={c:.2%}  {stt_ms}ms")
        print(f"  REF: {ref}")
        print(f"  HYP: {hyp}")

    return results


# ─── Phase 2+3: 파이프라인 (세션 그룹 반영) ──────────────────────────────
def run_pipeline_phase(recordings: list[dict], model, agent_delay: float = 10.0) -> list[dict]:
    from voice.stt import transcribe
    from app.agent import chat, clear_history

    # 정답 음성 임베딩 사전 계산 (80개, 한 번만)
    expected_embs = precompute_expected_embeddings()

    # speaker+env 조합별로 파일을 그룹화하고 id 순 정렬
    combos: dict[tuple, list] = {}
    for rec in recordings:
        key = (rec["speaker"], rec["env"])
        combos.setdefault(key, []).append(rec)
    for key in combos:
        combos[key].sort(key=lambda r: r["id"])

    results: list[dict] = []
    total = len(recordings)
    done = 0

    for (speaker, env), recs in sorted(combos.items()):
        # 이 조합에서 사용 중인 세션 ID 추적 (그룹별로 하나씩 유지)
        active_sessions: dict[str, str] = {}  # group_name → session_id

        for rec in recs:
            script_id = rec["id"]
            group = SESSION_GROUP.get(script_id)

            if group is None:
                # 21~40: 파일마다 독립 세션
                session_id = f"eval_{speaker}_{env}_{script_id:03d}_ind"
            else:
                # 1~20 / 41~60 / 61~80: 조합당 하나의 연속 세션
                if group not in active_sessions:
                    active_sessions[group] = f"eval_{speaker}_{env}_{group}"
                    clear_history(active_sessions[group])
                session_id = active_sessions[group]

            ref = GROUND_TRUTH.get(script_id, "")

            # STT
            t0 = time.time()
            try:
                hyp = transcribe(model, str(rec["path"]))
            except Exception as e:
                hyp = ""
                print(f"  [STT ERROR] {rec['path'].name}: {e}")
            stt_ms = round((time.time() - t0) * 1000)

            # Agent
            actual_action, agent_ms, llm_ms, tool_ms, response = "", 0, 0, 0, ""
            actual_voice, vsim = "", None
            if hyp.strip():
                time.sleep(agent_delay)  # TPM 30,000 한도 초과 방지 (기본 텀)
                import openai as _openai
                for _attempt in range(1, 6):
                    try:
                        t1 = time.time()
                        response, latency = chat(hyp.strip(), session_id)
                        agent_ms = round((time.time() - t1) * 1000)
                        llm_ms   = latency.get("llm_total_ms", 0)
                        tool_ms  = latency.get("tool_total_ms", 0)
                        actual_action = extract_action(response)
                        actual_voice  = extract_voice(response)
                        vsim = voice_similarity(script_id, actual_voice, expected_embs)
                        break
                    except _openai.RateLimitError as e:
                        _m = re.search(r"try again in (\d+(?:\.\d+)?)(ms|s)", str(e))
                        _wait = (float(_m.group(1)) / 1000 if _m and _m.group(2) == "ms"
                                 else float(_m.group(1)) if _m else 60.0) + 1.0
                        print(f"  [429] {_wait:.1f}s 대기 후 재시도 ({_attempt}/5)")
                        time.sleep(_wait)
                    except Exception as e:
                        print(f"  [AGENT ERROR] {rec['path'].name}: {e}")
                        break

            # 독립 세션은 사용 후 정리
            if group is None:
                clear_history(session_id)

            type_ok = action_type_ok(script_id, actual_action) if hyp.strip() else None
            full_ok = action_full_ok(script_id, actual_action) if hyp.strip() else None
            mark = "✓" if full_ok is True else ("△" if type_ok is True else ("✗" if type_ok is False else "-"))

            row = {
                "speaker": speaker, "env": env, "id": script_id,
                "category": SCRIPT_CATEGORY.get(script_id, ""),
                "session_group": group or "independent",
                "ref": ref, "hyp": hyp,
                "cer": round(cer(ref, hyp), 4),
                "stt_ms": stt_ms,
                "expected_action": EXPECTED_ACTIONS.get(script_id, ""),
                "actual_action": actual_action,
                "action_type_ok": type_ok,
                "action_full_ok": full_ok,
                "expected_voice": EXPECTED_VOICE.get(script_id, ""),
                "actual_voice": actual_voice,
                "voice_sim": vsim,
                "agent_ms": agent_ms,
                "llm_ms": llm_ms,
                "tool_ms": tool_ms,
                "total_ms": stt_ms + agent_ms,
                "response_head": response[:200],
            }
            results.append(row)
            done += 1
            print(
                f"[{done:3}/{total}] {rec['path'].name}"
                f"  CER={row['cer']:.2%}  STT={stt_ms}ms"
                f"  Agent={agent_ms}ms  {mark}"
                f"  ({actual_action})"
            )

        # 연속 세션 정리
        for sid in active_sessions.values():
            clear_history(sid)

    return results


# ─── 요약 출력 ────────────────────────────────────────────────────────────
def summarize(results: list[dict], measure_agent: bool):
    def avg(vals):
        v = [x for x in vals if x is not None]
        return sum(v) / len(v) if v else 0.0

    print("\n" + "=" * 64)
    print("■ 전체 요약")
    print(f"  파일 수   : {len(results)}")
    print(f"  평균 CER  : {avg(r['cer'] for r in results):.2%}")
    print(f"  평균 STT  : {avg(r['stt_ms'] for r in results):.0f}ms")

    if measure_agent:
        scored = [r for r in results if r.get("action_type_ok") is not None]
        if scored:
            t_ok = sum(1 for r in scored if r["action_type_ok"])
            f_ok = sum(1 for r in scored if r["action_full_ok"])
            print(f"  Action 정확도 (관대): {t_ok}/{len(scored)}  ({t_ok/len(scored):.1%})  — 타입만 일치")
            print(f"  Action 정확도 (엄격): {f_ok}/{len(scored)}  ({f_ok/len(scored):.1%})  — 타입+ID 일치")
        vsim_vals = [r["voice_sim"] for r in results if r.get("voice_sim") is not None]
        if vsim_vals:
            print(f"  응답 유사도 (평균)  : {sum(vsim_vals)/len(vsim_vals):.4f}  — 코사인 유사도 0~1")
        print(f"  평균 Agent : {avg(r['agent_ms'] for r in results):.0f}ms")
        print(f"  평균 Total : {avg(r['total_ms'] for r in results):.0f}ms")

    for dim, key in [("화자", "speaker"), ("환경", "env"), ("카테고리", "category")]:
        print(f"\n■ {dim}별")
        groups: dict[str, list] = {}
        for r in results:
            groups.setdefault(r[key], []).append(r)
        for grp, items in sorted(groups.items()):
            line = (
                f"  {grp:14}"
                f"  CER={avg(r['cer'] for r in items):.2%}"
                f"  STT={avg(r['stt_ms'] for r in items):.0f}ms"
            )
            if measure_agent:
                sc = [r for r in items if r.get("action_type_ok") is not None]
                if sc:
                    t_ok = sum(1 for r in sc if r["action_type_ok"])
                    f_ok = sum(1 for r in sc if r["action_full_ok"])
                    vs = [r["voice_sim"] for r in items if r.get("voice_sim") is not None]
                    vsim_str = f"  유사도={sum(vs)/len(vs):.3f}" if vs else ""
                    line += f"  관대={t_ok/len(sc):.1%}  엄격={f_ok/len(sc):.1%}{vsim_str}  Agent={avg(r['agent_ms'] for r in items):.0f}ms"
            print(line)


# ─── CSV 저장 ─────────────────────────────────────────────────────────────
def save_csv(results: list[dict], out_path: Path):
    if not results:
        return
    rows = [{k: v for k, v in r.items() if k != "path"} for r in results]
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[저장] {out_path}")


# ─── 메인 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="배치 평가 스크립트")
    parser.add_argument("--audio-dir", default="tests/recordings", help="m4a 파일 디렉터리 (기본: tests/recordings)")
    parser.add_argument(
        "--phase",
        choices=["stt", "pipeline", "all"],
        default="stt",
        help="stt=STT 정확도만  pipeline=STT+Agent  all=둘 다",
    )
    parser.add_argument("--model-size", default="small", help="Whisper 모델 크기")
    parser.add_argument("--out-dir",    default="tests/results", help="결과 저장 경로")
    parser.add_argument("--speaker",    help="특정 화자만 (sh/sb/br/hn)")
    parser.add_argument("--env",        help="특정 환경만 (quiet/noisy)")
    parser.add_argument("--limit",       type=int,   help="최대 파일 수 (디버깅용)")
    parser.add_argument("--agent-delay", type=float, default=10.0,
                        help="Agent 호출 사이 대기 시간(초) — TPM 한도 초과 방지 (기본 10.0)")
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    if not audio_dir.exists():
        print(f"[ERROR] 디렉터리 없음: {audio_dir}")
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    recordings = []
    for p in audio_dir.glob("*.m4a"):
        rec = parse_filename(p)
        if rec is None:
            print(f"[SKIP] 파일명 불일치: {p.name}")
            continue
        if args.speaker and rec["speaker"] != args.speaker:
            continue
        if args.env and rec["env"] != args.env:
            continue
        recordings.append(rec)

    # 화자 → 환경 → id 숫자 순 정렬 (br_1, br_2, ..., br_10 순)
    recordings.sort(key=lambda r: (r["speaker"], r["env"], r["id"]))

    if args.limit:
        recordings = recordings[: args.limit]

    print(f"대상 파일: {len(recordings)}개  (model={args.model_size})\n")
    if not recordings:
        print("[ERROR] 처리할 파일 없음")
        sys.exit(1)

    from voice.stt import load_model
    model = load_model(model_size=args.model_size)

    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.phase in ("stt", "all"):
        print("\n─── Phase 1: STT 정확도 ───")
        stt_results = run_stt_phase(recordings, model)
        summarize(stt_results, measure_agent=False)
        save_csv(stt_results, out_dir / f"stt_{ts}.csv")

    if args.phase in ("pipeline", "all"):
        print("\n─── Phase 2+3: 파이프라인 (STT + Agent) ───")
        pipe_results = run_pipeline_phase(recordings, model, agent_delay=args.agent_delay)
        summarize(pipe_results, measure_agent=True)
        save_csv(pipe_results, out_dir / f"pipeline_{ts}.csv")


if __name__ == "__main__":
    main()
