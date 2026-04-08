# api/routes/order.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.sqlite import create_order, complete_payment, get_orders, get_cart, clear_cart

router = APIRouter(prefix="/order", tags=["order"])

class OrderRequest(BaseModel):
    session_id: str
    payment_method: str = "card"

# 주문 생성
@router.post("")
def create_new_order(req: OrderRequest):
    items = get_cart(req.session_id)
    if not items:
        raise HTTPException(status_code=400, detail="장바구니가 비어있습니다.")
    total_price = sum(i["unit_price"] * i["quantity"] for i in items)
    order_id = create_order(req.session_id, total_price, req.payment_method)
    return {"order_id": order_id, "total_price": total_price, "message": "주문이 생성됐습니다."}

# 결제 완료
@router.post("/{order_id}/payment")
def payment(order_id: int, req: OrderRequest):
    complete_payment(order_id)
    clear_cart(req.session_id)
    return {"message": "결제가 완료됐습니다.", "order_id": order_id}

# 주문 내역 조회
@router.get("/{session_id}")
def get_order_history(session_id: str):
    orders = get_orders(session_id)
    return {"orders": orders}