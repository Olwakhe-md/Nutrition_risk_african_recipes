import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = Path("nutrition.db")
food_nutrient = Path(r"C:\Users\mdumiseni\Documents\data science assignements\data-science-portfolio\nutrition-risk-african-recipes\data_clean\food_nutrient.csv")
nutrient = Path(r"C:\Users\mdumiseni\Documents\data science assignements\data-science-portfolio\nutrition-risk-african-recipes\data_clean\nutrient.csv")

conn = sqlite3.connect(DB_PATH)

food_nutrient = pd.read_csv(food_nutrient)
nutrient = pd.read_csv(nutrient)

food_nutrient.to_sql("food_nutrient", conn, if_exists = "replace", index = False)
nutrient.to_sql("nutrient", conn, if_exists = "replace", index= False)

for table in ["food_nutrient", "nutrient"]:
    count = pd.read_sql_query(f"SELECT COUNT(*) as n FROM {table}", conn)
    print(table)
    print(count)
    print()

conn.close()
print("Done")
