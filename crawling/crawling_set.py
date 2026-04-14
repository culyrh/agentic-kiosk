# crawling/crawling_set.py
import json
import sqlite3
import requests
from bs4 import BeautifulSoup

URL = "https://www.lotteeatz.com/upload/stg/etc/ria/items.html"

# ria_menu.json에서 버거 이름 → id 매핑
with open("data/ria_menu.json", encoding="utf-8") as f:
    menus = json.load(f)
burgers = {m["name"]: m["id"] for m in menus if m["category"] == "버거"}

# 세트명 → 버거명 매핑
name_map = {
    "한우불고기 세트":                       "한우불고기버거",
    "더블 한우불고기 세트":                  "더블 한우불고기버거",
    "리아 불고기 세트":                      "리아 불고기",
    "리아 불고기 더블 세트":                 "리아 불고기 더블(빅불)",
    "리아 새우 세트":                        "리아 새우",
    "리아 사각새우 더블 세트":               "리아 사각새우 더블",
    "모짜렐라인더버거 베이컨 세트":          "모짜렐라 인 더 버거 베이컨",
    "더블엑스투버거 세트":                   "더블엑스투버거",
    "핫크리스피치킨버거 세트":               "핫크리스피치킨버거",
    "NEW 미라클버거 세트":                   "NEW 미라클버거",
    "NEW 더블 미라클버거 세트":              "NEW 더블 미라클버거",
    "클래식치즈버거 세트":                   "클래식치즈버거(버터번)",
    "더블 클래식치즈버거 세트":              "더블 클래식치즈버거(버터번)",
    "치킨버거 세트":                         "치킨버거",
    "더블 치킨버거 세트":                    "더블 치킨버거",
    "치킨버거 세트 (N)":                     "치킨버거(N)",
    "더블 치킨버거 세트 (N)":               "더블 치킨버거(N)",
    "데리버거 세트":                         "데리버거",
    "더블 데리버거 세트":                    "더블 데리버거",
    "모짜렐라버거세트 토마토바질 세트":      "모짜렐라버거 토마토바질",
    "모짜렐라버거세트 발사믹바질 세트":      "모짜렐라버거 발사믹바질",
    "통다리 크리스피치킨버거세트(그릭랜치)": "통다리 크리스피치킨버거(그릭랜치)",
    "통다리 크리스피치킨버거세트(파이어핫)": "통다리 크리스피치킨버거(파이어핫)",
}

# 크롤링
print("페이지 로딩 중...")
response = requests.get(URL)
response.encoding = "utf-8"
soup = BeautifulSoup(response.text, "html.parser")

sets = []
tbody = soup.find("tbody")
rows = tbody.find_all("tr")
current_category = ""

for row in rows:
    th = row.find("th")
    if th:
        current_category = th.text.strip()

    if current_category != "버거세트":
        continue

    tds = row.find_all("td")
    if len(tds) < 3:
        continue

    name    = tds[0].text.strip()
    allergy = tds[1].text.strip()
    calorie = tds[2].text.strip()
    origin  = tds[-1].text.strip()

    # burger_menu_id 매칭
    burger_name = name_map.get(name)
    burger_menu_id = burgers.get(burger_name) if burger_name else None

    if not burger_menu_id:
        print(f"  ⚠️  {name} → menu에 없음 (스킵)")
        continue

    # 단품 가격 가져와서 +2000
    burger_price_str = next(m["price"] for m in menus if m["id"] == burger_menu_id)
    burger_price = int(burger_price_str.replace(",", ""))
    set_price = f"{burger_price + 2000:,}"

    sets.append({
        "name":           name,
        "burger_menu_id": burger_menu_id,
        "set_price":      set_price,
        "img_url":        "",
        "description":    "",
        "allergy":        allergy,
        "origin":         origin,
        "calorie":        calorie,
    })
    print(f"  ✅ {name} | burger_id:{burger_menu_id}")

print(f"\n총 {len(sets)}개 크롤링 완료!")

# DB 저장
conn = sqlite3.connect("data/ria_menu.db")
cursor = conn.cursor()

print("\n기존 set_menus 삭제 중...")
cursor.execute("DELETE FROM set_options")
cursor.execute("DELETE FROM set_menus")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='set_menus'")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='set_options'")
print("   삭제 완료")

new_columns = [
    ("description", "TEXT DEFAULT ''"),
    ("img_url",     "TEXT DEFAULT ''"),
    ("allergy",     "TEXT DEFAULT ''"),
    ("origin",      "TEXT DEFAULT ''"),
    ("calorie",     "TEXT DEFAULT ''"),
]
for col_name, col_type in new_columns:
    try:
        cursor.execute(f"ALTER TABLE set_menus ADD COLUMN {col_name} {col_type}")
    except:
        pass

print("\nset_menus 삽입 중...")
inserted_sets = []

for s in sets:
    try:
        cursor.execute("""
            INSERT INTO set_menus (burger_menu_id, name, set_price, description, img_url, allergy, origin, calorie)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["burger_menu_id"],
            s["name"],
            s["set_price"],
            s["description"],
            s["img_url"],
            s["allergy"],
            s["origin"],
            s["calorie"],
        ))
        set_id = cursor.lastrowid
        s["set_id"] = set_id  # set_id도 저장
        inserted_sets.append(set_id)
        print(f"   ✅ {s['name']} (set_id:{set_id}, burger_id:{s['burger_menu_id']})")
    except Exception as e:
        print(f"   ❌ {s['name']} 실패: {e}")

# set_options 연결 (드링크/사이드만)
print("\nset_options 연결 중...")
cursor.execute("SELECT option_id, option_type FROM options")
all_options = cursor.fetchall()
option_ids = [o[0] for o in all_options if o[1] != "토핑"]

for set_id in inserted_sets:
    for option_id in option_ids:
        try:
            cursor.execute("INSERT INTO set_options (set_id, option_id) VALUES (?, ?)", (set_id, option_id))
        except:
            pass

print(f"   ✅ {len(inserted_sets)}개 세트에 옵션 연결 완료")

conn.commit()
conn.close()

# JSON 저장 (set_id 포함)
with open("data/ria_sets.json", "w", encoding="utf-8") as f:
    json.dump(sets, f, ensure_ascii=False, indent=2)
print("\n📄 data/ria_sets.json 저장됨")

print("\n===== 최종 결과 =====")
conn = sqlite3.connect("data/ria_menu.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM set_menus")
print(f"set_menus 테이블: {cursor.fetchone()[0]}개")
cursor.execute("SELECT COUNT(*) FROM set_options")
print(f"set_options 테이블: {cursor.fetchone()[0]}개")
conn.close()
print("\n✅ 완료!")