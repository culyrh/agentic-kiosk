#/app/tools/cart_tools.py
import re
import sqlite3
from langchain.tools import tool
from app.session_context import current_session_id

DB_PATH = "data/ria_menu.db"



def _build_search_terms(normalized: str, clean_name: str) -> list[str]:
    
    # 공백 기준 토큰 분리 + 접두어 분해로 검색어 목록을 생성한다.
    # 공백 있는 입력 -> 토큰 분리로 해결
    # 공백 없는 입력 -> 접두어 분해로 해결

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


def _cart_label(name, is_set):
    # 같은 메뉴가 단품/세트 두 행으로 존재할 수 있으므로 항상 구분해서 표기한다.
    return f"{name} {'세트' if is_set else '단품'}"


def _parse_set_qualifier(item_name: str):

    # 손님이 말한 "세트"/"단품" 한정어를 분리한다.
    # 반환: (한정어를 제거한 메뉴명, is_set 필터 또는 None)

    set_filter = None
    if "세트" in item_name:
        set_filter = 1
    elif "단품" in item_name:
        set_filter = 0

    clean = re.sub(r'\[.*?\]', '', item_name)
    clean = re.sub(r'\s*(세트|단품)\s*', ' ', clean).strip()
    return clean, set_filter


def _match_cart_item(cur, session_id: str, item_name: str):

    # 장바구니에서 메뉴를 찾는다. remove_from_cart / update_cart_quantity 공용.
    # 반환: (rows, match_stage)
    #   rows        : [(cart_id, name, is_set), ...]  <- menu_id가 아니라 cart_id 기준
    #   match_stage : "exact" | "token" | "prefix_full" | "prefix" | None
    #                 "prefix"(잘라낸 접두어로만 걸린 경우)만 신뢰도가 낮아 확인이 필요하다.

    clean_name, set_filter = _parse_set_qualifier(item_name)
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    base = """SELECT c.cart_id, m.name, c.is_set FROM cart c
              JOIN menu m ON c.menu_id = m.id
              WHERE c.session_id = ?"""
    set_cond = "" if set_filter is None else " AND c.is_set = ?"
    set_args = [] if set_filter is None else [set_filter]

    # 1차: 완전 일치
    cur.execute(base + set_cond + " AND REPLACE_SPACE(m.name) = ?",
                [session_id] + set_args + [normalized])
    exact_rows = cur.fetchall()
    if exact_rows:
        return exact_rows, "exact"

    # 2차: 토큰이 여러 개면 AND 검색 + 가장 긴 토큰으로 추가 검색해서 병합
    if len(tokens) > 1:
        and_conditions = " AND ".join(["REPLACE_SPACE(m.name) LIKE ?" for _ in tokens])
        cur.execute(base + set_cond + f" AND {and_conditions}",
                    [session_id] + set_args + [f"%{t}%" for t in tokens])
        rows = cur.fetchall()

        if rows:
            longest_token = max(tokens, key=len)
            cur.execute(base + set_cond + " AND REPLACE_SPACE(m.name) LIKE ?",
                        [session_id] + set_args + [f"%{longest_token}%"])
            existing_ids = {r[0] for r in rows}
            for row in cur.fetchall():
                if row[0] not in existing_ids:
                    rows.append(row)
                    existing_ids.add(row[0])
            return rows, "token"

    # 3차: 접두어 단계별 수집.
    # 잘리지 않은 전체 입력으로 찾았으면 신뢰도가 높으므로("불고기버거" -> "한우불고기버거")
    # 접두어 노이즈를 섞지 않고 즉시 종료한다. 잘라낸 접두어로만 걸린 경우만 확인 대상.
    terms = _build_search_terms(normalized, clean_name)
    collected = {}
    stage = None
    half = max(3, len(normalized) // 2)

    for term in terms:
        cur.execute(base + set_cond + " AND REPLACE_SPACE(m.name) LIKE ?",
                    [session_id] + set_args + [f"%{term}%"])
        for row in cur.fetchall():
            if row[0] not in collected:
                collected[row[0]] = row

        if collected:
            if term == normalized:
                stage = "prefix_full"
                break
            stage = "prefix"
            if len(term) <= half:
                break

    return list(collected.values()), stage



@tool
def add_to_cart(item_name: str, quantity: int = 1, customer_allergies: list[str] = []) -> str:
    """장바구니에 메뉴를 추가한다.

    item_name: 손님이 말한 메뉴명. 정확하지 않아도 자동으로 유사 메뉴를 찾아준다.
    customer_allergies: 손님이 대화 중 언급한 알레르기 성분 목록. 언급이 없으면 빈 리스트로 두어라.
                        예) "새우 알레르기 있어요" → ["새우"]
    알레르기 포함으로 추가 불가 메시지가 반환되면 손님에게 안내하고 다른 메뉴를 권유하라.
    여러 메뉴 선택지가 반환되면 그대로 보여주고 손님이 메뉴 이름으로 답하면 다시 호출하라.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    # [BEST], [NEW] 등 badge 태그 제거, "세트" 단어 제거 (세트는 upgrade_to_set으로 처리)
    clean_name = re.sub(r'\[.*?\]', '', item_name).strip()
    clean_name = re.sub(r'\s*세트\s*', ' ', clean_name).strip()
    normalized = clean_name.replace(" ", "")

    # 1차: 완전 일치.
    cur.execute(
        "SELECT id, price, name, allergy FROM menu WHERE REPLACE_SPACE(name) = ?",
        (normalized,)
    )
    exact_row = cur.fetchone()

    if exact_row:
        rows = [exact_row]
    else:
        tokens = [t for t in clean_name.split() if t] or [normalized]
        rows = []

        # 2차: 토큰이 여러 개면 AND 검색 (모든 토큰 포함).
        if len(tokens) > 1:
            and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in tokens])
            cur.execute(
                f"SELECT id, price, name, allergy FROM menu WHERE {and_conditions}",
                [f"%{t}%" for t in tokens]
            )
            rows = cur.fetchall()

            # AND 결과가 있을 때만 가장 긴 토큰으로 추가 검색해서 병합.
            if rows:
                longest_token = max(tokens, key=len)
                cur.execute(
                    "SELECT id, price, name, allergy FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
                    (f"%{longest_token}%",)
                )
                existing_ids = {r[0] for r in rows}
                for row in cur.fetchall():
                    if row[0] not in existing_ids:
                        rows.append(row)
                        existing_ids.add(row[0])

        # 2.5차: 토큰 단축 또는 제거하며 AND 재시도
        if not rows and len(tokens) > 1:
            # 먼저 각 토큰을 접두어로 단축 시도 (마지막 토큰부터 — 카테고리어가 보통 뒤에 옴)
            for skip_idx in range(len(tokens) - 1, -1, -1):
                tok = tokens[skip_idx]
                for trim in range(1, len(tok)):
                    shortened = tok[:-trim]
                    if len(shortened) < 2:
                        break
                    test_tokens = tokens[:skip_idx] + [shortened] + tokens[skip_idx + 1:]
                    and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in test_tokens])
                    cur.execute(
                        f"SELECT id, price, name, allergy FROM menu WHERE {and_conditions}",
                        [f"%{t}%" for t in test_tokens]
                    )
                    rows = cur.fetchall()
                    if rows:
                        break
                if rows:
                    break

            # 단축으로도 안 되면 토큰 통째로 제거 (3개 이상일 때, 뒤 토큰부터 제거)
            if not rows and len(tokens) > 2:
                for skip_idx in range(len(tokens) - 1, -1, -1):
                    subset = [t for i, t in enumerate(tokens) if i != skip_idx]
                    and_conditions = " AND ".join(["REPLACE_SPACE(name) LIKE ?" for _ in subset])
                    cur.execute(
                        f"SELECT id, price, name, allergy FROM menu WHERE {and_conditions}",
                        [f"%{t}%" for t in subset]
                    )
                    rows = cur.fetchall()
                    if rows:
                        break

        # 3차: 접두어를 긴 것부터 수집, 검색어 절반 길이까지 내려가며 누락 메뉴 추가.
        if not rows:
            terms = _build_search_terms(normalized, clean_name)
            collected = {}
            half = max(3, len(normalized) // 2)
            for term in terms:
                cur.execute(
                    "SELECT id, price, name, allergy FROM menu WHERE REPLACE_SPACE(name) LIKE ?",
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
        return f"'{item_name}' 메뉴를 찾을 수 없습니다."

    # 여러 메뉴가 매칭되면 선택지 반환.
    if len(rows) > 1:
        conn.close()
        options = "\n".join([f"- {name} ({price}원)" for _, price, name, _ in rows])
        return f"'{item_name}'에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 원하시나요?\n{options}"

    menu_id, price_str, actual_name, allergy = rows[0]

    # 손님이 언급한 알레르기 성분이 메뉴에 포함되면 담기 거부
    if customer_allergies and allergy:
        matched = [a for a in customer_allergies if a in allergy]
        if matched:
            conn.close()
            return f"'{actual_name}'에 {', '.join(matched)} 성분이 포함되어 있어 추가할 수 없습니다."
    try:
        unit_price = int(price_str) if isinstance(price_str, int) else int(price_str.replace(",", ""))
    except (ValueError, AttributeError):
        unit_price = 0
    session_id = current_session_id.get()

    # 이미 담긴 메뉴면 수량 증가, 없으면 새로 추가.
    cur.execute(
        "SELECT cart_id, quantity FROM cart WHERE session_id = ? AND menu_id = ? AND is_set = 0",
        (session_id, menu_id)
    )
    existing = cur.fetchone()

    if existing:
        cart_id, current_qty = existing
        cur.execute(
            "UPDATE cart SET quantity = ? WHERE cart_id = ?",
            (current_qty + quantity, cart_id)
        )
    else:
        cur.execute(
            "INSERT INTO cart (session_id, menu_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (session_id, menu_id, quantity, unit_price),
        )

    conn.commit()
    conn.close()

    return f"{actual_name} {quantity}개를 장바구니에 추가했습니다. (menu_id:{menu_id})"


@tool
def view_cart() -> str:
    """장바구니에 담긴 메뉴 목록과 총 금액을 반환한다.
    손님이 "장바구니 확인", "뭐 담았어", "총 얼마야" 등을 물을 때 사용하라.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.name, c.quantity, c.unit_price, c.is_set
        FROM cart c
        JOIN menu m ON c.menu_id = m.id
        WHERE c.session_id = ?
    """, (current_session_id.get(),))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return "장바구니가 비어 있습니다."

    lines = []
    total = 0
    for name, qty, unit_price, is_set in rows:
        subtotal = qty * unit_price
        total += subtotal
        lines.append(f"{_cart_label(name, is_set)} x {qty} = {subtotal:,}원")

    lines.append(f"합계: {total:,}원")
    return "\n".join(lines)


@tool
def remove_from_cart(item_name: str, confirm: bool = False) -> str:
    """장바구니에서 메뉴를 제거한다.

    메뉴명이 명확히 여러 개일 때만 여러 번 호출하라. 1개만 언급했을 때는 1번만 호출하라.
    여러 메뉴 선택지가 반환되면 손님에게 어떤 메뉴를 취소할지 물어봐라.
    손님이 "세트"/"단품"을 말했으면 item_name에 그대로 포함하라. 해당 항목만 골라낸다.

    confirm: 툴이 확인을 요청했고 손님이 맞다고 답한 경우에만 True로 다시 호출하라.
             손님 확인 없이 임의로 True를 넣지 마라.
    """
    session_id = current_session_id.get()

    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    rows, match_stage = _match_cart_item(cur, session_id, item_name)

    if not rows:
        conn.close()
        return f"장바구니에 '{item_name}'에 해당하는 메뉴가 없습니다."

    # 여러 메뉴가 매칭되면 선택지 반환
    if len(rows) > 1:
        conn.close()
        options = "\n".join([f"- {_cart_label(name, is_set)}" for _, name, is_set in rows])
        return f"'{item_name}'에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 취소하시겠어요?\n{options}"

    cart_id, actual_name, is_set = rows[0]
    label = _cart_label(actual_name, is_set)

    # 삭제는 되돌릴 수 없으므로 신뢰도가 낮은 접두어 매칭은 손님 확인을 먼저 받는다.
    if match_stage == "prefix" and not confirm:
        conn.close()
        return (f"'{item_name}'과(와) 비슷한 '{label}'이(가) 장바구니에 있습니다. "
                f"이 메뉴가 맞는지 손님께 확인한 뒤, 맞으면 confirm=True로 다시 호출하라.")

    cur.execute("DELETE FROM cart WHERE cart_id = ?", (cart_id,))
    conn.commit()
    conn.close()

    return f"{label}을(를) 장바구니에서 제거했습니다."


@tool
def update_cart_quantity(item_name: str, quantity: int, confirm: bool = False) -> str:
    """장바구니에 담긴 메뉴의 수량을 변경한다.
    quantity가 0 이하면 메뉴를 장바구니에서 제거한다.

    item_name: 수량을 변경할 메뉴명. 손님이 "세트"/"단품"을 말했으면 그대로 포함하라.
    quantity: 변경할 수량
    confirm: 툴이 확인을 요청했고 손님이 맞다고 답한 경우에만 True로 다시 호출하라.
             손님 확인 없이 임의로 True를 넣지 마라.
    """
    session_id = current_session_id.get()

    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    rows, match_stage = _match_cart_item(cur, session_id, item_name)

    if not rows:
        conn.close()
        return f"장바구니에 '{item_name}'에 해당하는 메뉴가 없습니다."

    if len(rows) > 1:
        conn.close()
        options = "\n".join([f"- {_cart_label(name, is_set)}" for _, name, is_set in rows])
        return f"'{item_name}'에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 변경하시겠어요?\n{options}"

    cart_id, actual_name, is_set = rows[0]
    label = _cart_label(actual_name, is_set)

    # 수량 변경·삭제도 파괴적 연산이므로 신뢰도가 낮으면 손님 확인을 먼저 받는다.
    if match_stage == "prefix" and not confirm:
        conn.close()
        return (f"'{item_name}'과(와) 비슷한 '{label}'이(가) 장바구니에 있습니다. "
                f"이 메뉴가 맞는지 손님께 확인한 뒤, 맞으면 confirm=True로 다시 호출하라.")

    if quantity <= 0:
        cur.execute("DELETE FROM cart WHERE cart_id = ?", (cart_id,))
        conn.commit()
        conn.close()
        return f"{label}을(를) 장바구니에서 제거했습니다."

    cur.execute("UPDATE cart SET quantity = ? WHERE cart_id = ?", (quantity, cart_id))
    conn.commit()
    conn.close()

    return f"{label} 수량을 {quantity}개로 변경했습니다."


@tool
def confirm_order(payment_method: str = "카드") -> str:
    """장바구니를 주문 완료 처리한다.
    반드시 손님이 결제 수단(카드/모바일)을 명확히 선택한 후에만 호출하라.
    "담아줘", "응", "네" 등 장바구니 담기 확인은 add_to_cart를 사용하라. 이 툴을 쓰지 마라.
    payment_method: 결제 수단. 카드/모바일 중 하나.
    """
    if payment_method not in ("카드", "모바일"):
        return "결제 수단은 카드 또는 모바일 중 하나를 선택해 주세요."

    session_id = current_session_id.get()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 장바구니 조회
    cur.execute("""
        SELECT m.name, c.quantity, c.unit_price, c.is_set
        FROM cart c
        JOIN menu m ON c.menu_id = m.id
        WHERE c.session_id = ?
    """, (session_id,))
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return "장바구니가 비어 있습니다. 먼저 메뉴를 담아주세요."

    # 총 금액 계산
    total_price = sum(qty * unit_price for _, qty, unit_price, _ in rows)

    # orders 테이블에 저장
    cur.execute(
        "INSERT INTO orders (session_id, total_price, payment_method, status) VALUES (?, ?, ?, 'done')",
        (session_id, total_price, payment_method)
    )
    order_id = cur.lastrowid

    # order_items 테이블에 상세 내역 저장
    cur.execute("""
        SELECT menu_id, quantity, unit_price, drink_option, side_option FROM cart WHERE session_id = ?
    """, (session_id,))
    cart_items = cur.fetchall()
    for menu_id, quantity, unit_price, drink_option, side_option in cart_items:
        cur.execute(
            "INSERT INTO order_items (order_id, menu_id, quantity, unit_price, drink_option, side_option) VALUES (?, ?, ?, ?, ?, ?)",
            (order_id, menu_id, quantity, unit_price, drink_option, side_option)
        )

    # 장바구니 비우기
    cur.execute("DELETE FROM cart WHERE session_id = ?", (session_id,))

    conn.commit()
    conn.close()

    lines = [f"{_cart_label(name, is_set)} x{qty} = {qty * unit_price:,}원" for name, qty, unit_price, is_set in rows]
    lines.append(f"총 결제 금액: {total_price:,}원")
    lines.append("주문이 완료되었습니다. 감사합니다!")
    return "\n".join(lines)


@tool
def upgrade_to_set(burger_name: str, drink_option: str, side_option: str) -> str:
    """장바구니의 단품 버거를 세트로 업그레이드한다.
    손님이 세트 여부와 음료/사이드를 모두 선택한 후 호출하라.

    burger_name: 세트로 바꿀 버거명
    drink_option: 선택한 음료명 (예: 콜라, 사이다)
    side_option: 선택한 사이드명 (예: 포테이토, 치즈스틱)
    """
    session_id = current_session_id.get()
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    clean_name = burger_name.strip()
    tokens = [t for t in clean_name.split() if t] or [clean_name.replace(" ", "")]

    def search_cart_set(token_list):
        and_conditions = " AND ".join(["REPLACE_SPACE(m.name) LIKE ?" for _ in token_list])
        cur.execute(f"""
            SELECT c.cart_id, m.name, s.set_price
            FROM cart c
            JOIN menu m ON c.menu_id = m.id
            JOIN set_menus s ON s.burger_menu_id = m.id
            WHERE c.session_id = ? AND {and_conditions}
        """, [session_id] + [f"%{t}%" for t in token_list])
        return cur.fetchone()

    # 1차: 전체 토큰 AND 검색
    row = search_cart_set(tokens)

    # 2차: 토큰 하나씩 제거하며 재시도 (뒤 토큰부터 — 카테고리어가 보통 뒤에 옴)
    if not row and len(tokens) > 1:
        for skip_idx in range(len(tokens) - 1, -1, -1):
            subset = [t for i, t in enumerate(tokens) if i != skip_idx]
            row = search_cart_set(subset)
            if row:
                break

    if not row:
        conn.close()
        return f"장바구니에 세트 가능한 '{burger_name}' 버거가 없습니다."

    cart_id, burger_name_actual, set_price = row

    # 선택한 음료/사이드의 option_id와 추가금액 조회
    total_price = set_price
    drink_option_id = None
    side_option_id = None

    for option_name, option_type in [(drink_option, '드링크'), (side_option, '사이드')]:
        opt_normalized = option_name.replace(" ", "")
        cur.execute("""
            SELECT o.option_id, o.extra_price FROM options o
            JOIN menu m ON o.menu_id = m.id
            WHERE REPLACE_SPACE(m.name) LIKE ? AND o.option_type = ?
        """, (f"%{opt_normalized}%", option_type))
        row = cur.fetchone()
        if row:
            option_id, extra_price = row
            if option_type == '드링크':
                drink_option_id = option_id
            else:
                side_option_id = option_id
            if extra_price:
                total_price += extra_price

    cur.execute(
        "UPDATE cart SET is_set=1, drink_option=?, side_option=?, unit_price=? WHERE cart_id=?",
        (drink_option_id, side_option_id, total_price, cart_id)
    )
    conn.commit()
    conn.close()

    return f"{burger_name_actual} 세트로 변경했습니다. (음료: {drink_option}, 사이드: {side_option}, {total_price:,}원)"


@tool
def downgrade_to_single(burger_name: str, confirm: bool = False) -> str:
    """장바구니의 세트 버거를 단품으로 변경한다.
    "단품으로 바꿔줘", "세트 취소해줘", "처음에 담은 거 단품으로" 등의 요청에 사용하라.
    직전 대화 맥락으로 메뉴를 특정하고 이 툴을 호출하라.

    burger_name: 단품으로 변경할 버거명
    confirm: 툴이 확인을 요청했고 손님이 맞다고 답한 경우에만 True로 다시 호출하라.
             손님 확인 없이 임의로 True를 넣지 마라.
    """
    session_id = current_session_id.get()
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    clean_name = re.sub(r'\[.*?\]', '', burger_name).strip()
    clean_name = re.sub(r'\s*(세트|단품)\s*', ' ', clean_name).strip()
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    # 1차: 완전 일치 (세트인 항목만)
    cur.execute(
        """SELECT c.cart_id, m.name, m.price FROM cart c
           JOIN menu m ON c.menu_id = m.id
           WHERE c.session_id = ? AND c.is_set = 1 AND REPLACE_SPACE(m.name) = ?""",
        (session_id, normalized)
    )
    row = cur.fetchone()

    if not row and len(tokens) > 1:
        and_conditions = " AND ".join(["REPLACE_SPACE(m.name) LIKE ?" for _ in tokens])
        cur.execute(
            f"""SELECT c.cart_id, m.name, m.price FROM cart c
                JOIN menu m ON c.menu_id = m.id
                WHERE c.session_id = ? AND c.is_set = 1 AND {and_conditions}""",
            [session_id] + [f"%{t}%" for t in tokens]
        )
        row = cur.fetchone()

    if not row:
        # 이름이 전혀 맞지 않은 경우. 말없이 최근 세트를 고르면 손님이 고른
        # 음료·사이드가 통째로 사라지므로, 실행하지 않고 되묻는다.
        cur.execute(
            """SELECT c.cart_id, m.name, m.price FROM cart c
               JOIN menu m ON c.menu_id = m.id
               WHERE c.session_id = ? AND c.is_set = 1
               ORDER BY c.cart_id DESC""",
            (session_id,)
        )
        set_rows = cur.fetchall()

        if not set_rows:
            conn.close()
            return "장바구니에 세트로 담긴 버거가 없습니다."

        if len(set_rows) > 1:
            conn.close()
            options = "\n".join([f"- {name} 세트" for _, name, _ in set_rows])
            return (f"장바구니에 '{burger_name}' 세트가 없습니다. "
                    f"어떤 세트를 단품으로 바꿀까요?\n{options}")

        if not confirm:
            conn.close()
            return (f"장바구니에 '{burger_name}' 세트가 없습니다. 대신 "
                    f"'{set_rows[0][1]} 세트'가 담겨 있습니다. 이 메뉴가 맞는지 "
                    f"손님께 확인한 뒤, 맞으면 confirm=True로 다시 호출하라.")

        row = set_rows[0]

    cart_id, actual_name, single_price = row
    try:
        unit_price = int(str(single_price).replace(",", ""))
    except (ValueError, AttributeError):
        unit_price = 0

    cur.execute(
        "UPDATE cart SET is_set=0, drink_option=NULL, side_option=NULL, unit_price=? WHERE cart_id=?",
        (unit_price, cart_id)
    )
    conn.commit()
    conn.close()

    return f"{actual_name} 세트를 단품으로 변경했습니다."


@tool
def clear_cart() -> str:
    """장바구니를 전부 비운다.
    손님이 "다 취소해줘", "처음부터 다시 할게" 등을 말할 때 사용하라.
    """
    session_id = current_session_id.get()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("DELETE FROM cart WHERE session_id = ?", (session_id,))
    affected = cur.rowcount
    conn.commit()
    conn.close()

    if affected == 0:
        return "장바구니가 이미 비어 있습니다."
    return "장바구니를 비웠습니다."
