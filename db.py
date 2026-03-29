

import sqlite3

def get_connection():
    return sqlite3.connect("ria_menu.db")


def create_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        name TEXT,
        badge TEXT,
        price TEXT,
        description TEXT,
        img_url TEXT,
        allergy TEXT,
        origin TEXT,
        nutrition TEXT
    )
    """)

    conn.commit()
    conn.close()


def insert_menu(data):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO menu (category, name, badge, price, description, img_url, allergy, origin, nutrition)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["category"],
        data["name"],
        data["badge"],
        data["price"],
        data["description"],
        data["img_url"],
        data["allergy"],
        data["origin"],
        str(data["nutrition"])
    ))

    conn.commit()
    conn.close()