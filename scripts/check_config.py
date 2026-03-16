import sqlite3
import json

conn = sqlite3.connect('user_study.db')
cursor = conn.cursor()

cursor.execute('SELECT config_json FROM study_configs WHERE is_active = 1 ORDER BY uploaded_at DESC LIMIT 1')
row = cursor.fetchone()

if row:
    config = json.loads(row[0])
    print(f"配置标题: {config.get('title')}")
    print(f"问题数量: {len(config.get('questions', []))}")
else:
    print("没有激活的配置")

conn.close()
