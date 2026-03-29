from langchain.tools import tool
from app.rag.chroma import get_chroma_db


def search_menu_logic(query: str, category: str = None):
    
    db = get_chroma_db()
    
    if category:
        results = db.similarity_search(
        query,
        k = 3,
        filter={"category": category}
    )
    else:
        results = db.similarity_search(query, k = 3)    

    
    return[
        {
            "id": doc.metadata.get("id"),
            "name": doc.metadata.get("name"),
        }
        for doc in results
    ]
    



@tool
def search_menu(query: str, category: str = None):
    """사용자 요청에 맞는 메뉴 검색"""
    return search_menu_logic(query, category)