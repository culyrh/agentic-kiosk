
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


@tool
def add_to_cart(item_name: str, quantity: int = 1, force: bool = False) -> str:
    """장바구니에 메뉴를 추가한다.

    item_name: 손님이 말한 메뉴명. 정확하지 않아도 자동으로 유사 메뉴를 찾아준다.
    force: True면 알레르기 경고를 무시하고 강제로 담는다. 손님이 알레르기 확인 후 담겠다고 했을 때만 True로 설정하라.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    # [BEST], [NEW] 등 badge 태그 제거 후 공백 정규화.
    clean_name = re.sub(r'\[.*?\]', '', item_name).strip()
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

            # 가장 긴 토큰으로 추가 검색해서 AND 결과에 없는 메뉴 병합.
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

        # 3차: 접두어를 긴 것부터 수집, 검색어 절반 길이까지 내려가며 누락 메뉴 추가.
        if not rows:
            terms = _build_search_terms(normalized, clean_name)
            collected = {}
            half = max(2, len(normalized) // 2)
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

    # 알레르기 정보가 있으면 경고 반환 (force=True면 건너뜀).
    if not force and allergy:
        conn.close()
        return f"'{actual_name}'에 알레르기 유발 성분이 포함되어 있습니다: {allergy}\n그래도 담으시겠어요?"
    unit_price = int(price_str)
    session_id = current_session_id.get()

    # 이미 담긴 메뉴면 수량 증가, 없으면 새로 추가.
    cur.execute(
        "SELECT cart_id, quantity FROM cart WHERE session_id = ? AND menu_id = ?",
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

    return f"{actual_name} {quantity}개를 장바구니에 추가했습니다."


@tool
def view_cart() -> str:
    """장바구니에 담긴 메뉴 목록과 총 금액을 반환한다.
    손님이 "장바구니 확인", "뭐 담았어", "총 얼마야" 등을 물을 때 사용하라.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.name, c.quantity, c.unit_price
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
    for name, qty, unit_price in rows:
        subtotal = qty * unit_price
        total += subtotal
        lines.append(f"{name} x {qty} = {subtotal:,}원")

    lines.append(f"합계: {total:,}원")
    return "\n".join(lines)


@tool
def remove_from_cart(item_name: str) -> str:
    """장바구니에서 메뉴를 제거한다"""

    session_id = current_session_id.get()

    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    clean_name = re.sub(r'\[.*?\]', '', item_name).strip()
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    # 1차: 완전 일치
    cur.execute(
        """SELECT m.id, m.name FROM cart c
           JOIN menu m ON c.menu_id = m.id
           WHERE c.session_id = ? AND REPLACE_SPACE(m.name) = ?""",
        (session_id, normalized)
    )
    exact_row = cur.fetchone()

    if exact_row:
        rows = [exact_row]
    else:
        rows = []

        # 2차: AND 검색 (다중 토큰)
        if len(tokens) > 1:
            and_conditions = " AND ".join(["REPLACE_SPACE(m.name) LIKE ?" for _ in tokens])
            cur.execute(
                f"""SELECT m.id, m.name FROM cart c
                    JOIN menu m ON c.menu_id = m.id
                    WHERE c.session_id = ? AND {and_conditions}""",
                [session_id] + [f"%{t}%" for t in tokens]
            )
            rows = cur.fetchall()

            # 가장 긴 토큰으로 추가 검색해서 AND 결과에 없는 메뉴 병합
            longest_token = max(tokens, key=len)
            cur.execute(
                """SELECT m.id, m.name FROM cart c
                   JOIN menu m ON c.menu_id = m.id
                   WHERE c.session_id = ? AND REPLACE_SPACE(m.name) LIKE ?""",
                (session_id, f"%{longest_token}%")
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
                    """SELECT m.id, m.name FROM cart c
                       JOIN menu m ON c.menu_id = m.id
                       WHERE c.session_id = ? AND REPLACE_SPACE(m.name) LIKE ?""",
                    (session_id, f"%{term}%")
                )
                for row in cur.fetchall():
                    if row[0] not in collected:
                        collected[row[0]] = row
                if collected and len(term) <= half:
                    break
            rows = list(collected.values())

    if not rows:
        conn.close()
        return f"장바구니에 '{item_name}'에 해당하는 메뉴가 없습니다."

    # 여러 메뉴가 매칭되면 선택지 반환
    if len(rows) > 1:
        conn.close()
        options = "\n".join([f"- {name}" for _, name in rows])
        return f"'{item_name}'에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 취소하시겠어요?\n{options}"

    menu_id, actual_name = rows[0]
    cur.execute("DELETE FROM cart WHERE session_id = ? AND menu_id = ?", (session_id, menu_id))
    conn.commit()
    conn.close()

    return f"{actual_name}을(를) 장바구니에서 제거했습니다."


