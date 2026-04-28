#/app/tools/menu_tools.py
import sqlite3
from langchain.tools import tool
from app.rag.chroma import get_chroma_db

DB_PATH = "data/ria_menu.db"


@tool
def get_menu_by_price(category: str = None, order: str = "asc", limit: int = 5, max_price: int = None, min_price: int = None) -> str:
    """가격 기준으로 메뉴를 조회한다. 가장 비싸거나 저렴한 메뉴, 또는 예산 내 메뉴를 찾을 때 사용하라.

    category: 버거/디저트/치킨/음료/아이스샷 중 하나. 전체 메뉴면 None.
    order: desc=비싼순, asc=저렴한순.
    limit: 반환할 메뉴 수 (기본 5개).
    max_price: 이 금액 이하인 메뉴만 조회. 예산 제한이 있을 때 사용.
    min_price: 이 금액 이상인 메뉴만 조회.
    예) "가장 비싼 버거" → category="버거", order="desc", limit=1
        "저렴한 음료 3개" → category="음료", order="asc", limit=3
        "8000원 이하 메뉴 추천" → max_price=8000, order="desc", limit=5
        "5000원~8000원 버거" → category="버거", min_price=5000, max_price=8000
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    price_expr = "CAST(REPLACE(price, ',', '') AS INTEGER)"
    order_sql = "DESC" if order == "desc" else "ASC"

    conditions = ["category != '토핑'"]
    params = []

    if category:
        conditions[0] = "category = ?"
        params.append(category)
    if max_price is not None:
        conditions.append(f"{price_expr} <= ?")
        params.append(max_price)
    if min_price is not None:
        conditions.append(f"{price_expr} >= ?")
        params.append(min_price)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    cur.execute(
        f"SELECT name, price FROM menu {where_clause} ORDER BY {price_expr} {order_sql} LIMIT ?",
        params
    )

    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "해당 조건에 맞는 메뉴를 찾을 수 없습니다."

    return "\n".join([f"메뉴명: {name}, 가격: {price}" for name, price in rows])


@tool
def get_menu_info(name: str) -> str:
    """특정 메뉴의 가격, 설명 등 정보를 조회한다.
    손님이 특정 메뉴 이름을 언급하며 가격이나 정보를 물어볼 때 사용하라.
    예) "치즈스틱 얼마야" → name="치즈스틱"
        "불고기버거 설명해줘" → name="불고기버거"
    """
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    normalized = name.replace(" ", "")
    cur.execute(
        "SELECT name, price, description, allergy FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
        (f"%{normalized}%",)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return f"'{name}' 메뉴를 찾을 수 없습니다."

    return "\n".join([
        f"메뉴명: {n}, 가격: {p}원, 설명: {d}, 알레르기: {a}"
        for n, p, d, a in rows
    ])


def search_menu_logic(query: str="", category: str = None, badge: str = None, exclude: list = [], offset: int = 0, exclude_names: list = []):

    # 카테고리만 지정된 경우 SQL로 페이지네이션 조회
    if category and not query and not badge:
        conn = sqlite3.connect(DB_PATH)
        conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
        cur = conn.cursor()

        if exclude_names:
            # 제외할 메뉴명을 정규화해서 NOT LIKE 조건으로 필터
            excl_conditions = " AND ".join(["REPLACE_SPACE(name) NOT LIKE ?" for _ in exclude_names])
            excl_params = [f"%{n.replace(' ', '')}%" for n in exclude_names]
            cur.execute(
                f"SELECT name, price, description, allergy FROM menu WHERE category = ? AND category != '토핑' AND {excl_conditions} LIMIT 3 OFFSET ?",
                [category] + excl_params + [offset]
            )
        else:
            cur.execute(
                "SELECT name, price, description, allergy FROM menu WHERE category = ? AND category != '토핑' LIMIT 3 OFFSET ?",
                (category, offset)
            )
        rows = cur.fetchall()
        conn.close()

        results = []
        for name, price, description, allergy in rows:
            if exclude and any(item in (allergy or "") for item in exclude):
                continue
            content = f"메뉴명: {name}\n        카테고리: {category}\n        가격: {price}원\n        설명: {description}\n        알레르기: {allergy}"
            results.append((content, 0.0))
        return results

    # 그 외: 벡터 검색
    conditions = []
    if category:
        conditions.append({"category": {"$eq": category}})
    if badge:
        conditions.append({"badge": {"$eq": badge}})

    if len(conditions) > 1:
        filters = {"$and": conditions}
    elif len(conditions) == 1:
        filters = conditions[0]
    else:
        filters = None

    db = get_chroma_db()
    results = db.similarity_search_with_score(
        query,
        k=5,
        filter=filters,
    )

    def is_excluded(doc):
        allergy = doc.metadata.get("allergy", "")
        return any(item in allergy for item in exclude)

    use_threshold = (category is None and badge is None)
    merged = [
        (doc, score) for doc, score in results
        if (not use_threshold or score < 0.7) and not is_excluded(doc)
    ]

    return [(doc.page_content, round(score, 4)) for doc, score in merged[:3]]


@tool
def search_menu(query: str = "", category: str = None, badge: str = None, exclude: list = [], offset: int = 0, exclude_names: list = []) -> str:
    """사용자 요청에 맞는 메뉴를 검색한다.

    사용자 발화에서 아래 파라미터를 추출하여 각각 정확히 채워라.

    - query: 재료, 맛, 특징 등 검색 의도 전체를 담아라. 유사어도 포함할 것.
      예) "초코 디저트" → "초코 초콜릿 디저트" / "새우 버거" → "새우 버거"
    - category: 손님이 음식 종류를 명확히 언급할 때만 추출. 버거/디저트/치킨/음료/아이스샷 중 하나.
      명확하지 않으면 반드시 None으로 둘 것. 추측해서 넣지 말 것.
      예) "햄버거", "버거" → "버거"
          "콜라", "음료", "커피", "주스" → "음료"
          "아이스크림", "소프트아이스크림", "소프트콘" → "아이스샷"
          "치킨", "윙", "순살" → "치킨"
          "감자", "너겟", "치즈스틱", "디저트" → "디저트"
          "오징어", "새우" 등 특정 재료만 언급 → None
          "매콤한거", "달콤한거", "든든한거" 등 맛/느낌만 언급 → None
    - badge: 신메뉴/베스트 언급 시 추출. NEW=신메뉴, BEST=베스트.
      예) "신메뉴", "새로 나온" → "NEW" / "인기", "베스트" → "BEST"
    - exclude: 제외할 알레르기 재료 목록.
      예) "고기 빼고" → ["쇠고기"] / "유제품 알러지" → ["우유", "치즈"]
    - exclude_names: 결과에서 제외할 메뉴명 목록. 손님이 특정 메뉴를 제외하고 다른 것을 원할 때 사용.
      query에 "제외", "말고" 등을 넣지 말고 이 파라미터를 사용하라.
      예) "콜라 말고 다른 음료" → exclude_names=["콜라"] / "콜라 사이다 빼고" → exclude_names=["콜라", "사이다"]
    - offset: 이미 보여준 메뉴 수. 손님이 "다른 거", "더 있어?" 등 추가 목록을 요청하면
      직전 search_menu 호출의 offset + 3으로 설정하라.
      예) 처음 조회 → offset=0 / "다른 거 있어?" → offset=3 / 또 더 → offset=6
    """
    results = search_menu_logic(query, category, badge, exclude, offset, exclude_names)

    if not results:
        return "검색 결과가 없습니다."

    return "\n".join([content for content, score in results]) # llm한테 문자열 반환.
