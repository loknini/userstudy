"""
导入真实配置到数据库
"""
import json
import sqlite3
from datetime import datetime

# 读取真实配置
with open('study_config.json', 'r', encoding='utf-8') as f:
    real_config = json.load(f)

print(f"真实配置标题: {real_config.get('title')}")
print(f"真实问题数量: {len(real_config.get('questions', []))}")

# 连接到数据库
conn = sqlite3.connect('user_study.db')
cursor = conn.cursor()

# 先将所有配置设为非激活
cursor.execute('UPDATE study_configs SET is_active = 0')

# 插入真实配置
cursor.execute(
    'INSERT INTO study_configs (config_json, version, uploaded_at, uploaded_by, is_active) VALUES (?, ?, ?, ?, ?)',
    (
        json.dumps(real_config, ensure_ascii=False),
        '2.0',
        datetime.now().isoformat(),
        'admin',
        1
    )
)

conn.commit()
conn.close()

print("\n✅ 真实配置已导入数据库！")
print("请刷新页面查看效果。")
