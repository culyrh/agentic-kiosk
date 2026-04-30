# db/sqlite.py
# 역할 : 다른파일들이 DB에 직접 접근하지 않고 db/sqlite.py의 함수를 통해서만 접근하도록 하는 중간 레이어

import sqlite3
import json
from pathlib import Path

DB_PATH = Path("data/ria_menu.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =====================================================
# 메뉴
# =====================================================

def list_menus(limit: int = 50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, category, badge, price, img_url, spicy_level
        FROM menu
        ORDER BY id ASC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_menu_by_id(menu_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM menu WHERE id = ?", (menu_id,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    for key in ("nutrition", "badge", "allergy"):
        if result.get(key):
            try:
                result[key] = json.loads(result[key])
            except:
                pass
    return result


def get_menu_by_name(name: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM menu WHERE name = ?", (name,)).fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    for key in ("nutrition", "badge", "allergy"):
        if result.get(key):
            try:
                result[key] = json.loads(result[key])
            except:
                pass
    return result


def search_menu_by_keyword(keyword: str, limit: int = 20):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, category, badge, price, img_url, spicy_level
        FROM menu
        WHERE name LIKE ? OR description LIKE ?
        ORDER BY id ASC
        LIMIT ?
    """, (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_menus_by_category(category: str, limit: int = 50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, category, badge, price, img_url, spicy_level
        FROM menu
        WHERE category = ?
        ORDER BY id ASC
        LIMIT ?
    """, (category, limit)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_set_by_burger_id(burger_menu_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM set_menus WHERE burger_menu_id = ?
    """, (burger_menu_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# =====================================================
# 옵션
# =====================================================

def get_options(option_type: str = None):
    conn = get_connection()
    if option_type:
        rows = conn.execute("""
            SELECT o.option_id, o.option_type, o.extra_price, m.name, m.price, m.img_url
            FROM options o
            JOIN menu m ON o.menu_id = m.id
            WHERE o.option_type = ?
            ORDER BY o.option_id ASC
        """, (option_type,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT o.option_id, o.option_type, o.extra_price, m.name, m.price, m.img_url
            FROM options o
            JOIN menu m ON o.menu_id = m.id
            ORDER BY o.option_type ASC, o.option_id ASC
        """).fetchall()
    conn.close()
    return [dict(row) for row in rows]

# =====================================================
# 세트 메뉴
# =====================================================

def list_sets():
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*, m.name as burger_name, m.img_url as burger_img_url
        FROM set_menus s
        JOIN menu m ON s.burger_menu_id = m.id
        ORDER BY s.set_id ASC
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_set_by_id(set_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT s.*, m.name as burger_name, m.img_url as burger_img_url
        FROM set_menus s
        JOIN menu m ON s.burger_menu_id = m.id
        WHERE s.set_id = ?
    """, (set_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# =====================================================
# 장바구니
# =====================================================

def get_cart(session_id: str):
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.*, m.name, m.img_url
        FROM cart c
        JOIN menu m ON c.menu_id = m.id
        WHERE c.session_id = ?
    """, (session_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_cart(session_id: str, menu_id: int, is_set: int,
             drink_option: str, side_option: str, quantity: int, unit_price: int):
    conn = get_connection()
    
    # 이미 같은 메뉴가 있는지 확인
    existing = conn.execute("""
        SELECT cart_id, quantity FROM cart
        WHERE session_id = ? AND menu_id = ? AND is_set = ?
    """, (session_id, menu_id, is_set)).fetchone()
    
    if existing:
        # 있으면 수량 증가
        conn.execute("""
            UPDATE cart SET quantity = quantity + ?
            WHERE cart_id = ?
        """, (quantity, existing["cart_id"]))
        cart_id = existing["cart_id"]
    else:
        # 없으면 새로 추가
        cursor = conn.execute("""
            INSERT INTO cart (session_id, menu_id, is_set, drink_option, side_option, quantity, unit_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, menu_id, is_set, drink_option, side_option, quantity, unit_price))
        cart_id = cursor.lastrowid
    
    conn.commit()
    conn.close()
    return cart_id


def update_cart(cart_id: int, quantity: int):
    conn = get_connection()
    conn.execute("UPDATE cart SET quantity = ? WHERE cart_id = ?", (quantity, cart_id))
    conn.commit()
    conn.close()

def increase_cart(cart_id: int):
    conn = get_connection()
    conn.execute("UPDATE cart SET quantity = quantity + 1 WHERE cart_id = ?", (cart_id,))
    conn.commit()
    conn.close()

def decrease_cart(cart_id: int):
    conn = get_connection()
    # 수량 1이면 삭제
    row = conn.execute("SELECT quantity FROM cart WHERE cart_id = ?", (cart_id,)).fetchone()
    if row and row["quantity"] <= 1:
        conn.execute("DELETE FROM cart WHERE cart_id = ?", (cart_id,))
    else:
        conn.execute("UPDATE cart SET quantity = quantity - 1 WHERE cart_id = ?", (cart_id,))
    conn.commit()
    conn.close()


def delete_cart_item(cart_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM cart WHERE cart_id = ?", (cart_id,))
    conn.commit()
    conn.close()


def clear_cart(session_id: str):
    conn = get_connection()
    conn.execute("DELETE FROM cart WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


# =====================================================
# 주문/결제
# =====================================================

def get_order_by_id(order_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_order(session_id: str, total_price: int, payment_method: str):
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO orders (session_id, total_price, payment_method, status)
        VALUES (?, ?, ?, 'pending')
    """, (session_id, total_price, payment_method))
    order_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return order_id


def complete_payment(order_id: int):
    conn = get_connection()
    conn.execute("UPDATE orders SET status = 'paid' WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()


def get_orders(session_id: str):
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM orders WHERE session_id = ?
        ORDER BY created_at DESC
    """, (session_id,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]
