#/app/tools/menu_tools.py
import sqlite3
from langchain.tools import tool
from app.rag.chroma import get_chroma_db

DB_PATH = "data/ria_menu.db"


_SYNONYMS: dict[str, list[str]] = {
    "소고기": ["쇠고기", "한우"],
    "쇠고기": ["소고기", "한우"],
    "한우":   ["소고기", "쇠고기"],
    "돼지고기": ["포크", "삼겹", "베이컨"],
    "닭고기": ["치킨", "닭"],
    "치킨":   ["닭고기", "닭"],
    "새우":   ["쉬림프"],
    "계란":   ["달걀", "에그"],
    "달걀":   ["계란", "에그"],
}

def _expand_exclude(items: list[str]) -> list[str]:
    expanded = list(items)
    for item in items:
        for syn in _SYNONYMS.get(item, []):
            if syn not in expanded:
                expanded.append(syn)
    return expanded


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
    """버거를 장바구니에 담은 직후 세트 여부를 확인하고 음료/사이드 옵션을 반환한다.
    세트 가격 단순 조회는 get_menu_info를 사용하라.
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
def get_menu_by_nutrition(sort_by: str, order: str = "asc", category: str = None, limit: int = 3) -> str:
    """영양소 기준으로 메뉴를 정렬해 조회한다.
    영양소 수치로 순위를 매길 때 사용하라. search_menu의 필터와 달리 정렬이 필요할 때 사용하라.

    sort_by: 정렬 기준 영양소. calories=칼로리, sugar=당류, protein=단백질.
    order: asc=낮은순, desc=높은순.
    category: 버거/디저트/치킨/음료/아이스샷 중 하나. 전체 메뉴면 None.
    limit: 반환할 메뉴 수 (기본 3개).
    예) "칼로리 낮은 메뉴" → sort_by="calories", order="asc"
        "제일 당 낮은 아이스크림" → sort_by="sugar", order="asc", category="아이스샷"
        "단백질 높은 버거" → sort_by="protein", order="desc", category="버거"
        "당뇨에 좋은/혈당 관리/저당 버거" → sort_by="sugar", order="asc", category="버거"
        "다이어트/칼로리 걱정/살찔까봐" → sort_by="calories", order="asc"
        "고단백/운동 후/헬스 식단" → sort_by="protein", order="desc"
    """
    import json as _json

    KEY_MAP = {"calories": "열량", "sugar": "당류", "protein": "단백질"}
    prefix = KEY_MAP.get(sort_by)
    if not prefix:
        return f"sort_by는 calories / sugar / protein 중 하나여야 합니다."

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if category:
        cur.execute("SELECT name, price, description, nutrition FROM menu WHERE category = ?", (category,))
    else:
        cur.execute("SELECT name, price, description, nutrition FROM menu")
    rows = cur.fetchall()
    conn.close()

    def parse_value(nutrition_str):
        if not nutrition_str:
            return -1
        d = _json.loads(nutrition_str)
        for k, v in d.items():
            if k.startswith(prefix):
                import re as _re
                m = _re.search(r'\d+', str(v).replace(",", ""))
                return int(m.group()) if m else -1
        return -1

    scored = [(name, price, desc, parse_value(nut)) for name, price, desc, nut in rows]
    # 데이터 없는 항목(-1) 제외
    scored = [(n, p, d, v) for n, p, d, v in scored if v >= 0]

    if not scored:
        return "해당 조건에 맞는 영양 정보가 없습니다."

    scored.sort(key=lambda x: x[3], reverse=(order == "desc"))

    unit = {"calories": "kcal", "sugar": "g", "protein": "g"}.get(sort_by, "")
    lines = [
        f"메뉴명: {n}, 가격: {p}원, {sort_by}: {v}{unit}, 설명: {d}"
        for n, p, d, v in scored[:limit]
    ]
    return "\n".join(lines)


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
        conditions.append("category = ?")
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

        # 2.5차: 뒤 토큰부터 제거하며 AND 재시도 (3개 이상일 때)
        if not rows and len(tokens) > 2:
            for skip_idx in range(len(tokens) - 1, -1, -1):
                subset = [t for i, t in enumerate(tokens) if i != skip_idx]
                and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in subset])
                cur.execute(
                    f"SELECT name, price, description, allergy, origin, nutrition FROM menu WHERE {and_conditions}",
                    [f"%{t}%" for t in subset]
                )
                rows = cur.fetchall()
                if rows:
                    break

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

    if not rows:
        conn.close()
        return f"'{name}' 메뉴를 찾을 수 없습니다."

    result_lines = []
    for n, p, d, a, o, nu in rows:
        line = f"메뉴명: {n}, 가격: {p}원, 설명: {d}, 알레르기: {a}, 원산지: {o}, 영양정보: {nu}"
        cur.execute(
            "SELECT s.set_price FROM set_menus s JOIN menu m ON s.burger_menu_id = m.id WHERE m.name = ?",
            (n,)
        )
        set_row = cur.fetchone()
        if set_row:
            line += f", 세트가격: {set_row[0]:,}원"
        result_lines.append(line)

    conn.close()
    return "\n".join(result_lines)


def search_menu_logic(query: str = "", category: str = None, badge: str = None, exclude: list = [], offset: int = 0, exclude_names: list = [], max_spicy: int = None, min_spicy: int = None):
    exclude = _expand_exclude(exclude) if exclude else []

    def build_spicy_clause():
        clauses, params = [], []
        if max_spicy is not None:
            clauses.append("spicy_level <= ?"); params.append(max_spicy)
        if min_spicy is not None:
            clauses.append("spicy_level >= ?"); params.append(min_spicy)
        return ("AND " + " AND ".join(clauses)) if clauses else "", params

    def format_row(name, price, description, allergy):
        return f"메뉴명: {name}\n        가격: {price}원\n        설명: {description}\n        알레르기: {allergy}"

    def allergy_ok(allergy, content=""):
        if not exclude:
            return True
        return not any(item in (allergy or "") or item in content for item in exclude)

    # exclude 재료가 query에 포함되면 SQL 경로로 강제 전환 (query와 exclude 충돌 방지)
    if exclude and query:
        if any(item in query for item in exclude):
            query = ""

    # SQL 경로: query 없이 category/badge/exclude 조합
    if not query:
        conn = sqlite3.connect(DB_PATH)
        conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
        cur = conn.cursor()

        spicy_clause, spicy_params = build_spicy_clause()
        conditions, params = [], []

        if category:
            conditions.append("category = ?"); params.append(category)
        if badge:
            conditions.append("badge LIKE ?"); params.append(f"%{badge}%")
        if exclude_names:
            for n in exclude_names:
                conditions.append("REPLACE_SPACE(name) NOT LIKE ?")
                params.append(f"%{n.replace(' ', '')}%")
        if exclude:
            for item in exclude:
                conditions.append("(allergy NOT LIKE ? AND description NOT LIKE ?)")
                params.extend([f"%{item}%", f"%{item}%"])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else "WHERE 1=1"
        limit = 3 if (category or badge) and not exclude else 20
        badge_order = "CASE WHEN badge LIKE '%BEST%' THEN 0 WHEN badge LIKE '%NEW%' THEN 1 ELSE 2 END ASC"
        cur.execute(
            f"SELECT name, price, description, allergy FROM menu {where} {spicy_clause} ORDER BY {badge_order} LIMIT ? OFFSET ?",
            params + spicy_params + [limit, offset]
        )
        rows = cur.fetchall()
        conn.close()

        results = [(format_row(*r), 0.0) for r in rows]
        return results[:3]

    # 벡터 검색 경로: query 있을 때
    # spicy_level은 NULL이 많아 ChromaDB where 필터가 문서를 통째로 제외함 → 후처리로 필터링
    chroma_filters = []
    if category:
        chroma_filters.append({"category": {"$eq": category}})
    filters = chroma_filters[0] if chroma_filters else None

    spicy_active = max_spicy is not None or min_spicy is not None
    exclude_active = bool(exclude)
    k = 10 if (spicy_active or exclude_active) else 5

    results = get_chroma_db().similarity_search_with_score(query, k=k + offset, filter=filters)

    def spicy_ok(doc):
        level = doc.metadata.get("spicy_level")
        if max_spicy is not None and (level is None or level > max_spicy):
            return False
        if min_spicy is not None and (level is None or level < min_spicy):
            return False
        return True

    def badge_ok(doc):
        return not badge or badge in doc.metadata.get("badge", "")

    use_threshold = not category and not badge and not spicy_active and not exclude_active
    merged = [
        (doc, score) for doc, score in results
        if (not use_threshold or score < 0.7)
        and allergy_ok(doc.metadata.get("allergy", ""), doc.page_content)
        and spicy_ok(doc)
        and badge_ok(doc)
    ]
    return [(doc.page_content, round(score, 4)) for doc, score in merged[offset:offset + 3]]


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
    - exclude: 제외할 재료 목록. 알레르기뿐 아니라 "~없는/~안 들어간/~빼고" 같은 재료 제외 요청에도 사용하라.
      예) "새우 알레르기 있어요" → ["새우"] / "마요네즈 없는 버거" → exclude=["마요네즈"], query=""
    - exclude_names: 제외할 메뉴명 목록. query에 "제외/말고" 넣지 말고 이 파라미터 사용.
    - offset: 이미 보여준 메뉴 수. "다른 거/더 있어?" → 직전 offset+3.
    - max_spicy / min_spicy: 매운맛 범위 필터. spicy_level 기준(0=안매움, 1=약간, 2=보통, 3=매움, 10=극매움).
      "안 매운 거/순한 거/덜 매운 거" → max_spicy=0
      "약간 매운 거/조금 매운 거" → min_spicy=1, max_spicy=1
      "보통 매운 거" → min_spicy=2, max_spicy=2
      "매운 거 추천" → min_spicy=2
      "아주 매운 거/극매운" → min_spicy=3
      언급 없으면 둘 다 None.
    영양소 기준 검색(칼로리/당류/단백질)은 get_menu_by_nutrition을 사용하라.
    """
    results = search_menu_logic(query, category, badge, exclude, offset, exclude_names, max_spicy, min_spicy)

    if not results:
        return "검색 결과가 없습니다."

    return "\n".join([content for content, score in results]) # llm한테 문자열 반환.

    