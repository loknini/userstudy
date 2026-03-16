#!/usr/bin/env python3
"""检查数据库表结构"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # 获取所有表
    tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    print("现有表：", [t[0] for t in tables])
    
    # 检查studies表结构
    if 'studies' in [t[0] for t in tables]:
        print('\nStudies表结构：')
        cols = conn.execute(text("PRAGMA table_info(studies)")).fetchall()
        for col in cols:
            print(f'  {col[1]}: {col[2]}')
    
    # 检查participants表结构
    if 'participants' in [t[0] for t in tables]:
        print('\nParticipants表结构：')
        cols = conn.execute(text("PRAGMA table_info(participants)")).fetchall()
        for col in cols:
            print(f'  {col[1]}: {col[2]}')
