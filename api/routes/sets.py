# api/routes/sets.py
from fastapi import APIRouter, HTTPException
from db.sqlite import list_sets, get_set_by_id

router = APIRouter(prefix="/sets", tags=["sets"])

@router.get("")
def get_sets():
    return {"items": list_sets()}

@router.get("/{set_id}")
def get_set(set_id: int):
    set_info = get_set_by_id(set_id)
    if not set_info:
        raise HTTPException(status_code=404, detail="세트 메뉴를 찾을 수 없습니다.")
    return set_info