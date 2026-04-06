import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

NUTRITION_URL = "https://www.lotteeatz.com/upload/stg/etc/ria/items.html"
OUT_PATH = Path("data/menu.json")

ALLERGEN_KEYS = [
    "달걀", "밀", "대두", "우유", "쇠고기", "닭고기", "토마토",
    "아황산류", "복숭아", "새우", "돼지고기", "조개류", "오징어",
    "땅콩", "게"
]


def normalize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    name = name.replace("NEW ", "").replace("New ", "")
    return name


def infer_category(name: str) -> str:
    if "세트" in name:
        return "set"
    if any(x in name for x in ["버거", "불고기", "새우", "라이스"]):
        return "burger"
    if any(x in name for x in ["콜라", "에이드", "커피"]):
        return "drink"
    return "unknown"


def infer_set_available(name: str, category: str) -> bool:
    return category == "burger"


def infer_spicy_level(name: str) -> int:
    spicy_keywords = ["핫", "매운", "파이어", "청양", "김치"]
    return 2 if any(k in name for k in spicy_keywords) else 0


def extract_allergens(text: str) -> list[str]:
    return [key for key in ALLERGEN_KEYS if key in text]


def extract_kcal_from_cells(cells: list[str]) -> int | None:
    # 1) "684kcal ~ 1,370kcal" 같은 셀
    for cell in cells:
        m = re.search(r"(\d[\d,]*)\s*kcal", cell, flags=re.IGNORECASE)
        if m:
            return int(m.group(1).replace(",", ""))

    # 2) 버거메뉴처럼 숫자 열이 따로 떨어진 경우:
    # 예: [구분, 제품명, 알레르기, 263, 572, 23(43%), ...]
    # 보통 중량 다음 값이 kcal
    numeric_cells = []
    for cell in cells:
        cell_clean = cell.replace(",", "").strip()
        if re.fullmatch(r"\d{2,4}", cell_clean):
            numeric_cells.append(int(cell_clean))

    if len(numeric_cells) >= 2:
        return numeric_cells[1]

    return None


def extract_origin(cells: list[str]) -> str:
    keywords = ["국내산", "호주산", "브라질산", "외국산", "페루산", "중국산"]
    for cell in reversed(cells):
        if any(k in cell for k in keywords):
            return cell.strip()
    return ""


def parse_row(cells: list[str]) -> dict | None:
    if len(cells) < 3:
        return None

    section = cells[0].strip()
    name = normalize_name(cells[1])
    allergens_text = cells[2].strip()

    valid_sections = ["버거세트", "버거메뉴", "치킨", "디저트", "음료", "콤보", "팩"]
    if not any(keyword in section for keyword in ["버거", "세트", "치킨", "디저트", "음료", "콤보", "팩"]):
        return None

    if not name or name == "제품명":
        return None

    allergens = extract_allergens(allergens_text)
    kcal = extract_kcal_from_cells(cells)
    category = infer_category(name)

    return {
        "name": name,
        "category": category,
        "price": None,
        "description": "",
        "image_url": "",
        "is_set_available": infer_set_available(name, category),
        "spicy_level": infer_spicy_level(name),
        "allergens": allergens,
        "kcal": kcal,
        "origin_text": extract_origin(cells),
        "raw_source": "nutrition_page"
    }


def deduplicate(items: list[dict]) -> list[dict]:
    seen = {}
    for item in items:
        if item["name"] not in seen:
            seen[item["name"]] = item
    return list(seen.values())


def crawl_nutrition_page() -> list[dict]:
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(NUTRITION_URL, headers=headers, timeout=20)
    res.raise_for_status()

    print("status_code:", res.status_code)
    print("encoding before:", res.encoding)
    print("apparent_encoding:", res.apparent_encoding)

    res.encoding = res.apparent_encoding

    print("encoding after:", res.encoding)

    soup = BeautifulSoup(res.text, "html.parser")

    rows = soup.select("tr")
    print("total tr rows:", len(rows))

    items = []

    for row in rows:
        cols = row.select("th, td")
        cells = [col.get_text(" ", strip=True) for col in cols if col.get_text(" ", strip=True)]

        if cells:
            parsed = parse_row(cells)
            if parsed:
                items.append(parsed)

    items = deduplicate(items)


    print("parsed items:", len(items))
    if items:
        print("first item:", items[0])

    return items


def main():
    items = crawl_nutrition_page()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"saved {len(items)} items to {OUT_PATH}")


if __name__ == "__main__":
    main()