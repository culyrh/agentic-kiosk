import sqlite3
from langchain_core.documents import Document

DB_PATH = "data/ria_menu.db"


def load_menu():

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, category, name, badge, price, description, allergy, origin, spicy_level
        FROM menu
    """)
    rows = cur.fetchall()
    conn.close()

    documents = []

    for id, category, name, badge, price, description, allergy, origin, spicy_level in rows:

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
            }
        )

        documents.append(doc)

    return documents
