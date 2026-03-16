"""
数据库结构修复脚本
添加缺少的列
"""
import sqlite3
import os

def fix_database(db_path: str = "user_study.db"):
    """修复数据库结构"""
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 50)
    print("数据库结构修复")
    print("=" * 50)
    
    # 检查 participants 表的列
    print("\n1. 检查 participants 表结构...")
    cursor.execute("PRAGMA table_info(participants)")
    columns = {row[1] for row in cursor.fetchall()}
    print(f"   现有列: {columns}")
    
    # 添加缺少的 completed_at 列
    if 'completed_at' not in columns:
        print("   → 添加 completed_at 列...")
        cursor.execute("ALTER TABLE participants ADD COLUMN completed_at DATETIME")
        print("   ✅ completed_at 列已添加")
    else:
        print("   ✅ completed_at 列已存在")
    
    # 检查 responses 表的列
    print("\n2. 检查 responses 表结构...")
    cursor.execute("PRAGMA table_info(responses)")
    columns = {row[1] for row in cursor.fetchall()}
    print(f"   现有列: {columns}")
    
    # 检查 study_configs 表
    print("\n3. 检查 study_configs 表...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='study_configs'")
    if not cursor.fetchone():
        print("   → 创建 study_configs 表...")
        cursor.execute("""
            CREATE TABLE study_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_json TEXT NOT NULL,
                version VARCHAR(20) DEFAULT '1.0',
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                uploaded_by VARCHAR(50),
                is_active INTEGER DEFAULT 1
            )
        """)
        print("   ✅ study_configs 表已创建")
    else:
        print("   ✅ study_configs 表已存在")
    
    # 检查 audit_logs 表
    print("\n4. 检查 audit_logs 表...")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
    if not cursor.fetchone():
        print("   → 创建 audit_logs 表...")
        cursor.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50),
                entity_id VARCHAR(50),
                details TEXT,
                ip_address VARCHAR(45),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("   ✅ audit_logs 表已创建")
    else:
        print("   ✅ audit_logs 表已存在")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 50)
    print("数据库修复完成！")
    print("=" * 50)
    print("\n请重新启动应用。")
    return True


if __name__ == "__main__":
    import sys
    db_file = sys.argv[1] if len(sys.argv) > 1 else "user_study.db"
    fix_database(db_file)
