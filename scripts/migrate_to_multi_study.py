#!/usr/bin/env python3
"""
数据库迁移脚本：单问卷 → 多问卷系统

迁移步骤：
1. 确保 studies 表结构正确
2. 为 participants 表添加 study_id 列
3. 创建默认问卷
4. 迁移现有参与者数据
5. 验证迁移结果
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text, Column, String, ForeignKey
from sqlalchemy.orm import sessionmaker

from app.database import Base, engine
from app.models import Study, Participant, Response


def migrate_database():
    """执行数据库迁移"""
    print("=" * 60)
    print("开始数据库迁移：单问卷 → 多问卷系统")
    print("=" * 60)
    
    # 创建会话
    Session = sessionmaker(bind=engine)
    db = Session()
    
    try:
        # 检查表结构
        existing_tables = db.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )).fetchall()
        existing_table_names = [t[0] for t in existing_tables]
        
        print(f"\n现有表: {existing_table_names}")
        
        # Step 1: 检查并创建/修复 studies 表
        print("\n[Step 1/5] 检查 studies 表...")
        
        if 'studies' not in existing_table_names:
            print("  创建 studies 表...")
            Study.__table__.create(engine)
        else:
            # 检查是否有 code 列
            cols = db.execute(text("PRAGMA table_info(studies)")).fetchall()
            col_names = [c[1] for c in cols]
            
            if 'code' not in col_names:
                print("  警告: 现有 studies 表结构不正确，需要重建")
                # 备份现有数据（如果有）
                try:
                    existing_data = db.execute(text("SELECT * FROM studies")).fetchall()
                    print(f"  备份 {len(existing_data)} 条现有研究记录")
                except:
                    existing_data = []
                
                # 删除旧表并重新创建
                db.execute(text("DROP TABLE studies"))
                Study.__table__.create(engine)
                print("  已重建 studies 表")
            else:
                print("  ✓ studies 表结构正确")
        
        # Step 2: 检查 participants 表结构
        print("\n[Step 2/5] 检查 participants 表...")
        
        cols = db.execute(text("PRAGMA table_info(participants)")).fetchall()
        col_names = [c[1] for c in cols]
        
        if 'study_id' not in col_names:
            print("  需要为 participants 表添加 study_id 列")
            
            # 备份数据
            participants_backup = db.execute(text(
                "SELECT id, started_at, ip_address, user_agent, completed_at FROM participants"
            )).fetchall()
            print(f"  备份 {len(participants_backup)} 条参与者记录")
            
            responses_backup = db.execute(text(
                "SELECT id, participant_id, question_id, selected_index, rating, comment, time_spent, created_at FROM responses"
            )).fetchall()
            print(f"  备份 {len(responses_backup)} 条回答记录")
            
            # 删除表（SQLite不支持ALTER TABLE ADD COLUMN with foreign key）
            db.execute(text("DROP TABLE IF EXISTS responses"))
            db.execute(text("DROP TABLE IF EXISTS participants"))
            print("  删除旧表")
            
            # 创建新表
            Participant.__table__.create(engine)
            Response.__table__.create(engine)
            print("  创建新表（包含 study_id）")
            
            need_data_restore = True
        else:
            print("  ✓ participants 表已有 study_id 列")
            need_data_restore = False
            participants_backup = []
            responses_backup = []
        
        # Step 3: 创建默认问卷
        print("\n[Step 3/5] 创建默认问卷...")
        
        # 检查是否已有默认问卷
        default_study = db.query(Study).filter(Study.code == "default").first()
        
        if not default_study:
            # 读取现有配置
            study_config_path = Path(__file__).parent / "study_config.json"
            config_data = None
            if study_config_path.exists():
                try:
                    with open(study_config_path, 'r', encoding='utf-8') as f:
                        config_json = json.load(f)
                        config_data = json.dumps(config_json, ensure_ascii=False)
                        study_name = config_json.get('title', '默认研究')
                except:
                    config_data = None
            
            if not config_data:
                # 使用默认配置
                config_data = json.dumps({
                    "title": "默认研究",
                    "instructions": "请完成以下问卷",
                    "questions": []
                }, ensure_ascii=False)
                study_name = "默认研究"
            
            default_study = Study(
                code="default",
                name=study_name,
                description="系统自动创建的默认问卷，包含所有历史数据",
                config_json=config_data,
                status="active"
            )
            db.add(default_study)
            db.flush()
            print(f"✓ 默认问卷创建成功 (ID: {default_study.id}, Code: default)")
        else:
            print(f"✓ 默认问卷已存在 (ID: {default_study.id})")
        
        # Step 4: 恢复数据（如果需要）
        if need_data_restore and participants_backup:
            print("\n[Step 4/5] 迁移参与者数据...")
            
            for p_data in participants_backup:
                # 解析日期时间
                started_at = p_data[1]
                completed_at = p_data[4]
                
                if isinstance(started_at, str):
                    started_at = datetime.fromisoformat(started_at.replace(' ', 'T'))
                if isinstance(completed_at, str):
                    completed_at = datetime.fromisoformat(completed_at.replace(' ', 'T'))
                
                new_participant = Participant(
                    id=p_data[0],
                    study_id=default_study.id,
                    started_at=started_at,
                    ip_address=p_data[2],
                    user_agent=p_data[3],
                    completed_at=completed_at
                )
                db.add(new_participant)
            
            db.flush()
            print(f"✓ 已迁移 {len(participants_backup)} 条参与者记录")
            
            # 恢复回答数据
            for r_data in responses_backup:
                created_at = r_data[7]
                if isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace(' ', 'T'))
                
                new_response = Response(
                    id=r_data[0],
                    participant_id=r_data[1],
                    question_id=r_data[2],
                    selected_index=r_data[3],
                    rating=r_data[4],
                    comment=r_data[5],
                    time_spent=r_data[6],
                    created_at=created_at
                )
                db.add(new_response)
            
            print(f"✓ 已迁移 {len(responses_backup)} 条回答记录")
        else:
            # 为现有参与者分配默认问卷
            orphaned = db.query(Participant).filter(
                Participant.study_id.is_(None)
            ).all()
            
            if orphaned:
                print(f"\n[Step 4/5] 为 {len(orphaned)} 条参与者记录分配默认问卷...")
                for p in orphaned:
                    p.study_id = default_study.id
                print(f"✓ 已分配")
            else:
                print("\n[Step 4/5] 所有参与者已关联问卷，跳过")
        
        db.commit()
        
        # Step 5: 验证迁移
        print("\n[Step 5/5] 验证迁移结果...")
        
        study_count = db.query(Study).count()
        participant_count = db.query(Participant).count()
        response_count = db.query(Response).count()
        
        print(f"  Studies: {study_count}")
        print(f"  Participants: {participant_count}")
        print(f"  Responses: {response_count}")
        
        # 验证数据完整性
        assert study_count >= 1, "应该至少有一个问卷"
        
        # 验证外键关系
        orphaned_count = db.query(Participant).filter(
            Participant.study_id.is_(None)
        ).count()
        
        if orphaned_count > 0:
            print(f"  警告: {orphaned_count} 条参与者记录未关联问卷")
        else:
            print("  ✓ 所有参与者已关联问卷")
        
        print("\n" + "=" * 60)
        print("✅ 数据库迁移成功！")
        print("=" * 60)
        print(f"\n默认问卷代码: default")
        print(f"访问链接: http://localhost:8888/study/default")
        print("\n请重启应用以应用更改。")
        
    except Exception as e:
        db.rollback()
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    migrate_database()