import sqlite3
from pathlib import Path

DB_PATH = Path("data/menu.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_menus(limit: int = 50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, category, price, spicy_level, kcal
        FROM menus
        ORDER BY name ASC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_menu_by_id(menu_id: int):
    conn = get_connection()
    row = conn.execute("""
        SELECT *
        FROM menus
        WHERE id = ?
    """, (menu_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_menu_by_name(name: str):
    conn = get_connection()
    row = conn.execute("""
        SELECT *
        FROM menus
        WHERE name = ?
    """, (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def search_menu_by_keyword(keyword: str, limit: int = 20):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, category, price, spicy_level, kcal
        FROM menus
        WHERE name LIKE ? OR description LIKE ?
        ORDER BY name ASC
        LIMIT ?
    """, (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
    conn.close()
    return [dict(row) for row in rows]