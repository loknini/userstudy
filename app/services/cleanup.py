"""
数据清理服务 - 定时清理无效数据 & 临时文件
"""
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Participant, Response
from app.database import SessionLocal


class CleanupService:
    """数据清理服务"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
    
    def cleanup_inactive_participants(self, 
                                      zero_progress_timeout_hours: int = 24) -> Dict:
        """
        清理无效参与者数据
        
        策略：
        1. 进度=0且超过指定小时数未答题 -> 删除（只打开页面未答题）
        2. 进度>0的保留（即使未完成）
        3. 已完成的保留
        
        Args:
            zero_progress_timeout_hours: 零进度参与者超时时间（小时）
        
        Returns:
            清理统计信息
        """
        now = datetime.utcnow()
        
        # 清理进度为0且超时的参与者
        zero_progress_timeout = now - timedelta(hours=zero_progress_timeout_hours)
        
        zero_progress_participants = self.db.query(Participant).filter(
            Participant.started_at < zero_progress_timeout,
            ~Participant.id.in_(
                self.db.query(Response.participant_id).distinct()
            )
        ).all()
        
        zero_progress_count = len(zero_progress_participants)
        
        # 执行删除（级联删除会自动删除关联的 responses）
        deleted_ids = []
        
        for p in zero_progress_participants:
            deleted_ids.append({
                'id': p.id[:8] + '...',
                'reason': 'zero_progress',
                'started_at': p.started_at.isoformat()
            })
            self.db.delete(p)
        
        self.db.commit()
        
        return {
            'timestamp': now.isoformat(),
            'deleted_count': zero_progress_count,
            'zero_progress_deleted': zero_progress_count,
            'deleted_ids': deleted_ids
        }
    
    def get_cleanup_preview(self, zero_progress_timeout_hours: int = 24) -> Dict:
        """
        预览将要清理的数据（不实际删除）
        
        Args:
            zero_progress_timeout_hours: 零进度参与者超时时间（小时）
        """
        now = datetime.utcnow()
        
        # 进度为0的
        zero_progress_timeout = now - timedelta(hours=zero_progress_timeout_hours)
        zero_progress_count = self.db.query(Participant).filter(
            Participant.started_at < zero_progress_timeout,
            ~Participant.id.in_(
                self.db.query(Response.participant_id).distinct()
            )
        ).count()
        
        return {
            'would_delete_zero_progress': zero_progress_count,
            'total_would_delete': zero_progress_count,
            'zero_progress_timeout_hours': zero_progress_timeout_hours
        }
    
    def close(self):
        """关闭数据库会话"""
        if self.db:
            self.db.close()


def _cleanup_orphaned_temp_files(
    temp_root: Path,
    max_age_hours: int = 24,
) -> Dict:
    """
    清理过期的临时文件。

    清理对象：
    1. _temp/{upload_id}/  — 已解压但未完成问卷创建的 zip 内容
    2. _temp/tmp*.zip       — 上传过程中遗留的原始 zip 文件

    Args:
        temp_root: 临时文件根目录 (settings.upload_path / "_temp")
        max_age_hours: 超过此小时数未修改的临时目录将被删除

    Returns:
        {deleted_dirs: int, deleted_files: int, freed_bytes: int}
    """
    if not temp_root.exists():
        return {"deleted_dirs": 0, "deleted_files": 0, "freed_bytes": 0}

    now = datetime.now()
    cutoff = now.timestamp() - max_age_hours * 3600
    deleted_dirs = 0
    deleted_files = 0
    freed_bytes = 0

    for item in temp_root.iterdir():
        try:
            stat = item.stat()
            if stat.st_mtime > cutoff:
                continue

            if item.is_dir():
                # 计算目录大小
                dir_size = sum(
                    f.stat().st_size
                    for f in item.rglob("*")
                    if f.is_file()
                )
                shutil.rmtree(str(item), ignore_errors=True)
                deleted_dirs += 1
                freed_bytes += dir_size
            elif item.is_file() and item.suffix.lower() == ".zip":
                # 残留的原始 zip 文件（tmpXXXXXX.zip）
                file_size = stat.st_size
                item.unlink(missing_ok=True)
                deleted_files += 1
                freed_bytes += file_size
        except OSError:
            # 权限问题等，跳过继续
            pass

    return {
        "deleted_dirs": deleted_dirs,
        "deleted_files": deleted_files,
        "freed_bytes": freed_bytes,
    }


def run_cleanup_job(zero_progress_timeout_hours: int = None):
    """
    定时任务入口函数
    每天凌晨2点执行清理（数据库记录 + 临时文件）
    """
    from datetime import datetime
    from app.database import SessionLocal
    from app.config import get_settings
    from app.services.cleanup_strategies import SystemCleanupConfig
    
    print(f"[{datetime.now().isoformat()}] 开始执行数据清理任务...")
    
    db = SessionLocal()
    try:
        # 1. 数据库清理：使用策略系统执行所有启用的策略
        results = SystemCleanupConfig.run_enabled_strategies(db)
        
        total_db_deleted = sum(
            r.get("deleted_count", 0) for r in results if r["status"] == "success"
        )
        
        print(f"  [DB] 完成: 已执行 {len(results)} 个策略, 清理 {total_db_deleted} 条记录")
        for r in results:
            status_icon = "✓" if r["status"] == "success" else "✗"
            print(f"    {status_icon} {r['name']}: {r.get('deleted_count', 0)} 条")
        
        # 2. 文件系统清理：zip 临时文件
        settings = get_settings()
        temp_root = settings.upload_path / "_temp"
        file_result = _cleanup_orphaned_temp_files(temp_root, max_age_hours=24)
        
        freed_mb = round(file_result["freed_bytes"] / (1024 * 1024), 1)
        print(
            f"  [FS] 临时文件清理: {file_result['deleted_dirs']} 个解压目录, "
            f"{file_result['deleted_files']} 个残留 zip, 释放 {freed_mb} MB"
        )
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_db_deleted": total_db_deleted,
            "db_results": results,
            "temp_files": file_result,
        }
    except Exception as e:
        print(f"  错误: {type(e).__name__}: {str(e)}")
        raise
    finally:
        db.close()
