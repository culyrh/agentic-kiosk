from db.sqlite import get_menu_by_name


def run(name: str):
    result = get_menu_by_name(name)
    if not result:
        return {"error": "메뉴를 찾을 수 없습니다."}
    return result