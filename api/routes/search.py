# api/routes/search.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.rag.search import search_menu  # ← AI 로직 import

router = APIRouter(prefix="/search", tags=["search"])

class SearchRequest(BaseModel):
    query: str
    k: int = 5
    score_threshold: float = 0.5

@router.post("")
def search(req: SearchRequest):
    results = search_menu(req.query, req.k, req.score_threshold)
    return {"query": req.query, "results": results}