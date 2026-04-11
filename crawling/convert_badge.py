# convert_spicy.py
import json

with open("data/ria_menu.json", encoding="utf-8") as f:
    menus = json.load(f)

for m in menus:
    if "spicy_level" not in m:
        m["spicy_level"] = 0

with open("data/ria_menu.json", "w", encoding="utf-8") as f:
    json.dump(menus, f, ensure_ascii=False, indent=2)

print("✅ 완료!")