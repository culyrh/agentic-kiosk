
import json
import re
import sqlite3
from langchain_core.documents import Document

DB_PATH = "data/ria_menu.db"


def load_menu():

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category, name, badge, price, description, allergy, origin, spicy_level, nutrition
        FROM menu
    """)
    rows = cur.fetchall()
    conn.close()

    documents = []

    for id, category, name, badge, price, description, allergy, origin, spicy_level, nutrition in rows:

        nutrition_dict = json.loads(nutrition) if nutrition else {}
        raw_calories = nutrition_dict.get("열량", "0") if nutrition_dict else "0"
        match = re.search(r'\d+', str(raw_calories).replace(",", ""))
        calories = int(match.group()) if match else 0

        text = f"""
        메뉴명: {name}
        설명: {description}
        원산지: {origin or ''}
        """.strip()

        doc = Document(
            page_content=text,
            metadata={
                "id": id,
                "price": price,
                "category": category,
                "badge": badge or "",
                "allergy": allergy or "",
                "spicy_level": spicy_level,
                "calories": calories,
            }
        )

        documents.append(doc)

    return documents
