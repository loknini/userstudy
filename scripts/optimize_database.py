"""
数据库性能优化脚本
- 启用 WAL 模式
- 创建索引
- 分析表
"""
import sqlite3
import os

def optimize_database(db_path: str = "user_study.db"):
    """优化 SQLite 数据库性能"""
    
    if not os.path.exists(db_path):
        print(f"数据库文件不存在: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 50)
    print("数据库性能优化")
    print("=" * 50)
    
    # 1. 启用 WAL 模式
    print("\n1. 启用 WAL 模式...")
    cursor.execute("PRAGMA journal_mode")
    current_mode = cursor.fetchone()[0]
    print(f"   当前模式: {current_mode}")
    
    if current_mode != "wal":
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA journal_mode")
        new_mode = cursor.fetchone()[0]
        print(f"   新模式: {new_mode}")
        print("   ✅ WAL 模式已启用")
    else:
        print("   ✅ WAL 模式已是启用状态")
    
    # 2. 设置同步模式
    print("\n2. 优化同步模式...")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA synchronous")
    sync_mode = cursor.fetchone()[0]
    print(f"   同步模式: {sync_mode}")
    print("   ✅ 同步模式已优化")
    
    # 3. 设置缓存大小
    print("\n3. 设置缓存大小...")
    cursor.execute("PRAGMA cache_size=-100000")  # 100MB
    cursor.execute("PRAGMA cache_size")
    cache_size = cursor.fetchone()[0]
    print(f"   缓存大小: {abs(cache_size)} 页 ({abs(cache_size) * 4 / 1024:.1f} MB)")
    print("   ✅ 缓存已优化")
    
    # 4. 创建额外索引
    print("\n4. 检查并创建索引...")
    
    # 获取现有索引
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing_indexes = {row[0] for row in cursor.fetchall()}
    
    indexes_to_create = [
        ("idx_responses_participant", "CREATE INDEX IF NOT EXISTS idx_responses_participant ON responses(participant_id)"),
        ("idx_responses_question", "CREATE INDEX IF NOT EXISTS idx_responses_question ON responses(question_id)"),
        ("idx_responses_created", "CREATE INDEX IF NOT EXISTS idx_responses_created ON responses(created_at)"),
        ("idx_participants_started", "CREATE INDEX IF NOT EXISTS idx_participants_started ON participants(started_at)"),
        ("idx_study_configs_active", "CREATE INDEX IF NOT EXISTS idx_study_configs_active ON study_configs(is_active, uploaded_at)"),
    ]
    
    for idx_name, create_sql in indexes_to_create:
        if idx_name in existing_indexes:
            print(f"   - {idx_name}: 已存在")
        else:
            cursor.execute(create_sql)
            print(f"   - {idx_name}: 已创建")
    
    print("   ✅ 索引检查完成")
    
    # 5. 分析表（优化查询计划）
    print("\n5. 分析表统计信息...")
    cursor.execute("ANALYZE")
    print("   ✅ 表分析完成")
    
    # 6. 显示数据库状态
    print("\n6. 数据库状态:")
    cursor.execute("SELECT COUNT(*) FROM participants")
    participant_count = cursor.fetchone()[0]
    print(f"   - 参与者数量: {participant_count}")
    
    cursor.execute("SELECT COUNT(*) FROM responses")
    response_count = cursor.fetchone()[0]
    print(f"   - 响应数量: {response_count}")
    
    cursor.execute("PRAGMA page_count")
    page_count = cursor.fetchone()[0]
    cursor.execute("PRAGMA page_size")
    page_size = cursor.fetchone()[0]
    db_size_mb = (page_count * page_size) / (1024 * 1024)
    print(f"   - 数据库大小: {db_size_mb:.2f} MB")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 50)
    print("数据库优化完成！")
    print("=" * 50)
    print("\n优化项目:")
    print("  ✅ WAL 模式（提升并发性能）")
    print("  ✅ 同步模式 NORMAL（平衡安全与性能）")
    print("  ✅ 100MB 缓存")
    print("  ✅ 查询索引")
    print("  ✅ 表统计信息分析")


if __name__ == "__main__":
    import sys
    
    db_file = sys.argv[1] if len(sys.argv) > 1 else "user_study.db"
    optimize_database(db_file)
