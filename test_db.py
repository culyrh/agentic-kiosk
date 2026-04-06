from db.sqlite import list_menus, get_menu_by_name, search_menu_by_keyword

print("=== 메뉴 5개 ===")
print(list_menus(5))

print("\n=== 이름 조회 ===")
print(get_menu_by_name("한우불고기 세트"))

print("\n=== 키워드 검색 ===")
print(search_menu_by_keyword("불고기"))