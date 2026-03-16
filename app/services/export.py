"""
导出服务 - 处理异步导出任务
"""
import csv
import io
import os
import uuid
from datetime import datetime
from typing import Optional
from pathlib import Path
import threading

from sqlalchemy.orm import Session

from app.database import get_db_context
from app.services.stats import StatsService


# 内存中的任务存储（生产环境应使用 Redis 或数据库）
_export_tasks = {}
_export_lock = threading.Lock()


class ExportTaskManager:
    """导出任务管理器"""
    
    def __init__(self):
        self.tasks = _export_tasks
        self.lock = _export_lock
    
    def create_task(self) -> str:
        """创建新任务"""
        task_id = str(uuid.uuid4())
        with self.lock:
            self.tasks[task_id] = {
                "task_id": task_id,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "completed_at": None,
                "file_path": None,
                "message": None
            }
        return task_id
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        with self.lock:
            return self.tasks.get(task_id)
    
    def update_task(self, task_id: str, **kwargs) -> None:
        """更新任务状态"""
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)
    
    def start_export_csv(self, task_id: str, export_dir: Path) -> None:
        """启动 CSV 导出任务（后台线程）"""
        self.update_task(task_id, status="processing")
        
        def export_worker():
            try:
                with get_db_context() as db:
                    stats_service = StatsService(db)
                    data = stats_service.export_responses_csv()
                    
                    # 生成 CSV
                    output = io.StringIO()
                    if data:
                        writer = csv.DictWriter(output, fieldnames=data[0].keys())
                        writer.writeheader()
                        writer.writerows(data)
                    
                    # 保存文件
                    file_name = f"export_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    file_path = export_dir / file_name
                    
                    export_dir.mkdir(parents=True, exist_ok=True)
                    with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                        f.write(output.getvalue())
                    
                    self.update_task(
                        task_id,
                        status="completed",
                        completed_at=datetime.utcnow(),
                        file_path=str(file_path),
                        message=f"导出完成，共 {len(data)} 条记录"
                    )
                    
            except Exception as e:
                self.update_task(
                    task_id,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    message=str(e)
                )
        
        # 启动后台线程
        thread = threading.Thread(target=export_worker)
        thread.daemon = True
        thread.start()


# 全局任务管理器实例
export_manager = ExportTaskManager()
