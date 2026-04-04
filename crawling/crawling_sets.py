# crawling/crawling_sets.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# 롯데리아 주문 페이지에서 세트 메뉴 정보를 크롤링해서
# data/ria_sets.json 파일로 저장합니다.
#
# 수집 항목:
# - 세트명, 가격, 설명, 이미지 URL
# - 알레르기, 원산지, 열량
# - burger_menu_id (menu 테이블 연결용)
# =====================================================

import time
import json
import sqlite3
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

# menu 테이블에서 버거 이름 → id 매핑 가져오기
conn = sqlite3.connect("data/ria_menu.db")
cursor = conn.cursor()
cursor.execute("SELECT id, name FROM menu WHERE category = '버거'")
menu_map = {name: id for id, name in cursor.fetchall()}
conn.close()

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)

URL = "https://www.lotteeatz.com/qsv/products/10/12198?parentCategoryId=0266&categoryId=02"
driver.get(URL)
time.sleep(3)

sets = []

# 버거 항목 수 확인
items = driver.find_elements(By.CSS_SELECTOR, ".btn-link")
total = len(items)
print(f"버거 항목 {total}개 발견\n")

for i in range(total):
    try:
        # 매번 새로 가져오기 (DOM 갱신 때문에)
        items = driver.find_elements(By.CSS_SELECTOR, ".btn-link")
        driver.execute_script("arguments[0].click();", items[i])
        time.sleep(2)

        # =====================
        # 세트 탭 클릭
        # =====================
        try:
            set_btns = driver.find_elements(By.CSS_SELECTOR, "#menuProductLists .item")
            set_btn = None
            for btn in set_btns:
                if "세트" in btn.text:
                    set_btn = btn
                    break

            if not set_btn:
                print(f"  ⚠️  세트 탭 없음 → 스킵")
                driver.back()
                time.sleep(2)
                continue

            driver.execute_script("arguments[0].click();", set_btn)
            time.sleep(1)
        except:
            print(f"  ⚠️  세트 탭 클릭 실패 → 스킵")
            driver.back()
            time.sleep(2)
            continue

        # =====================
        # 데이터 수집
        # =====================

        # 세트명
        try:
            # 선택된 버튼의 label 텍스트 가져오기
            selected_label = set_btn.find_element(By.CSS_SELECTOR, "label")
            name = selected_label.text.strip().split("\n")[0]  # 가격 제외하고 이름만
        except:
            name = set_btn.find_element(By.CSS_SELECTOR, ".rdo-name").text.strip()

        # 가격
        try:
            price_text = set_btn.find_element(By.CSS_SELECTOR, ".val").text.strip()
            price = int(price_text.replace(",", "").strip())
        except:
            price = 0

        # 설명
        try:
            description = driver.find_element(By.CSS_SELECTOR, ".btext").text.strip()
        except:
            description = ""

        # 이미지 URL
        try:
            img_element = driver.find_element(By.CSS_SELECTOR, ".thumb-img")
            img_url = img_element.value_of_css_property("background-image")
            img_url = img_url.replace('url("', '').replace('")', '').replace("url('", "").replace("')", "")
        except:
            img_url = ""

        # 세트 탭 클릭 후
        driver.execute_script("arguments[0].click();", set_btn)
            
        # time.sleep 대신 명시적 대기
        wait.until(EC.presence_of_element_located(
            (By.ID, "productInfoAllergyContents")
        ))

        # 상세정보 펼치기 부분 전체 삭제하고 이걸로 교체
        time.sleep(1)  # 로딩 대기

        # 알레르기
        try:
            allergy = driver.execute_script(
                "return document.getElementById('productInfoAllergyContents').textContent;"
            )
            allergy = allergy.strip() if allergy else ""
        except:
            allergy = ""

        # 원산지
        try:
            origin = driver.execute_script(
                "return document.getElementById('productInfoOriginContents').textContent;"
            )
            origin = origin.strip() if origin else ""
        except:
            origin = ""

        # 열량
        try:
            calorie = driver.execute_script("""
                var rows = document.querySelectorAll('.tbl-row-info tbody tr');
                for(var i=0; i<rows.length; i++){
                    if(rows[i].querySelector('th') && rows[i].querySelector('th').textContent.includes('열량')){
                        return rows[i].querySelector('td').textContent;
                    }
                }
                return '';
            """)
            calorie = calorie.strip() if calorie else ""
        except:
            calorie = ""

        # burger_menu_id 매칭
        # 세트명에서 "세트" 제거해서 단품명 추출
        burger_name = name.replace(" 세트", "").replace("버거세트", "버거").strip()
        burger_menu_id = menu_map.get(burger_name)

        # 단품명으로 못 찾으면 부분 매칭 시도
        if not burger_menu_id:
            for menu_name, m_id in menu_map.items():
                if menu_name in burger_name or burger_name in menu_name:
                    burger_menu_id = m_id
                    break

        data = {
            "name": name,
            "set_price": price,
            "description": description,
            "img_url": img_url,
            "allergy": allergy,
            "origin": origin,
            "calorie": calorie,
            "burger_menu_id": burger_menu_id
        }

        sets.append(data)
        print(f"  ✅ {name} ({price}원) burger_id:{burger_menu_id}")

        driver.back()
        time.sleep(2)

    except Exception as e:
        print(f"  ❌ {i}번째 항목 실패: {e}")
        try:
            driver.back()
            time.sleep(2)
        except:
            pass

driver.quit()

# JSON 저장
with open("data/ria_sets.json", "w", encoding="utf-8") as f:
    json.dump(sets, f, ensure_ascii=False, indent=2)

print(f"\n✅ 총 {len(sets)}개 세트 크롤링 완료!")
print("📄 data/ria_sets.json 저장됨")

# burger_menu_id null인 것 확인
null_count = sum(1 for s in sets if not s["burger_menu_id"])
if null_count:
    print(f"\n⚠️  burger_menu_id 없는 세트 {null_count}개:")
    for s in sets:
        if not s["burger_menu_id"]:
            print(f"   - {s['name']}")