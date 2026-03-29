
import json
from langchain_core.documents import Document



def load_menu():
    
    # 데이터 가져오기
    with open("data/menu.json", "r", encoding="utf-8") as f:
        menus = json.load(f)
    # return menus 
    
    # 형태 변환   
    document = []
    
    for menu in menus:
        text = f"""
        메뉴명: {menu['name']}
        카테고리: {menu['category']}
        가격: {menu['price']}원
        맵기: {menu['spicy_level']} 단계
        설명: {menu['description']} 입니다.
        추천 상황: {', '.join(menu['tags'])}
        """.strip()
        
        doc = Document(
            page_content=text, # 검색용 의미 덩어리 (Semantic chunk)
            metadata={ # LLM이 읽는게 x, 검색 전 필터링에 사용.
                "id": menu["id"],
                "name": menu["name"],
                "price": menu["price"],
                "spicy_level": menu["spicy_level"],
                "category": menu["category"],
                "tags": menu["tags"]
            }
        )    
        
        document.append(doc)
    return document    


    
    
    

