import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/menu.db")
JSON_PATH = Path("data/menu.json")


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category TEXT,
        price INTEGER,
        description TEXT,
        image_url TEXT,
        is_set_available INTEGER,
        spicy_level INTEGER,
        allergens TEXT,
        kcal INTEGER,
        origin_text TEXT,
        raw_source TEXT
    )
    """)
    conn.commit()


def load_json() -> list[dict]:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def insert_items(conn: sqlite3.Connection, items: list[dict]) -> int:
    inserted_count = 0

    for item in items:
        if "," in item.get("name", ""):
            continue

        conn.execute("""
        INSERT OR REPLACE INTO menus
        (name, category, price, description, image_url, is_set_available, spicy_level, allergens, kcal, origin_text, raw_source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("name"),
            item.get("category"),
            item.get("price"),
            item.get("description"),
            item.get("image_url"),
            1 if item.get("is_set_available") else 0,
            item.get("spicy_level"),
            ", ".join(item.get("allergens", [])) if isinstance(item.get("allergens"), list) else item.get("allergens"),
            item.get("kcal"),
            item.get("origin_text"),
            item.get("raw_source"),
        ))
        inserted_count += 1

    conn.commit()
    return inserted_count


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    conn.execute("DELETE FROM menus")
    conn.commit()

    items = load_json()
    inserted_count = insert_items(conn, items)

    conn.close()
    print(f"loaded {inserted_count} items into {DB_PATH}")

if __name__ == "__main__":
    main()