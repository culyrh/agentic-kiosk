# api/routes/menu.py
from fastapi import APIRouter, HTTPException, Query
from db.sqlite import (
    list_menus, get_menu_by_id, search_menu_by_keyword,
    get_menus_by_category, get_set_by_burger_id
)

router = APIRouter(prefix="/menu", tags=["menu"])

# 전체 메뉴 조회 / 키워드 검색 / 카테고리 필터
@router.get("")
def get_menus(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = 50
):
    if q:
        return {"items": search_menu_by_keyword(q, limit)}
    if category:
        return {"items": get_menus_by_category(category, limit)}
    return {"items": list_menus(limit)}

# 단건 조회
@router.get("/{menu_id}")
def get_menu_detail(menu_id: int):
    menu = get_menu_by_id(menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
    return menu

# 세트 조회
@router.get("/{menu_id}/set")
def get_menu_set(menu_id: int):
    set_info = get_set_by_burger_id(menu_id)
    if not set_info:
        raise HTTPException(status_code=404, detail="세트 메뉴가 없습니다.")
    return {"set": set_info}