# db_setup.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# 현재 ria_menu.db에는 단품 메뉴(menu 테이블)만 있어.
# 이 스크립트를 실행하면 아래 작업을 순서대로 진행해:
#
# 1. 기존 menu 테이블에 컬럼 2개 추가
#    - spicy_level      : 매운맛 단계 (0~3), AI 추천에 활용
#    - is_set_available : 세트 가능 여부 (0=불가, 1=가능)
#
# 2. options 테이블 생성
#    - 세트 구성할 때 고를 수 있는 선택지 목록
#    - 예: 콜라(D01), 사이다(D02), 포테이토(S01) 등
#
# 3. set_menus 테이블 생성
#    - 어떤 버거가 세트로 팔리는지 + 세트 가격
#    - 예: 리아불고기 세트 7,500원
#
# 4. set_options 테이블 생성
#    - 어떤 세트에서 어떤 옵션을 고를 수 있는지 연결
#    - 예: 리아불고기 세트 → 콜라, 사이다, 포테이토 선택 가능
#
# 5. cart 테이블 생성
#    - 사용자가 현재 담아놓은 장바구니 항목
#    - 세트인지 단품인지, 어떤 옵션 골랐는지 저장
#
# 6. orders 테이블 생성
#    - 결제 완료된 최종 주문 내역 저장
#    - 결제 수단, 총 금액, 결제 상태 등
#
# 7. sessions 테이블 생성
#    - 현재 대화 상태 저장 (방식 2 - 백엔드가 상태 관리)
#    - AI가 "그걸로 줘" 같은 표현 처리할 때 활용
#    - 예: last_recommended = "핫크리스피버거"
#
# ※ 이 스크립트는 최초 1번만 실행하면 돼!
#    이미 테이블이 있으면 스킵하고 넘어가니까
#    실수로 두 번 실행해도 괜찮아.
# =====================================================

import sqlite3
import json

conn = sqlite3.connect("ria_menu.db")
cursor = conn.cursor()

# 1. menu 테이블에 컬럼 추가
print("1. menu 테이블 컬럼 추가 중...")
try:
    cursor.execute("ALTER TABLE menu ADD COLUMN spicy_level INTEGER DEFAULT 0")
    print("   spicy_level 추가 완료")
except:
    print("   spicy_level 이미 있음 (스킵)")

try:
    cursor.execute("ALTER TABLE menu ADD COLUMN is_set_available INTEGER DEFAULT 0")
    print("   is_set_available 추가 완료")
except:
    print("   is_set_available 이미 있음 (스킵)")

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
        FOREIGN KEY (burger_menu_id) REFERENCES menu(id)
    )
""")
print("   set_menus 테이블 완료")

# 4. set_options 테이블 생성
print("4. set_options 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS set_options (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        set_id    INTEGER,
        option_id TEXT,
        FOREIGN KEY (set_id) REFERENCES set_menus(set_id),
        FOREIGN KEY (option_id) REFERENCES options(option_id)
    )
""")
print("   set_options 테이블 완료")

# 5. cart 테이블 생성
print("5. cart 테이블 생성 중...")
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

# 6. orders 테이블 생성
print("6. orders 테이블 생성 중...")
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

# 7. sessions 테이블 생성
print("7. sessions 테이블 생성 중...")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id       TEXT PRIMARY KEY,
        current_state    TEXT DEFAULT 'browsing',
        last_recommended TEXT,
        updated_at       TEXT DEFAULT (datetime('now', 'localtime'))
    )
""")
print("   sessions 테이블 완료")

conn.commit()
conn.close()

print("\n✅ 모든 테이블 생성 완료!")