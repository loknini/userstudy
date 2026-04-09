"""
添加 random_seed 列到 participants 表的迁移脚本
"""
import sqlite3
import hashlib
import time
from pathlib import Path


def migrate_add_random_seed():
    """为现有参与者添加 random_seed 列"""
    db_path = Path(__file__).parent.parent / "user_study.db"
    
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查 random_seed 列是否已存在
        cursor.execute("PRAGMA table_info(participants)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'random_seed' in columns:
            print("random_seed 列已存在，无需迁移")
            return
        
        # 添加 random_seed 列
        print("添加 random_seed 列...")
        cursor.execute("ALTER TABLE participants ADD COLUMN random_seed INTEGER")
        
        # 为现有参与者生成随机种子
        print("为现有参与者生成随机种子...")
        cursor.execute("SELECT id FROM participants")
        participants = cursor.fetchall()
        
        for (participant_id,) in participants:
            # 使用参与者ID生成固定的随机种子
            seed_str = f"{participant_id}"
            seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**31)
            cursor.execute(
                "UPDATE participants SET random_seed = ? WHERE id = ?",
                (seed, participant_id)
            )
        
        conn.commit()
        print(f"成功为 {len(participants)} 个参与者添加了随机种子")
        
    except Exception as e:
        print(f"迁移失败: {e}")
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_random_seed()
