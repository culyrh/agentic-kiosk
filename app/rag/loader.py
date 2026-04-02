
# import ast
import json
# import re
from langchain_core.documents import Document


# def _parse_num(value: str) -> float:
#     # '25(45)' -> 25.0 / '1050(53)' -> 1050.0 / '618' -> 618.0
#     match = re.match(r"[\d.]+", str(value).strip())
#     return float(match.group()) if match else 0.0


def load_menu():

    # 데이터 가져오기
    with open("ria_menu.json", "r", encoding="utf-8") as f:
        menus = json.load(f)

    # 형태 변환
    document = []

    for menu in menus:
        # nutrition = ast.literal_eval(menu["nutrition"])

        # calories  = _parse_num(nutrition.get("열량", 0))
        # protein   = _parse_num(nutrition.get("단백질g(%)", 0))
        # sodium    = _parse_num(nutrition.get("나트륨mg(%)", 0))
        # sugar     = _parse_num(nutrition.get("당류g", 0))
        # fat       = _parse_num(nutrition.get("포화지방", 0))
        # weight    = _parse_num(nutrition.get("총중량", 0))

        badge_text = f"[{menu['badge']}]" if menu.get("badge") else ""
        
        text = f"""
        메뉴명: {menu['name']}{badge_text}
        카테고리: {menu['category']}
        가격: {menu['price']}원
        설명: {menu['description']}
        알레르기: {menu.get('allergy', '')}
        원산지: {menu.get('origin', '')}
        """.strip()

        doc = Document(
            page_content=text,
            
            metadata={ # 조건 검사, 필터링
                "id": menu["id"],      
                "price": int(menu["price"].replace(",", "")),
                "category": menu["category"],
                "badge": menu.get("badge", ""),
                "allergy": menu.get("allergy", ""),
                "origin": menu.get("origin", ""),
            }
        )

        document.append(doc)
    return document
