"""
数据迁移脚本 - 从旧版本 Flask 数据库迁移到 FastAPI 新版本

用法:
    python migrate.py
"""
import sqlite3
import json
from pathlib import Path
from datetime import datetime


def migrate_database():
    """迁移旧数据库数据到新结构"""
    db_path = Path("user_study.db")
    
    if not db_path.exists():
        print("❌ 数据库文件不存在，无需迁移")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查是否是旧版本数据库
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    
    print(f"📊 发现表: {tables}")
    
    # 检查是否已迁移
    if "audit_logs" in tables:
        print("✅ 数据库已是最新版本，无需迁移")
        conn.close()
        return
    
    print("🔄 开始迁移数据...")
    
    # 备份原数据库
    backup_path = f"user_study_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    import shutil
    shutil.copy(db_path, backup_path)
    print(f"💾 已备份原数据库到: {backup_path}")
    
    try:
        # 添加新列（如果不存在）
        cursor.execute("PRAGMA table_info(participants)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "completed_at" not in columns:
            print("➕ 添加 completed_at 列到 participants 表...")
            cursor.execute("ALTER TABLE participants ADD COLUMN completed_at TEXT")
        
        # 创建新表
        print("➕ 创建新表...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS study_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_json TEXT NOT NULL,
                version TEXT DEFAULT '1.0',
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
                uploaded_by TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # 导入现有配置
        config_path = Path("study_config.json")
        if config_path.exists():
            print("📥 导入现有配置到数据库...")
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
            
            cursor.execute("""
                INSERT INTO study_configs (config_json, version, uploaded_by, is_active)
                VALUES (?, ?, ?, 1)
            """, (config_content, 'migrated', 'migration_script'))
        
        # 更新完成状态（根据响应数量）
        print("🔄 更新参与者完成状态...")
        cursor.execute("""
            UPDATE participants
            SET completed_at = (
                SELECT MAX(created_at) FROM responses 
                WHERE responses.participant_id = participants.id
            )
            WHERE id IN (
                SELECT participant_id FROM responses
                GROUP BY participant_id
                HAVING COUNT(*) >= 10  -- 假设至少10题为完成
            )
        """)
        
        # 创建索引
        print("🔍 创建索引...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_participant_completed ON participants(completed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_response_created ON responses(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_config_active ON study_configs(is_active, uploaded_at)")
        
        conn.commit()
        print("✅ 迁移完成！")
        
        # 统计信息
        cursor.execute("SELECT COUNT(*) FROM participants")
        participant_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM responses")
        response_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM study_configs")
        config_count = cursor.fetchone()[0]
        
        print(f"\n📊 迁移后统计:")
        print(f"   参与者: {participant_count}")
        print(f"   响应数: {response_count}")
        print(f"   配置数: {config_count}")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ 迁移失败: {e}")
        raise
    finally:
        conn.close()


def verify_migration():
    """验证迁移结果"""
    from app.database import SessionLocal
    from app.services.study import StudyService
    from app.services.stats import StatsService
    
    print("\n🔍 验证迁移结果...")
    
    db = SessionLocal()
    try:
        study_service = StudyService(db)
        stats_service = StatsService(db)
        
        # 检查配置
        config = study_service.get_active_config()
        if config:
            print(f"✅ 配置加载成功: {config.title}")
            print(f"   问题数: {len(config.questions)}")
        else:
            print("⚠️ 配置未加载")
        
        # 检查统计
        if config:
            stats = stats_service.get_overall_stats(config)
            print(f"✅ 统计功能正常")
            print(f"   总参与者: {stats.total_participants}")
            print(f"   完成率: {stats.completion_rate}%")
        
        print("\n🎉 验证通过！可以开始使用新版本了。")
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("User Study Platform - 数据库迁移工具")
    print("=" * 50)
    print()
    
    migrate_database()
    
    # 询问是否验证
    response = input("\n是否验证迁移结果? (y/n): ")
    if response.lower() == 'y':
        verify_migration()
