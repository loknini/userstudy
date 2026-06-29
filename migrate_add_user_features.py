"""添加更多用户特征字段的数据库迁移脚本

运行方式：
    python migrate_add_user_features.py
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import engine, Base, SessionLocal
from sqlalchemy import text


def migrate():
    """执行数据库迁移"""
    print("开始迁移：添加更多用户特征字段...")

    db = SessionLocal()
    try:
        # 检查 participant 表是否存在
        result = db.execute(text(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='participants'"
        ))

        if not result.fetchone():
            print("[SKIP] participants 表不存在，跳过迁移")
            return

        # 获取当前表的列
        result = db.execute(text("PRAGMA table_info(participants)"))
        columns = [row[1] for row in result.fetchall()]

        print(f"   当前 participants 表字段：{columns}")

        # 需要添加的字段
        new_columns = [
            ("screen_resolution", "VARCHAR(20)"),
            ("language", "VARCHAR(10)"),
            ("timezone", "VARCHAR(50)"),
            ("platform", "VARCHAR(50)"),
            ("cookies_enabled", "VARCHAR(10)"),
            ("do_not_track", "VARCHAR(10)"),
        ]

        # 逐个添加字段
        added = 0
        skipped = 0
        for col_name, col_type in new_columns:
            if col_name not in columns:
                try:
                    db.execute(text(
                        f"ALTER TABLE participants "
                        f"ADD COLUMN {col_name} {col_type}"
                    ))
                    print(f"   [OK] 添加字段：{col_name}")
                    added += 1
                except Exception as e:
                    print(f"   [FAIL] 添加字段失败 {col_name}: {e}")
                    raise
            else:
                print(f"   [SKIP] 字段已存在，跳过：{col_name}")
                skipped += 1

        db.commit()
        print(f"[DONE] 迁移完成！新增 {added} 个字段，跳过 {skipped} 个")

    except Exception as e:
        db.rollback()
        print(f"[FAIL] 迁移失败：{e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
