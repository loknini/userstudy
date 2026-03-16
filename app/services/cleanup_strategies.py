"""
可扩展的数据清理策略系统
支持自定义添加、配置和执行多种清理策略
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Participant, Response, CleanupStrategyModel
from app.database import SessionLocal
import json


class StrategyType(Enum):
    """策略类型枚举"""
    ZERO_PROGRESS = "zero_progress"           # 零进度清理
    ABANDONED = "abandoned"                   # 放弃实验清理
    COMPLETED_ARCHIVE = "completed_archive"   # 已完成数据归档
    OLD_DATA = "old_data"                     # 老旧数据清理
    CUSTOM_FILTER = "custom_filter"           # 自定义筛选


@dataclass
class CleanupStrategy:
    """清理策略配置"""
    id: str
    name: str
    description: str
    strategy_type: StrategyType
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_run: Optional[datetime] = None
    last_run_result: Optional[Dict] = None
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'strategy_type': self.strategy_type.value,
            'enabled': self.enabled,
            'params': self.params,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'last_run_result': self.last_run_result
        }


class BaseCleanupStrategy(ABC):
    """清理策略基类"""
    
    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
    
    @abstractmethod
    def get_name(self) -> str:
        """策略名称"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """策略描述"""
        pass
    
    @abstractmethod
    def get_param_schema(self) -> Dict[str, Any]:
        """
        获取参数配置模式
        返回参数定义，用于前端生成表单
        """
        pass
    
    @abstractmethod
    def preview(self, params: Dict[str, Any]) -> Dict:
        """预览将要清理的数据"""
        pass
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict:
        """执行清理"""
        pass
    
    def close(self):
        """关闭数据库会话"""
        if self.db:
            self.db.close()


class ZeroProgressStrategy(BaseCleanupStrategy):
    """零进度清理策略"""
    
    def get_name(self) -> str:
        return "零进度参与者清理"
    
    def get_description(self) -> str:
        return "清理只打开页面但未答题的参与者记录"
    
    def get_param_schema(self) -> Dict[str, Any]:
        return {
            'timeout_hours': {
                'type': 'number',
                'label': '超时时间（小时）',
                'description': '超过此时间未答题将被清理',
                'default': 24,
                'min': 1,
                'max': 168,
                'required': True
            }
        }
    
    def preview(self, params: Dict[str, Any]) -> Dict:
        timeout_hours = params.get('timeout_hours', 24)
        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)
        
        count = self.db.query(Participant).filter(
            Participant.started_at < cutoff_time,
            ~Participant.id.in_(
                self.db.query(Response.participant_id).distinct()
            )
        ).count()
        
        return {
            'would_delete': count,
            'description': f'将清理 {count} 条零进度记录（>{timeout_hours}小时未答题）'
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict:
        timeout_hours = params.get('timeout_hours', 24)
        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)
        
        participants = self.db.query(Participant).filter(
            Participant.started_at < cutoff_time,
            ~Participant.id.in_(
                self.db.query(Response.participant_id).distinct()
            )
        ).all()
        
        deleted_count = len(participants)
        deleted_ids = [p.id[:8] + '...' for p in participants]
        
        for p in participants:
            self.db.delete(p)
        
        self.db.commit()
        
        return {
            'deleted_count': deleted_count,
            'deleted_ids': deleted_ids
        }


class AbandonedExperimentStrategy(BaseCleanupStrategy):
    """放弃实验清理策略 - 清理长时间未完成且没有最近活动的"""
    
    def get_name(self) -> str:
        return "放弃实验清理"
    
    def get_description(self) -> str:
        return "清理有答题记录但长时间未完成且没有新活动的参与者"
    
    def get_param_schema(self) -> Dict[str, Any]:
        return {
            'inactive_days': {
                'type': 'number',
                'label': '无活动天数',
                'description': '超过此天数无新答题记录将被清理',
                'default': 30,
                'min': 7,
                'max': 365,
                'required': True
            },
            'min_progress': {
                'type': 'number',
                'label': '最小进度',
                'description': '只清理进度低于此值的参与者',
                'default': 10,
                'min': 0,
                'max': 79,
                'required': True
            }
        }
    
    def preview(self, params: Dict[str, Any]) -> Dict:
        inactive_days = params.get('inactive_days', 30)
        min_progress = params.get('min_progress', 10)
        cutoff_time = datetime.utcnow() - timedelta(days=inactive_days)
        
        # 获取最近有活动的参与者
        recent_active = self.db.query(Response.participant_id).filter(
            Response.created_at >= cutoff_time
        ).distinct().subquery()
        
        # 获取未完成且无近期活动的参与者
        candidates = self.db.query(Participant).filter(
            Participant.completed_at.is_(None),
            ~Participant.id.in_(recent_active)
        ).all()
        
        # 计算进度并筛选
        count = 0
        for p in candidates:
            progress = self.db.query(Response).filter(
                Response.participant_id == p.id
            ).count()
            if progress < min_progress:
                count += 1
        
        return {
            'would_delete': count,
            'description': f'将清理 {count} 条放弃实验记录（>{inactive_days}天无活动且进度<{min_progress}）'
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict:
        inactive_days = params.get('inactive_days', 30)
        min_progress = params.get('min_progress', 10)
        cutoff_time = datetime.utcnow() - timedelta(days=inactive_days)
        
        recent_active = self.db.query(Response.participant_id).filter(
            Response.created_at >= cutoff_time
        ).distinct().subquery()
        
        candidates = self.db.query(Participant).filter(
            Participant.completed_at.is_(None),
            ~Participant.id.in_(recent_active)
        ).all()
        
        deleted_ids = []
        deleted_count = 0
        
        for p in candidates:
            progress = self.db.query(Response).filter(
                Response.participant_id == p.id
            ).count()
            if progress < min_progress:
                deleted_ids.append(p.id[:8] + '...')
                self.db.delete(p)
                deleted_count += 1
        
        self.db.commit()
        
        return {
            'deleted_count': deleted_count,
            'deleted_ids': deleted_ids
        }


class OldDataStrategy(BaseCleanupStrategy):
    """老旧数据清理策略"""
    
    def get_name(self) -> str:
        return "老旧数据清理"
    
    def get_description(self) -> str:
        return "清理指定日期之前的所有数据（包括已完成）"
    
    def get_param_schema(self) -> Dict[str, Any]:
        return {
            'before_date': {
                'type': 'date',
                'label': '清理此日期之前的数据',
                'description': '将删除此日期之前创建的所有参与者记录',
                'required': True
            },
            'include_completed': {
                'type': 'boolean',
                'label': '包含已完成的数据',
                'description': '是否也清理已完成的实验数据',
                'default': False
            }
        }
    
    def preview(self, params: Dict[str, Any]) -> Dict:
        before_date_str = params.get('before_date')
        include_completed = params.get('include_completed', False)
        
        if not before_date_str:
            return {'would_delete': 0, 'description': '请设置日期'}
        
        before_date = datetime.strptime(before_date_str, '%Y-%m-%d')
        
        query = self.db.query(Participant).filter(
            Participant.started_at < before_date
        )
        
        if not include_completed:
            query = query.filter(Participant.completed_at.is_(None))
        
        count = query.count()
        
        return {
            'would_delete': count,
            'description': f'将清理 {count} 条{before_date_str}之前的老旧记录'
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict:
        before_date_str = params.get('before_date')
        include_completed = params.get('include_completed', False)
        
        before_date = datetime.strptime(before_date_str, '%Y-%m-%d')
        
        query = self.db.query(Participant).filter(
            Participant.started_at < before_date
        )
        
        if not include_completed:
            query = query.filter(Participant.completed_at.is_(None))
        
        participants = query.all()
        deleted_count = len(participants)
        deleted_ids = [p.id[:8] + '...' for p in participants]
        
        for p in participants:
            self.db.delete(p)
        
        self.db.commit()
        
        return {
            'deleted_count': deleted_count,
            'deleted_ids': deleted_ids
        }


class StrategyManager:
    """策略管理器 - 管理所有清理策略"""
    
    def __init__(self):
        self.strategies: Dict[StrategyType, BaseCleanupStrategy] = {
            StrategyType.ZERO_PROGRESS: ZeroProgressStrategy,
            StrategyType.ABANDONED: AbandonedExperimentStrategy,
            StrategyType.OLD_DATA: OldDataStrategy,
        }
        # 存储用户自定义策略配置
        self._custom_strategies: Dict[str, CleanupStrategy] = {}
        self._load_custom_strategies()
    
    def _load_custom_strategies(self):
        """从数据库或文件加载用户自定义策略"""
        # 这里可以实现从数据库加载
        # 现在使用内存存储，重启后重置
        pass
    
    def get_available_strategies(self) -> List[Dict]:
        """获取所有可用的策略类型"""
        result = []
        for strategy_type, strategy_class in self.strategies.items():
            instance = strategy_class()
            try:
                result.append({
                    'type': strategy_type.value,
                    'name': instance.get_name(),
                    'description': instance.get_description(),
                    'param_schema': instance.get_param_schema()
                })
            finally:
                instance.close()
        return result
    
    def create_custom_strategy(self, 
                               name: str, 
                               description: str,
                               strategy_type: StrategyType,
                               params: Dict[str, Any]) -> CleanupStrategy:
        """创建自定义策略"""
        strategy_id = f"custom_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        strategy = CleanupStrategy(
            id=strategy_id,
            name=name,
            description=description,
            strategy_type=strategy_type,
            params=params,
            enabled=True
        )
        
        self._custom_strategies[strategy_id] = strategy
        return strategy
    
    def get_custom_strategies(self) -> List[Dict]:
        """获取所有自定义策略"""
        return [s.to_dict() for s in self._custom_strategies.values()]
    
    def update_custom_strategy(self, strategy_id: str, 
                               updates: Dict[str, Any]) -> Optional[CleanupStrategy]:
        """更新自定义策略"""
        if strategy_id not in self._custom_strategies:
            return None
        
        strategy = self._custom_strategies[strategy_id]
        
        if 'name' in updates:
            strategy.name = updates['name']
        if 'description' in updates:
            strategy.description = updates['description']
        if 'params' in updates:
            strategy.params = updates['params']
        if 'enabled' in updates:
            strategy.enabled = updates['enabled']
        
        return strategy
    
    def delete_custom_strategy(self, strategy_id: str) -> bool:
        """删除自定义策略"""
        if strategy_id in self._custom_strategies:
            del self._custom_strategies[strategy_id]
            return True
        return False
    
    def execute_strategy(self, strategy_id: str, 
                        custom_params: Optional[Dict] = None) -> Dict:
        """执行指定策略"""
        # 获取策略配置
        if strategy_id in self._custom_strategies:
            strategy_config = self._custom_strategies[strategy_id]
            if not strategy_config.enabled:
                raise ValueError(f"策略 {strategy_id} 已禁用")
            
            strategy_type = strategy_config.strategy_type
            params = custom_params or strategy_config.params
        else:
            # 内置策略直接通过类型执行
            try:
                strategy_type = StrategyType(strategy_id)
                params = custom_params or {}
            except ValueError:
                raise ValueError(f"未知的策略: {strategy_id}")
        
        # 执行策略
        if strategy_type not in self.strategies:
            raise ValueError(f"未实现的策略类型: {strategy_type}")
        
        strategy_class = self.strategies[strategy_type]
        instance = strategy_class()
        
        try:
            result = instance.execute(params)
            
            # 更新策略执行记录
            if strategy_id in self._custom_strategies:
                self._custom_strategies[strategy_id].last_run = datetime.utcnow()
                self._custom_strategies[strategy_id].last_run_result = result
            
            return result
        finally:
            instance.close()
    
    def preview_strategy(self, strategy_id: str, 
                        params: Dict[str, Any]) -> Dict:
        """预览策略执行结果"""
        try:
            strategy_type = StrategyType(strategy_id)
        except ValueError:
            raise ValueError(f"未知的策略: {strategy_id}")
        
        if strategy_type not in self.strategies:
            raise ValueError(f"未实现的策略类型: {strategy_type}")
        
        strategy_class = self.strategies[strategy_type]
        instance = strategy_class()
        
        try:
            return instance.preview(params)
        finally:
            instance.close()


# 全局策略管理器实例
strategy_manager = StrategyManager()


# ============ 系统默认策略配置 ============

class SystemCleanupConfig:
    """系统清理配置"""
    
    # 系统默认策略（作为配置，不存储在数据库）
    DEFAULT_STRATEGIES = [
        {
            "id": "system_zero_progress",
            "name": "零进度参与者清理（自动）",
            "description": "系统自动清理只打开页面但未答题的参与者记录",
            "type": "zero_progress",
            "enabled": True,
            "is_system": True,
            "params": {
                "hours": 24
            },
            "schedule": "0 2 * * *"  # 每天凌晨2点
        }
    ]
    
    @staticmethod
    def get_all_strategies_with_system(db: Session) -> List[Dict]:
        """获取所有策略（包括系统默认）"""
        strategies = []
        
        # 添加系统策略
        for default in SystemCleanupConfig.DEFAULT_STRATEGIES:
            # 尝试从数据库读取自定义配置
            db_strategy = db.query(CleanupStrategyModel).filter(
                CleanupStrategyModel.id == default["id"]
            ).first()
            
            if db_strategy:
                # 解析 JSON params
                try:
                    params = json.loads(db_strategy.params) if db_strategy.params else default["params"]
                except json.JSONDecodeError:
                    params = default["params"]
                
                strategies.append({
                    **default,
                    "enabled": bool(db_strategy.enabled),
                    "params": params,
                    "last_run": db_strategy.last_run.isoformat() if db_strategy.last_run else None
                })
            else:
                strategies.append({
                    **default,
                    "last_run": None
                })
        
        # 添加自定义策略
        custom_strategies = db.query(CleanupStrategyModel).filter(
            CleanupStrategyModel.is_system == False
        ).all()
        
        for cs in custom_strategies:
            # 解析 JSON params
            try:
                params = json.loads(cs.params) if cs.params else {}
            except json.JSONDecodeError:
                params = {}
            
            strategies.append({
                "id": cs.id,
                "name": cs.name,
                "description": cs.description,
                "type": cs.strategy_type if isinstance(cs.strategy_type, str) else cs.strategy_type.value,
                "enabled": bool(cs.enabled),
                "is_system": False,
                "params": params,
                "last_run": cs.last_run.isoformat() if cs.last_run else None
            })
        
        return strategies
    
    @staticmethod
    def get_strategy_config(strategy_id: str, db: Session = None) -> Optional[Dict]:
        """获取策略配置"""
        # 检查是否是系统策略
        for default in SystemCleanupConfig.DEFAULT_STRATEGIES:
            if default["id"] == strategy_id:
                if db:
                    db_strategy = db.query(CleanupStrategyModel).filter(
                        CleanupStrategyModel.id == strategy_id
                    ).first()
                    if db_strategy:
                        # 解析 JSON params
                        try:
                            params = json.loads(db_strategy.params) if db_strategy.params else default["params"]
                        except json.JSONDecodeError:
                            params = default["params"]
                        
                        return {
                            **default,
                            "enabled": bool(db_strategy.enabled),
                            "params": params,
                            "last_run": db_strategy.last_run.isoformat() if db_strategy.last_run else None
                        }
                return {**default, "last_run": None}
        
        # 检查是否是自定义策略
        if db:
            cs = db.query(CleanupStrategyModel).filter(
                CleanupStrategyModel.id == strategy_id
            ).first()
            
            if cs:
                # 解析 JSON params
                try:
                    params = json.loads(cs.params) if cs.params else {}
                except json.JSONDecodeError:
                    params = {}
                
                return {
                    "id": cs.id,
                    "name": cs.name,
                    "description": cs.description,
                    "type": cs.strategy_type if isinstance(cs.strategy_type, str) else cs.strategy_type.value,
                    "enabled": bool(cs.enabled),
                    "is_system": False,
                    "params": params,
                    "last_run": cs.last_run.isoformat() if cs.last_run else None
                }
        
        return None
    
    @staticmethod
    def update_system_strategy(strategy_id: str, updates: Dict, db: Session) -> bool:
        """更新系统策略配置"""
        is_system = any(s["id"] == strategy_id for s in SystemCleanupConfig.DEFAULT_STRATEGIES)
        
        if not is_system:
            return False
        
        db_strategy = db.query(CleanupStrategyModel).filter(
            CleanupStrategyModel.id == strategy_id
        ).first()
        
        if db_strategy:
            if "enabled" in updates:
                db_strategy.enabled = 1 if updates["enabled"] else 0
            if "params" in updates:
                # 合并现有参数和新参数
                try:
                    existing_params = json.loads(db_strategy.params) if db_strategy.params else {}
                except json.JSONDecodeError:
                    existing_params = {}
                
                merged_params = {**existing_params, **updates["params"]}
                db_strategy.params = json.dumps(merged_params, ensure_ascii=False)
        else:
            # 创建系统策略的数据库记录
            default = next(s for s in SystemCleanupConfig.DEFAULT_STRATEGIES if s["id"] == strategy_id)
            params = updates.get("params", default["params"])
            
            db_strategy = CleanupStrategyModel(
                id=strategy_id,
                name=default["name"],
                description=default["description"],
                strategy_type=StrategyType.ZERO_PROGRESS.value,
                enabled=1 if updates.get("enabled", default["enabled"]) else 0,
                is_system=1,
                params=json.dumps(params, ensure_ascii=False)
            )
            db.add(db_strategy)
        
        db.commit()
        return True
    
    @staticmethod
    def run_enabled_strategies(db: Session) -> List[Dict]:
        """执行所有启用的策略（用于定时任务）"""
        results = []
        strategies = SystemCleanupConfig.get_all_strategies_with_system(db)
        
        for strategy in strategies:
            if strategy["enabled"]:
                try:
                    strategy_type = strategy["type"]
                    params = strategy.get("params", {})
                    
                    result = strategy_manager.execute_strategy(strategy_type, params)
                    
                    # 更新执行时间和结果
                    db_strategy = db.query(CleanupStrategyModel).filter(
                        CleanupStrategyModel.id == strategy["id"]
                    ).first()
                    
                    if db_strategy:
                        db_strategy.last_run = datetime.utcnow()
                        db_strategy.last_run_result = json.dumps(result, ensure_ascii=False, default=str)
                        db.commit()
                    
                    results.append({
                        "strategy_id": strategy["id"],
                        "name": strategy["name"],
                        "status": "success",
                        "deleted_count": result.get("deleted_count", 0)
                    })
                except Exception as e:
                    # 记录错误
                    db_strategy = db.query(CleanupStrategyModel).filter(
                        CleanupStrategyModel.id == strategy["id"]
                    ).first()
                    if db_strategy:
                        db_strategy.last_run = datetime.utcnow()
                        db_strategy.last_run_result = json.dumps({"error": str(e)}, ensure_ascii=False)
                        db.commit()
                    
                    results.append({
                        "strategy_id": strategy["id"],
                        "name": strategy["name"],
                        "status": "error",
                        "error": str(e)
                    })
        
        return results
