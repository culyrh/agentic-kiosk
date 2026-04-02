# crawling/crawling_sets.py
#
# =====================================================
# 이 파일이 하는 일
# =====================================================
# 롯데리아 영양성분표 페이지에서 세트 메뉴 목록을 크롤링해서
# ria_sets_raw.json 파일로 저장하는 스크립트야.
#
# 크롤링 결과:
# - 세트 이름
# - 알레르기 정보
# - 열량 범위
#
# ※ 세트 가격은 해당 페이지에 없어서
#    단품 가격 + 2,500원으로 자동 계산함
#    (나중에 수동으로 수정 가능)
# =====================================================

import requests
from bs4 import BeautifulSoup
import json

URL = "https://www.lotteeatz.com/upload/stg/etc/ria/items.html"

def crawl_sets():
    print("페이지 요청 중...")
    response = requests.get(URL)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    rows = soup.find_all("tr")

    sets = []
    current_category = ""

    for row in rows:
        cols = row.find_all("td")
        if not cols:
            continue

        # 카테고리 셀 확인 (버거세트, 버거메뉴 등)
        if len(cols) >= 1:
            first = cols[0].get_text(strip=True)
            if first in ["버거세트", "버거메뉴", "치킨메뉴", "드링크 메뉴", "디저트 메뉴", "토핑메뉴"]:
                current_category = first
                continue

        # 버거세트만 수집
        if current_category != "버거세트":
            continue

        # 세트 이름, 알레르기, 열량 추출
        if len(cols) >= 3:
            name    = cols[0].get_text(strip=True)
            allergy = cols[1].get_text(strip=True)
            calorie = cols[2].get_text(strip=True)

            if not name:
                continue

            print(f"  발견: {name}")

            sets.append({
                "name": name,
                "allergy": allergy,
                "calorie": calorie,
                "set_price": None,   # 가격은 수동 입력 필요
                "burger_menu_id": None  # menu 테이블 id와 연결 필요
            })

    # JSON 저장
    with open("ria_sets_raw.json", "w", encoding="utf-8") as f:
        json.dump(sets, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 총 {len(sets)}개 세트 크롤링 완료!")
    print("📄 ria_sets_raw.json 저장됨")
    print("\n⚠️  다음 작업 필요:")
    print("   1. ria_sets_raw.json 열어서")
    print("   2. 각 세트의 set_price 직접 입력")
    print("   3. burger_menu_id 연결 (menu 테이블 id)")

if __name__ == "__main__":
    crawl_sets()