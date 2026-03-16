#!/usr/bin/env python3
"""
迁移脚本：创建 cleanup_strategies 表
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import text
from app.database import engine, Base
from app.models import CleanupStrategyModel

def migrate():
    print("开始迁移：创建 cleanup_strategies 表...")
    
    # 检查表是否已存在
    with engine.connect() as conn:
        tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        table_names = [t[0] for t in tables]
        
        if 'cleanup_strategies' in table_names:
            print("✓ cleanup_strategies 表已存在，跳过迁移")
            return
    
    # 创建表
    CleanupStrategyModel.__table__.create(engine)
    print("✓ cleanup_strategies 表创建成功")
    
    print("\n迁移完成！")

if __name__ == "__main__":
    migrate()
