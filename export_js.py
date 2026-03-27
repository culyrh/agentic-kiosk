
import sqlite3
import pandas as pd

conn = sqlite3.connect("ria_menu.db")

df = pd.read_sql_query("SELECT * FROM menu", conn)
df = df.drop(columns=["img_url"])

df.to_json("ria_menu.json", orient="records", force_ascii=False, indent=2)

print("JSON 저장 완료")