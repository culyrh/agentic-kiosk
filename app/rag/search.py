# app/rag/search.py
from app.rag.chroma import get_chroma_db

def search_menu(query: str, k: int = 5, score_threshold: float = 0.5):
    db = get_chroma_db()
    results = db.similarity_search_with_score(query, k=k)
    
    return [
        {
            "menu_id": doc.metadata.get("id"),
            "name": doc.page_content.split("\n")[0].replace("메뉴명:", "").strip(),
            "score": round(score, 4),
            "content": doc.page_content
        }
        for doc, score in results
        if score < score_threshold
    ]