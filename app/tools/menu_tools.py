#/app/tools/menu_tools.py
import sqlite3
from langchain.tools import tool
from app.rag.chroma import get_chroma_db

DB_PATH = "data/ria_menu.db"


def _build_search_terms(normalized: str, clean_name: str) -> list[str]:
    tokens = [t for t in clean_name.split() if t] or [normalized]
    terms = []
    for tok in tokens:
        terms.append(tok)
        for trim in range(1, len(tok)):
            prefix = tok[:-trim]
            if len(prefix) >= 2:
                terms.append(prefix)
    seen = set()
    return [t for t in terms if not (t in seen or seen.add(t))]


@tool
def get_set_info(burger_name: str) -> str:
    """버거의 세트 메뉴 정보와 선택 가능한 음료/사이드 옵션을 반환한다.
    버거를 장바구니에 담은 직후 세트 여부를 확인할 때 사용하라.
    예) add_to_cart로 버거를 담은 후 → get_set_info 호출 → 세트 안내
    """
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    clean_name = burger_name.strip()
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    # 1차: 완전 일치
    cur.execute(
        "SELECT id, name, price FROM menu WHERE REPLACE_SPACE(name) = ?",
        (normalized,)
    )
    burger = cur.fetchone()

    if not burger:
        rows = []

        # 2차: AND 검색 + 가장 긴 토큰 병합
        if len(tokens) > 1:
            and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in tokens])
            cur.execute(
                f"SELECT id, name, price FROM menu WHERE {and_conditions}",
                [f"%{t}%" for t in tokens]
            )
            rows = cur.fetchall()

            # AND 결과가 있을 때만 가장 긴 토큰으로 추가 검색해서 병합
            if rows:
                longest_token = max(tokens, key=len)
                cur.execute(
                    "SELECT id, name, price FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
                    (f"%{longest_token}%",)
                )
                existing_ids = {r[0] for r in rows}
                for row in cur.fetchall():
                    if row[0] not in existing_ids:
                        rows.append(row)
                        existing_ids.add(row[0])

        # 3차: 접두어 단계별 수집
        if not rows:
            terms = _build_search_terms(normalized, clean_name)
            collected = {}
            half = max(2, len(normalized) // 2)
            for term in terms:
                cur.execute(
                    "SELECT id, name, price FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
                    (f"%{term}%",)
                )
                for row in cur.fetchall():
                    if row[0] not in collected:
                        collected[row[0]] = row
                if collected and len(term) <= half:
                    break
            rows = list(collected.values())

        burger = rows[0] if rows else None

    if not burger:
        conn.close()
        return "세트 메뉴 정보를 찾을 수 없습니다."

    burger_id, burger_name_actual, burger_price = burger

    cur.execute(
        "SELECT set_id, set_price FROM set_menus WHERE burger_menu_id = ?",
        (burger_id,)
    )
    set_menu = cur.fetchone()

    if not set_menu:
        conn.close()
        return f"{burger_name_actual}은(는) 세트 메뉴가 없습니다."

    _, set_price = set_menu

    cur.execute("""
        SELECT m.name, o.extra_price FROM options o
        JOIN menu m ON o.menu_id = m.id
        WHERE o.option_type = '드링크'
    """)
    drinks = [f"{name}({'+' + str(ep) + '원' if ep else '기본'})" for name, ep in cur.fetchall()]

    cur.execute("""
        SELECT m.name, o.extra_price FROM options o
        JOIN menu m ON o.menu_id = m.id
        WHERE o.option_type = '사이드'
    """)
    sides = [f"{name}({'+' + str(ep) + '원' if ep else '기본'})" for name, ep in cur.fetchall()]

    conn.close()

    return (
        f"{burger_name_actual} 세트: {set_price:,}원 (단품 {burger_price:,}원, +{set_price - burger_price:,}원)\n"
        f"음료 선택: {', '.join(drinks)}\n"
        f"사이드 선택: {', '.join(sides)}"
    )


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

    conditions = []
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

    clean_name = name.strip()
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    # 1차: 완전 일치
    cur.execute(
        "SELECT name, price, description, allergy, origin, nutrition FROM menu WHERE REPLACE_SPACE(name) = ?",
        (normalized,)
    )
    rows = cur.fetchall()

    if not rows:
        # 2차: AND 검색 + 가장 긴 토큰 병합
        if len(tokens) > 1:
            and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in tokens])
            cur.execute(
                f"SELECT name, price, description, allergy, origin, nutrition FROM menu WHERE {and_conditions}",
                [f"%{t}%" for t in tokens]
            )
            rows = cur.fetchall()

            # AND 결과가 있을 때만 가장 긴 토큰으로 추가 검색해서 병합
            if rows:
                longest_token = max(tokens, key=len)
                cur.execute(
                    "SELECT name, price, description, allergy, origin, nutrition FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
                    (f"%{longest_token}%",)
                )
                existing_ids = {r[0] for r in rows}
                for row in cur.fetchall():
                    if row[0] not in existing_ids:
                        rows.append(row)
                        existing_ids.add(row[0])

        # 3차: 접두어 단계별 수집
        if not rows:
            terms = _build_search_terms(normalized, clean_name)
            collected = {}
            half = max(2, len(normalized) // 2)
            for term in terms:
                cur.execute(
                    "SELECT name, price, description, allergy, origin, nutrition FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
                    (f"%{term}%",)
                )
                for row in cur.fetchall():
                    if row[0] not in collected:
                        collected[row[0]] = row
                if collected and len(term) <= half:
                    break
            rows = list(collected.values())

    conn.close()

    if not rows:
        return f"'{name}' 메뉴를 찾을 수 없습니다."

    return "\n".join([
        f"메뉴명: {n}, 가격: {p}원, 설명: {d}, 알레르기: {a}, 원산지: {o}, 영양정보: {nu}"
        for n, p, d, a, o, nu in rows
    ])


def search_menu_logic(query: str="", category: str = None, badge: str = None, exclude: list = [], offset: int = 0, exclude_names: list = [], max_spicy: int = None, min_spicy: int = None):

    # 쿼리·카테고리·배지 없이 exclude만 있으면 SQL로 전체 메뉴 조회 후 알레르기 필터
    if not query and not category and not badge and exclude:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        spicy_clauses = []
        spicy_params = []
        if max_spicy is not None:
            spicy_clauses.append("spicy_level <= ?")
            spicy_params.append(max_spicy)
        if min_spicy is not None:
            spicy_clauses.append("spicy_level >= ?")
            spicy_params.append(min_spicy)
        spicy_clause = ("AND " + " AND ".join(spicy_clauses)) if spicy_clauses else ""
        cur.execute(
            f"SELECT name, price, description, allergy FROM menu WHERE 1=1 {spicy_clause} LIMIT 20 OFFSET ?",
            spicy_params + [offset]
        )
        rows = cur.fetchall()
        conn.close()

        results = []
        for name, price, description, allergy in rows:
            if any(item in (allergy or "") for item in exclude):
                continue
            if exclude_names and any(en in name for en in exclude_names):
                continue
            content = f"메뉴명: {name}\n        가격: {price}원\n        설명: {description}\n        알레르기: {allergy}"
            results.append((content, 0.0))
        return results[:3]

    # 카테고리 또는 배지만 지정된 경우 SQL로 페이지네이션 조회
    if (category or badge) and not query:
        conn = sqlite3.connect(DB_PATH)
        conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
        cur = conn.cursor()

        spicy_clauses = []
        spicy_params = []
        if max_spicy is not None:
            spicy_clauses.append("spicy_level <= ?")
            spicy_params.append(max_spicy)
        if min_spicy is not None:
            spicy_clauses.append("spicy_level >= ?")
            spicy_params.append(min_spicy)
        spicy_clause = ("AND " + " AND ".join(spicy_clauses)) if spicy_clauses else ""

        base_conditions = []
        base_params = []
        if category:
            base_conditions.append("category = ?")
            base_params.append(category)
        if badge:
            base_conditions.append("badge LIKE ?")
            base_params.append(f"%{badge}%")
        base_clause = " AND ".join(base_conditions)

        if exclude_names:
            excl_conditions = " AND ".join(["REPLACE_SPACE(name) NOT LIKE ?" for _ in exclude_names])
            excl_params = [f"%{n.replace(' ', '')}%" for n in exclude_names]
            cur.execute(
                f"SELECT name, price, description, allergy FROM menu WHERE {base_clause} AND {excl_conditions} {spicy_clause} LIMIT 3 OFFSET ?",
                base_params + excl_params + spicy_params + [offset]
            )
        else:
            cur.execute(
                f"SELECT name, price, description, allergy FROM menu WHERE {base_clause} {spicy_clause} LIMIT 3 OFFSET ?",
                base_params + spicy_params + [offset]
            )
        rows = cur.fetchall()
        conn.close()

        results = []
        for name, price, description, allergy in rows:
            if exclude and any(item in (allergy or "") for item in exclude):
                continue
            content = f"메뉴명: {name}\n        가격: {price}원\n        설명: {description}\n        알레르기: {allergy}"
            results.append((content, 0.0))
        return results

    # 그 외: 벡터 검색
    # spicy_level은 NULL이 많아 ChromaDB 필터가 해당 문서를 통째로 제외함 → 후처리로 대신 필터링
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

    # spicy 필터가 있으면 더 많이 가져와서 후처리
    k = 15 if (max_spicy is not None or min_spicy is not None) else 5

    db = get_chroma_db()
    results = db.similarity_search_with_score(
        query,
        k=k,
        filter=filters,
    )

    def is_excluded(doc):
        allergy = doc.metadata.get("allergy", "")
        return any(item in allergy for item in exclude)

    def spicy_ok(doc):
        level = doc.metadata.get("spicy_level")
        if max_spicy is not None and (level is None or level > max_spicy):
            return False
        if min_spicy is not None and (level is None or level < min_spicy):
            return False
        return True

    # spicy 필터가 활성화되면 threshold를 완화 (유사도보다 spicy 조건이 우선)
    spicy_active = max_spicy is not None or min_spicy is not None
    use_threshold = (category is None and badge is None) and not spicy_active
    merged = [
        (doc, score) for doc, score in results
        if (not use_threshold or score < 0.7) and not is_excluded(doc) and spicy_ok(doc)
    ]

    return [(doc.page_content, round(score, 4)) for doc, score in merged[:3]]


@tool
def search_menu(query: str = "", category: str = None, badge: str = None, exclude: list = [], offset: int = 0, exclude_names: list = [], max_spicy: int = None, min_spicy: int = None) -> str:
    """사용자 요청에 맞는 메뉴를 검색한다. 메뉴 추천 또는 어떤 메뉴가 있는지 물어볼 때만 사용하라.

    - query: 재료, 맛, 특징 등 검색 의도 전체. 유사어도 포함.
      예) "초코 디저트" → "초코 초콜릿 디저트" / "새우 버거" → "새우 버거"
    - category: 음식 종류 명확히 언급 시만. 버거/디저트/치킨/음료/아이스샷. 불명확하면 None.
      예) "햄버거/버거" → "버거" / "콜라/음료/커피" → "음료" / "아이스크림/소프트콘" → "아이스샷"
          "치킨/윙/순살" → "치킨" / "감자/너겟/치즈스틱" → "디저트"
          "오징어/새우" 등 재료만, "매콤한거" 등 맛만 언급 → None
    - badge: 손님이 아래 키워드를 언급할 때 해당 값으로 설정. 언급 없으면 None.
      NEW=신메뉴/새로나온, BEST=베스트/대표메뉴/인기, 비건=비건/채식,
      추천=추천, 재주문1위=재주문1위/또먹고싶은, 카페인=카페인없는/디카페인
    - exclude: 제외할 알레르기 재료 목록.
    - exclude_names: 제외할 메뉴명 목록. query에 "제외/말고" 넣지 말고 이 파라미터 사용.
    - offset: 이미 보여준 메뉴 수. "다른 거/더 있어?" → 직전 offset+3.
    - max_spicy / min_spicy: 매운맛 범위 필터. spicy_level 기준(0=안매움, 1=약간, 2=보통, 3=매움, 10=극매움).
      "안 매운 거/순한 거/덜 매운 거" → max_spicy=0
      "약간 매운 거/조금 매운 거" → min_spicy=1, max_spicy=1
      "보통 매운 거" → min_spicy=2, max_spicy=2
      "매운 거 추천" → min_spicy=2
      "아주 매운 거/극매운" → min_spicy=3
      언급 없으면 둘 다 None.
    """
    results = search_menu_logic(query, category, badge, exclude, offset, exclude_names, max_spicy, min_spicy)

    if not results:
        return "검색 결과가 없습니다."

    return "\n".join([content for content, score in results]) # llm한테 문자열 반환.
