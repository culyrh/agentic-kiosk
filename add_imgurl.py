# add_imgurl.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# 원래 DB(ria_menu44.db)에서 메뉴 이름과 img_url을 가져와서
# 현재 ria_menu.json에 img_url을 추가해줍니다.
#
# 이름이 일치하는 메뉴에만 img_url이 추가되고
# 없는 메뉴는 빈 문자열로 유지됩니다.
# =====================================================

import sqlite3
import json

# 원래 DB에서 이름 → img_url 매핑 가져오기
print("1. 원래 DB에서 img_url 가져오는 중...")
conn = sqlite3.connect("ria_menu44.db")
cursor = conn.cursor()
cursor.execute("SELECT name, img_url FROM menu")
rows = cursor.fetchall()
conn.close()

# 이름 → img_url 딕셔너리 생성
img_map = {}
for name, img_url in rows:
    if img_url:
        img_map[name] = img_url

print(f"   img_url 있는 메뉴: {len(img_map)}개")

# ria_menu.json 읽기
print("\n2. ria_menu.json에 img_url 추가 중...")
with open("ria_menu.json", encoding="utf-8") as f:
    menus = json.load(f)

matched = 0
unmatched = []

for menu in menus:
    if menu["name"] in img_map:
        menu["img_url"] = img_map[menu["name"]]
        matched += 1
    else:
        if "img_url" not in menu:
            menu["img_url"] = ""
        unmatched.append(menu["name"])

# 저장
with open("ria_menu.json", "w", encoding="utf-8") as f:
    json.dump(menus, f, ensure_ascii=False, indent=2)

print(f"   매칭 성공: {matched}개")
print(f"   매칭 실패 (img_url 없음): {len(unmatched)}개")
if unmatched:
    print("   매칭 실패 목록:")
    for name in unmatched:
        print(f"     - {name}")

print("\n✅ img_url 추가 완료!")
print("※ insert_data.py 다시 실행해서 DB에 반영하세요.")