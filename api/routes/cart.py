# api/routes/cart.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.sqlite import (
    get_cart, add_cart, update_cart, delete_cart_item, clear_cart,
    increase_cart, decrease_cart, get_menu_by_id
)

router = APIRouter(prefix="/cart", tags=["cart"])

class CartAddRequest(BaseModel):
    session_id: str
    menu_id: int
    is_set: int = 0
    drink_option: str = ""
    side_option: str = ""
    quantity: int = 1
    unit_price: int = 0

class CartUpdateRequest(BaseModel):
    quantity: int


# 장바구니 조회
@router.get("/{session_id}")
def get_cart_items(session_id: str):
    items = get_cart(session_id)
    total = sum(i["unit_price"] * i["quantity"] for i in items)
    return {"items": items, "total": total}


# 장바구니 담기
@router.post("")
def add_cart_item(req: CartAddRequest):
    # menu_id 유효성 검사
    menu = get_menu_by_id(req.menu_id)
    if not menu:
        raise HTTPException(status_code=404, detail="메뉴를 찾을 수 없습니다.")
    # quantity 검증
    if req.quantity < 1:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다.")
    # unit_price 없으면 DB에서 자동으로 가져오기
    unit_price = req.unit_price if req.unit_price > 0 else menu["price"]
    cart_id = add_cart(
        req.session_id, req.menu_id, req.is_set,
        req.drink_option, req.side_option, req.quantity, unit_price
    )
    return {"cart_id": cart_id, "message": "장바구니에 담겼습니다."}


# 수량 수정
@router.put("/{cart_id}")
def update_cart_item(cart_id: int, req: CartUpdateRequest):
    if req.quantity < 1:
        raise HTTPException(status_code=400, detail="수량은 1 이상이어야 합니다.")
    update_cart(cart_id, req.quantity)
    return {"message": "수량이 수정됐습니다."}


# 수량 +1
@router.patch("/{cart_id}/increase")
def increase_cart_item(cart_id: int):
    increase_cart(cart_id)
    return {"message": "수량이 증가됐습니다."}


# 수량 -1 (1이면 자동 삭제)
@router.patch("/{cart_id}/decrease")
def decrease_cart_item(cart_id: int):
    decrease_cart(cart_id)
    return {"message": "수량이 감소됐습니다."}


# 항목 삭제
@router.delete("/{cart_id}")
def delete_item(cart_id: int):
    delete_cart_item(cart_id)
    return {"message": "삭제됐습니다."}


# 장바구니 전체 비우기
@router.delete("/session/{session_id}")
def clear_cart_items(session_id: str):
    clear_cart(session_id)
    return {"message": "장바구니가 비워졌습니다."}