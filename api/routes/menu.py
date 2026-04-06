from fastapi import APIRouter, HTTPException, Query

from db.sqlite import list_menus, get_menu_by_id, search_menu_by_keyword

router = APIRouter(prefix="/menu", tags=["menu"])


@router.get("")
def get_menus(q: str | None = Query(default=None), limit: int = 20):
    if q:
        return {"items": search_menu_by_keyword(q, limit)}
    return {"items": list_menus(limit)}


@router.get("/{menu_id}")
def get_menu_detail(menu_id: int):
    menu = get_menu_by_id(menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
    return menu