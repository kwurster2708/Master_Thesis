import sqlite3
import pandas as pd

conn = sqlite3.connect(r"\Users\Kim_W\Ekkono_Code\WeatherData.sqlite")
df = pd.read_sql("SELECT * FROM mytable", conn) #just add the information that is needed for the dashboard
df.to_parquet("Database.parquet")