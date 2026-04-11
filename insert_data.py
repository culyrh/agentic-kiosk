# insert_data.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# 1. 기존 테이블 데이터 전체 삭제
# 2. ria_menu.json → menu 테이블 삽입
#    - id: 카테고리별 100번대 (버거:101~, 디저트:201~, ...)
#    - badge: 배열 형태 JSON (예: ["NEW", "BEST"])
#    - nutrition: 딕셔너리 형태 JSON
#    - spicy_level: 매운맛 단계 (0~3)
# 3. ria_options.json → options 테이블 삽입
#    - 드링크(D), 사이드(S), 토핑(T) 구분
# 4. ria_sets.json → set_menus 삽입
#    - burger_menu_id: menu 테이블과 연결
#    - set_price: 단품가격 + 2,000원
#    - 토핑 옵션은 set_options에서 제외
# 5. set_options 연결 (드링크/사이드만)
#
# ※ 실행 전 크롤링이 완료되어 있어야 합니다:
#    python crawling/crawling_set.py     (세트 정보)
#    python crawling/crawling_setimage.py (세트 이미지)
#
# ※ 여러 번 실행해도 괜찮습니다.
#    실행할 때마다 기존 데이터를 삭제하고 새로 삽입합니다.
# =====================================================

import sqlite3
import json

conn = sqlite3.connect("data/ria_menu.db")
cursor = conn.cursor()

# =====================================================
# 1. 기존 데이터 전체 삭제
# =====================================================
print("1. 기존 데이터 전체 삭제 중...")
cursor.execute("DELETE FROM set_options")
cursor.execute("DELETE FROM set_menus")
cursor.execute("DELETE FROM options")
cursor.execute("DELETE FROM menu")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='set_menus'")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='set_options'")
print("   삭제 완료")

# =====================================================
# 2. ria_menu.json → menu 테이블 삽입
# =====================================================
print("\n2. menu 테이블 데이터 삽입 중...")

with open("data/ria_menu.json", encoding="utf-8") as f:
    menus = json.load(f)

for m in menus:
    try:
        cursor.execute("""
            INSERT INTO menu (id, category, name, badge, price, description, img_url, allergy, origin, nutrition, spicy_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            m["id"],
            m["category"],
            m["name"],
            json.dumps(m.get("badge", []), ensure_ascii=False),
            m["price"],
            m.get("description", ""),
            m.get("img_url", ""),
            m.get("allergy", ""),
            m.get("origin", ""),
            json.dumps(m.get("nutrition", {}), ensure_ascii=False),
            m.get("spicy_level", 0),
        ))
        print(f"   ✅ {m['id']} - {m['name']}")
    except Exception as e:
        print(f"   ❌ {m['name']} 실패: {e}")

# =====================================================
# 3. ria_options.json → options 테이블 삽입
# =====================================================
print("\n3. options 테이블 데이터 삽입 중...")

with open("data/ria_options.json", encoding="utf-8") as f:
    options = json.load(f)

for o in options:
    try:
        cursor.execute("""
            INSERT INTO options (option_id, option_type, menu_id, extra_price)
            VALUES (?, ?, ?, ?)
        """, (
            o["option_id"],
            o["option_type"],
            o["menu_id"],
            o["extra_price"]
        ))
        print(f"   ✅ {o['option_id']} - {o['name']}")
    except sqlite3.IntegrityError:
        print(f"   ⚠️  {o['option_id']} 이미 존재 (스킵)")

# =====================================================
# 4. ria_sets.json → set_menus 삽입
# =====================================================
print("\n4. set_menus 테이블 데이터 삽입 중...")

with open("data/ria_sets.json", encoding="utf-8") as f:
    sets = json.load(f)

# 토핑 제외한 옵션만 세트에 연결
all_option_ids = [o["option_id"] for o in options if o["option_type"] != "토핑"]
inserted_sets = []

for s in sets:
    if s["burger_menu_id"] is None:
        print(f"   ⚠️  {s['name']} → burger_menu_id 없음 (스킵)")
        continue
    try:
        cursor.execute("""
            INSERT INTO set_menus (burger_menu_id, name, set_price, description, img_url, allergy, origin, calorie)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["burger_menu_id"],
            s["name"],
            s.get("set_price", ""),
            s.get("description", ""),
            s.get("img_url", ""),
            s.get("allergy", ""),
            s.get("origin", ""),
            s.get("calorie", "")
        ))
        set_id = cursor.lastrowid
        inserted_sets.append(set_id)
        print(f"   ✅ {s['name']} (set_id: {set_id})")
    except Exception as e:
        print(f"   ❌ {s['name']} 실패: {e}")

# =====================================================
# 5. set_options 연결 (드링크/사이드만, 토핑 제외)
# =====================================================
print("\n5. set_options 연결 중...")
for set_id in inserted_sets:
    for option_id in all_option_ids:
        try:
            cursor.execute("""
                INSERT INTO set_options (set_id, option_id) VALUES (?, ?)
            """, (set_id, option_id))
        except Exception as e:
            print(f"   ❌ set_id:{set_id} - {option_id} 실패: {e}")
print(f"   ✅ {len(inserted_sets)}개 세트에 옵션 연결 완료")

# =====================================================
# 저장 및 결과 확인
# =====================================================
conn.commit()

print("\n===== 최종 결과 =====")
cursor.execute("SELECT COUNT(*) FROM menu")
print(f"menu 테이블:        {cursor.fetchone()[0]}개")
cursor.execute("SELECT COUNT(*) FROM options")
print(f"options 테이블:     {cursor.fetchone()[0]}개")
cursor.execute("SELECT COUNT(*) FROM set_menus")
print(f"set_menus 테이블:   {cursor.fetchone()[0]}개")
cursor.execute("SELECT COUNT(*) FROM set_options")
print(f"set_options 테이블: {cursor.fetchone()[0]}개")

conn.close()
print("\n✅ 모든 데이터 삽입 완료!")