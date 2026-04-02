
from langchain.tools import tool
from app.rag.chroma import get_chroma_db

# 임시 저장 (실제로는 DB/Redis 권장)
cart = {}

### 지금은 예시임.

@tool
def add_to_cart(item_name:str, quantity: int = 1):
    """장바구니에 메뉴 추가"""
    
    return f"{item_name} {quantity}개 추가"


@tool
def remove_from_cart(item_name: str):
    """장바구니에서 메뉴를 제거한다"""
    
    return f"{item_name}이 장바구니에 없음"