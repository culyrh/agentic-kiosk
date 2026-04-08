# api/routes/search.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.rag.chroma import get_chroma_db

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    k: int = 5
    score_threshold: float = 0.5

@router.post("")
def search_menu(req: SearchRequest):
    db = get_chroma_db()
    results = db.similarity_search_with_score(req.query, k=req.k)
    
    filtered = [
    {
        "menu_id": doc.metadata.get("id"),      # menu_id → id
        "name": doc.page_content.split("\n")[0].replace("메뉴명:", "").strip(),  # name은 page_content에서 추출
        "score": round(score, 4),
        "content": doc.page_content
    }
    for doc, score in results
    if score < req.score_threshold
    ]    
    
    return {"query": req.query, "results": filtered}