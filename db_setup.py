# db_setup.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# ria_menu.db에 필요한 테이블을 생성합니다.
#
# 생성 테이블 목록:
# 1. menu 테이블 컬럼 추가
#    - spicy_level : 매운맛 단계 (0~3), AI 추천에 활용
#
# 2. options 테이블
#    - 세트 구성 선택지 (드링크/사이드/토핑)
#    - option_type: 드링크(D), 사이드(S)
#    - 예: 콜라(D01), 포테이토(S01)
#
# 3. set_menus 테이블
#    - 버거 세트 메뉴 정보
#    - set_price: 단품가격 + 2,000원
#    - burger_menu_id: menu 테이블의 버거 id 참조
#    - calorie: 세트 기준 열량 범위
#
# 4. cart 테이블
#    - 주문 중인 장바구니 항목
#    - is_set: 세트 여부 (0=단품, 1=세트)
#    - 세트인 경우 drink_option, side_option 저장
#
# 5. orders 테이블
#    - 결제 완료된 주문 내역
#    - status: pending → paid
#
# ※ 이미 테이블이 있으면 스킵하므로
#    여러 번 실행해도 괜찮습니다.
# =====================================================

import sqlite3

conn = sqlite3.connect("data/ria_menu.db")
cursor = conn.cursor()

# 1. menu 테이블에 컬럼 추가
print("1. menu 테이블 컬럼 추가 중...")
try:
    cursor.execute("ALTER TABLE menu ADD COLUMN spicy_level INTEGER DEFAULT 0")
    print("   spicy_level 추가 완료")
except:
    print("   spicy_level 이미 있음 (스킵)")

# 2. options 테이블 생성
print("2. options 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS options (
        option_id    TEXT PRIMARY KEY,
        option_type  TEXT,
        menu_id      INTEGER,
        extra_price  INTEGER DEFAULT 0,
        FOREIGN KEY (menu_id) REFERENCES menu(id)
    )
""")
print("   options 테이블 완료")

# 3. set_menus 테이블 생성
print("3. set_menus 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS set_menus (
        set_id         INTEGER PRIMARY KEY AUTOINCREMENT,
        burger_menu_id INTEGER,
        name           TEXT,
        set_price      INTEGER,
        description    TEXT DEFAULT '',
        img_url        TEXT DEFAULT '',
        allergy        TEXT DEFAULT '',
        origin         TEXT DEFAULT '',
        calorie        TEXT DEFAULT '',
        FOREIGN KEY (burger_menu_id) REFERENCES menu(id)
    )
""")
print("   set_menus 테이블 완료")

# 4. cart 테이블 생성
print("4. cart 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        cart_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   TEXT,
        menu_id      INTEGER,
        is_set       INTEGER DEFAULT 0,
        side_option  TEXT,
        drink_option TEXT,
        quantity     INTEGER DEFAULT 1,
        unit_price   INTEGER,
        FOREIGN KEY (menu_id) REFERENCES menu(id)
    )
""")
print("   cart 테이블 완료")

# 5. orders 테이블 생성
print("5. orders 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        order_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id     TEXT,
        total_price    INTEGER,
        payment_method TEXT,
        status         TEXT DEFAULT 'pending',
        created_at     TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
print("   orders 테이블 완료")

# 6. order_items 테이블 생성
print("6. order_items 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS order_items (
        item_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id       INTEGER,
        menu_id        INTEGER,
        quantity       INTEGER,
        unit_price     INTEGER,
        drink_option   TEXT,
        side_option    TEXT,
        FOREIGN KEY (order_id) REFERENCES orders(order_id),
        FOREIGN KEY (menu_id) REFERENCES menu(id)
    )
""")
print("   order_items 테이블 완료")

conn.commit()
conn.close()

print("\n✅ 모든 테이블 생성 완료!")