@tool
def update_cart_quantity(item_name: str, quantity: int) -> str:
    """장바구니에 담긴 메뉴의 수량을 변경한다.
    quantity가 0 이하면 메뉴를 장바구니에서 제거한다.

    item_name: 수량을 변경할 메뉴명
    quantity: 변경할 수량
    """
    session_id = current_session_id.get()

    conn = sqlite3.connect(DB_PATH)
    conn.create_function("REPLACE_SPACE", 1, lambda s: s.replace(" ", "") if s else s)
    cur = conn.cursor()

    clean_name = re.sub(r'\[.*?\]', '', item_name).strip()
    normalized = clean_name.replace(" ", "")
    tokens = [t for t in clean_name.split() if t] or [normalized]

    # 1차: 완전 일치
    cur.execute(
        """SELECT m.id, m.name FROM cart c
           JOIN menu m ON c.menu_id = m.id
           WHERE c.session_id = ? AND REPLACE_SPACE(m.name) = ?""",
        (session_id, normalized)
    )
    exact_row = cur.fetchone()

    if exact_row:
        rows = [exact_row]
    else:
        rows = []

        # 2차: AND 검색 (다중 토큰)
        if len(tokens) > 1:
            and_conditions = " AND ".join(["REPLACE_SPACE(m.name) LIKE ?" for _ in tokens])
            cur.execute(
                f"""SELECT m.id, m.name FROM cart c
                    JOIN menu m ON c.menu_id = m.id
                    WHERE c.session_id = ? AND {and_conditions}""",
                [session_id] + [f"%{t}%" for t in tokens]
            )
            rows = cur.fetchall()

            # 가장 긴 토큰으로 추가 검색해서 AND 결과에 없는 메뉴 병합
            longest_token = max(tokens, key=len)
            cur.execute(
                """SELECT m.id, m.name FROM cart c
                   JOIN menu m ON c.menu_id = m.id
                   WHERE c.session_id = ? AND REPLACE_SPACE(m.name) LIKE ?""",
                (session_id, f"%{longest_token}%")
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
                    """SELECT m.id, m.name FROM cart c
                       JOIN menu m ON c.menu_id = m.id
                       WHERE c.session_id = ? AND REPLACE_SPACE(m.name) LIKE ?""",
                    (session_id, f"%{term}%")
                )
                for row in cur.fetchall():
                    if row[0] not in collected:
                        collected[row[0]] = row
                if collected and len(term) <= half:
                    break
            rows = list(collected.values())

    if not rows:
        conn.close()
        return f"장바구니에 '{item_name}'에 해당하는 메뉴가 없습니다."

    if len(rows) > 1:
        conn.close()
        options = "\n".join([f"- {name}" for _, name in rows])
        return f"'{item_name}'에 해당하는 메뉴가 여러 개 있습니다. 어떤 메뉴를 변경하시겠어요?\n{options}"

    menu_id, actual_name = rows[0]

    if quantity <= 0:
        cur.execute("DELETE FROM cart WHERE session_id = ? AND menu_id = ?", (session_id, menu_id))
        conn.commit()
        conn.close()
        return f"{actual_name}을(를) 장바구니에서 제거했습니다."

    cur.execute(
        "UPDATE cart SET quantity = ? WHERE session_id = ? AND menu_id = ?",
        (quantity, session_id, menu_id)
    )
    conn.commit()
    conn.close()

    return f"{actual_name} 수량을 {quantity}개로 변경했습니다."


@tool
def confirm_order(payment_method: str = "카드") -> str:
    """장바구니를 주문 완료 처리한다.
    손님이 "주문할게요", "결제할게요", "이걸로 할게요" 등을 말할 때 사용하라.
    payment_method: 결제 수단. 기본값 카드. 카드/모바일 중 하나.
    """
    session_id = current_session_id.get()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 장바구니 조회
    cur.execute("""
        SELECT m.name, c.quantity, c.unit_price
        FROM cart c
        JOIN menu m ON c.menu_id = m.id
        WHERE c.session_id = ?
    """, (session_id,))
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return "장바구니가 비어 있습니다. 먼저 메뉴를 담아주세요."

    # 총 금액 계산
    total_price = sum(qty * unit_price for _, qty, unit_price in rows)

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

    lines = [f"{name} x{qty} = {qty * unit_price:,}원" for name, qty, unit_price in rows]
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

    normalized = burger_name.replace(" ", "")

    # cart에 담긴 버거 중 이름이 일치하고 set_menus에 있는 항목을 한 번에 조회
    cur.execute("""
        SELECT c.cart_id, m.name, s.set_price
        FROM cart c
        JOIN menu m ON c.menu_id = m.id
        JOIN set_menus s ON s.burger_menu_id = m.id
        WHERE c.session_id = ? AND REPLACE_SPACE(m.name) LIKE ?
    """, (session_id, f"%{normalized}%"))
    row = cur.fetchone()

    if not row:
        conn.close()
        return f"장바구니에 세트 가능한 '{burger_name}' 버거가 없습니다."

    cart_id, burger_name_actual, set_price = row

    # 선택한 음료/사이드 추가금액 반영
    total_price = set_price
    for option_name, option_type in [(drink_option, '드링크'), (side_option, '사이드')]:
        opt_normalized = option_name.replace(" ", "")
        cur.execute("""
            SELECT o.extra_price FROM options o
            JOIN menu m ON o.menu_id = m.id
            WHERE REPLACE_SPACE(m.name) LIKE ? AND o.option_type = ?
        """, (f"%{opt_normalized}%", option_type))
        ep_row = cur.fetchone()
        if ep_row and ep_row[0]:
            total_price += ep_row[0]

    cur.execute(
        "UPDATE cart SET is_set=1, drink_option=?, side_option=?, unit_price=? WHERE cart_id=?",
        (drink_option, side_option, total_price, cart_id)
    )
    conn.commit()
    conn.close()

    return f"{burger_name_actual} 세트로 변경했습니다. (음료: {drink_option}, 사이드: {side_option}, {total_price:,}원)"


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
