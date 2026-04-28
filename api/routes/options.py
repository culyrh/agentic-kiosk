# api/routes/options.py
from fastapi import APIRouter, Query
from db.sqlite import get_options

router = APIRouter(prefix="/options", tags=["options"])

@router.get("")
def get_option_list(type: str | None = Query(default=None)):
    """
    세트 구성 옵션 조회
    - type=드링크 → 드링크 목록
    - type=사이드 → 사이드 목록
    - type 없음 → 전체 목록
    """
    items = get_options(type)
    return {"items": items}