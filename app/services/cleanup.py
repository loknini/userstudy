"""
数据清理服务 - 定时清理无效数据
"""
from datetime import datetime, timedelta
from typing import Dict, List

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


def run_cleanup_job(zero_progress_timeout_hours: int = None):
    """
    定时任务入口函数
    每天凌晨2点执行清理（使用策略系统配置）
    """
    from datetime import datetime
    from app.database import SessionLocal
    from app.services.cleanup_strategies import SystemCleanupConfig
    
    print(f"[{datetime.now().isoformat()}] 开始执行数据清理任务...")
    
    db = SessionLocal()
    try:
        # 使用策略系统执行所有启用的策略
        results = SystemCleanupConfig.run_enabled_strategies(db)
        
        total_deleted = sum(r.get("deleted_count", 0) for r in results if r["status"] == "success")
        
        print(f"  完成: 已执行 {len(results)} 个策略")
        print(f"  总计清理: {total_deleted} 条记录")
        
        for r in results:
            status_icon = "✓" if r["status"] == "success" else "✗"
            print(f"    {status_icon} {r['name']}: {r.get('deleted_count', 0)} 条")
        
        return {
            "timestamp": datetime.now().isoformat(),
            "total_deleted": total_deleted,
            "results": results
        }
    except Exception as e:
        print(f"  错误: {type(e).__name__}: {str(e)}")
        raise
    finally:
        db.close()
