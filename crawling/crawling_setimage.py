# crawling/crawling_setimage.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# lotteeatz.com/products/introductions 페이지에서
# 각 버거의 세트 이미지 URL을 크롤링해서
# data/ria_sets.json에 img_url을 업데이트합니다.
# =====================================================

import json
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ria_sets.json 로드
with open("data/ria_sets.json", encoding="utf-8") as f:
    sets = json.load(f)

# ria_menu.json에서 버거 id → 상품 페이지 URL 가져오기
# products/introductions 페이지 URL 패턴 파악 필요
# brand/ria 페이지에서 버거 링크 수집

driver = webdriver.Chrome()
wait = WebDriverWait(driver, 10)

driver.get("https://www.lotteeatz.com/brand/ria")
time.sleep(3)

# 버거 탭 클릭
tabs = driver.find_elements(By.CSS_SELECTOR, "#categoryList .tab-item")
for tab in tabs:
    if "버거" in tab.text:
        driver.execute_script("arguments[0].click();", tab)
        time.sleep(2)
        break

# 세트명 → index 딕셔너리
set_map = {s["name"]: i for i, s in enumerate(sets)}

items = driver.find_elements(By.CSS_SELECTOR, ".prod-tit")
total = len(items)
print(f"버거 항목 {total}개 발견\n")

success = 0
fail = 0

for j in range(total):
    try:
        elements = driver.find_elements(By.CSS_SELECTOR, ".btn-link")
        driver.execute_script("arguments[0].click();", elements[j])
        time.sleep(2)

        # 연관상품 목록에서 세트 찾기
        opt_items = driver.find_elements(By.CSS_SELECTOR, ".ui-col-list .item")

        for item in opt_items:
            try:
                # 세트명 확인
                opt_name = item.find_element(By.CSS_SELECTOR, ".opt-name").text.strip()

                if "세트" not in opt_name:
                    continue

                # 이미지 URL 가져오기
                opt_img = item.find_element(By.CSS_SELECTOR, ".opt-img")
                bg = opt_img.value_of_css_property("background-image")
                img_url = bg.replace('url("', '').replace('")', '').replace("url('", "").replace("')", "")

                # JSON에서 매칭
                if opt_name in set_map:
                    idx = set_map[opt_name]
                    sets[idx]["img_url"] = img_url
                    print(f"  ✅ {opt_name}")
                    success += 1
                else:
                    print(f"  ⚠️  {opt_name} → JSON 매칭 실패")
                    fail += 1

            except Exception as e:
                continue

        driver.back()
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".btn-link")))

    except Exception as e:
        print(f"  ❌ {j}번째 실패: {e}")
        try:
            driver.back()
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".btn-link")))
        except:
            pass

driver.quit()

# JSON 저장
with open("data/ria_sets.json", "w", encoding="utf-8") as f:
    json.dump(sets, f, ensure_ascii=False, indent=2)

print(f"\n✅ 완료! 성공: {success}개, 실패: {fail}개")
print("📄 data/ria_sets.json 저장됨")