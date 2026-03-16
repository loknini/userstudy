"""
SQLAlchemy 数据库模型
"""
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.database import Base


def generate_uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


def generate_short_code(length: int = 6) -> str:
    """生成短代码（排除易混淆字符）"""
    import random
    import string
    # 排除易混淆字符: 0, O, 1, I, l
    chars = ''.join(set(string.ascii_lowercase + string.digits) - {'0', 'o', '1', 'i', 'l'})
    return ''.join(random.choices(chars, k=length))


class Study(Base):
    """研究/问卷模型（多问卷支持）"""
    __tablename__ = "studies"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    code = Column(String(20), unique=True, nullable=False, index=True)  # 短代码，如"abc123"
    name = Column(String(200), nullable=False)  # 问卷名称
    description = Column(Text, nullable=True)  # 描述
    config_json = Column(Text, nullable=False)  # 问卷配置JSON
    status = Column(String(20), default="active", nullable=False)  # active/paused/archived
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    participants = relationship("Participant", back_populates="study", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index('idx_study_code', 'code'),
        Index('idx_study_status', 'status', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Study(id={self.id}, code={self.code}, name={self.name})>"


class Participant(Base):
    """参与者模型"""
    __tablename__ = "participants"
    
    id = Column(String(36), primary_key=True, default=generate_uuid)
    study_id = Column(String(36), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(45), nullable=True)  # IPv6 最长 45 字符
    user_agent = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)  # 完成时间
    
    # 关系
    study = relationship("Study", back_populates="participants")
    responses = relationship("Response", back_populates="participant", cascade="all, delete-orphan")
    
    # 索引
    __table_args__ = (
        Index('idx_participant_study', 'study_id', 'started_at'),
        Index('idx_participant_started', 'started_at'),
        Index('idx_participant_ip', 'ip_address'),
    )
    
    def __repr__(self) -> str:
        return f"<Participant(id={self.id}, started_at={self.started_at})>"
    
    @property
    def response_count(self) -> int:
        """返回该参与者的答题数量"""
        return len(self.responses) if self.responses else 0
    
    @property
    def is_completed(self) -> bool:
        """是否已完成问卷"""
        return self.completed_at is not None


class Response(Base):
    """用户响应模型"""
    __tablename__ = "responses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String(36), ForeignKey("participants.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String(50), nullable=False, index=True)
    selected_index = Column(Integer, nullable=True)  # 选择的图片索引
    rating = Column(Integer, nullable=True)  # 评分（可选）
    comment = Column(Text, nullable=True)  # 评论（可选）
    time_spent = Column(Float, nullable=True)  # 答题用时（秒）
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    participant = relationship("Participant", back_populates="responses")
    
    # 复合索引
    __table_args__ = (
        Index('idx_response_participant_question', 'participant_id', 'question_id', unique=True),
        Index('idx_response_created', 'created_at'),
        Index('idx_response_question', 'question_id', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Response(id={self.id}, participant_id={self.participant_id}, question_id={self.question_id})>"


class StudyConfig(Base):
    """研究配置存储模型"""
    __tablename__ = "study_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    config_json = Column(Text, nullable=False)  # JSON 字符串
    version = Column(String(20), nullable=False, default="1.0")
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    uploaded_by = Column(String(50), nullable=True)  # 上传者标识
    is_active = Column(Integer, default=1)  # 是否当前激活的配置
    
    # 索引
    __table_args__ = (
        Index('idx_config_active', 'is_active', 'uploaded_at'),
    )
    
    def __repr__(self) -> str:
        return f"<StudyConfig(id={self.id}, version={self.version}, uploaded_at={self.uploaded_at})>"


class AuditLog(Base):
    """审计日志模型（可选，用于记录重要操作）"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(50), nullable=False)  # 操作类型
    entity_type = Column(String(50), nullable=True)  # 实体类型
    entity_id = Column(String(50), nullable=True)  # 实体ID
    details = Column(Text, nullable=True)  # 详细内容（JSON）
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 索引
    __table_args__ = (
        Index('idx_audit_created', 'created_at'),
        Index('idx_audit_action', 'action', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, created_at={self.created_at})>"


class CleanupStrategyModel(Base):
    """清理策略配置模型"""
    __tablename__ = "cleanup_strategies"
    
    id = Column(String(50), primary_key=True)  # 策略ID
    name = Column(String(100), nullable=False)  # 策略名称
    description = Column(Text, nullable=True)  # 描述
    strategy_type = Column(String(50), nullable=False)  # 策略类型
    enabled = Column(Integer, default=1, nullable=False)  # 是否启用
    is_system = Column(Integer, default=0, nullable=False)  # 是否系统策略
    params = Column(Text, nullable=True)  # 参数JSON
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_run = Column(DateTime, nullable=True)  # 上次执行时间
    last_run_result = Column(Text, nullable=True)  # 上次执行结果JSON
    
    # 索引
    __table_args__ = (
        Index('idx_cleanup_enabled', 'enabled', 'is_system'),
        Index('idx_cleanup_type', 'strategy_type'),
    )
    
    def __repr__(self) -> str:
        return f"<CleanupStrategyModel(id={self.id}, name={self.name}, enabled={self.enabled})>"
