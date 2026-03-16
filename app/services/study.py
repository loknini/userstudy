"""
研究核心服务 - 处理业务逻辑
"""
import json
import random
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Participant, Response, StudyConfig, Study
from app.schemas import (
    StudyConfigData, StudyConfigOut, ParticipantCreate, 
    AnswerSubmit, AnswerResult, QuestionPageData
)
from app.utils.short_code import generate_unique_short_code, validate_short_code, normalize_short_code


class StudyService:
    """研究服务类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ==================== 配置管理 ====================
    
    def get_active_config(self) -> Optional[StudyConfigData]:
        """获取当前激活的研究配置"""
        # 首先从数据库获取
        config_record = self.db.query(StudyConfig).filter(
            StudyConfig.is_active == 1
        ).order_by(StudyConfig.uploaded_at.desc()).first()
        
        if config_record:
            try:
                config_dict = json.loads(config_record.config_json)
                return StudyConfigData(**config_dict)
            except (json.JSONDecodeError, ValueError):
                pass  # 解析失败，回退到文件
        
        # 回退到配置文件
        try:
            from app.config import get_settings
            settings = get_settings()
            if settings.study_config_path.exists():
                with open(settings.study_config_path, 'r', encoding='utf-8') as f:
                    config_dict = json.load(f)
                    return StudyConfigData(**config_dict)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass
        
        return None
    
    def save_config(self, config_data: StudyConfigData, uploaded_by: Optional[str] = None) -> StudyConfig:
        """保存新的研究配置"""
        # 先将所有配置设为非激活
        self.db.query(StudyConfig).update({StudyConfig.is_active: 0})
        
        # 创建新配置
        config_record = StudyConfig(
            config_json=json.dumps(config_data.model_dump(), ensure_ascii=False),
            version=config_data.title,  # 使用标题作为版本标识
            uploaded_by=uploaded_by,
            is_active=1
        )
        self.db.add(config_record)
        self.db.commit()
        self.db.refresh(config_record)
        
        return config_record
    
    def get_config_history(self, limit: int = 10) -> List[StudyConfig]:
        """获取配置历史"""
        return self.db.query(StudyConfig).order_by(
            StudyConfig.uploaded_at.desc()
        ).limit(limit).all()
    
    # ==================== Study（多问卷）管理 ====================
    
    def get_study_by_code(self, code: str) -> Optional[Study]:
        """通过短代码获取问卷"""
        normalized_code = normalize_short_code(code)
        return self.db.query(Study).filter(Study.code == normalized_code).first()
    
    def get_study_by_id(self, study_id: str) -> Optional[Study]:
        """通过ID获取问卷"""
        return self.db.query(Study).filter(Study.id == study_id).first()
    
    def get_all_studies(self, skip: int = 0, limit: int = 100) -> List[Study]:
        """获取所有问卷列表"""
        return self.db.query(Study).order_by(Study.created_at.desc()).offset(skip).limit(limit).all()
    
    def get_active_studies(self) -> List[Study]:
        """获取所有激活状态的问卷"""
        return self.db.query(Study).filter(Study.status == "active").all()
    
    def create_study(
        self, 
        name: str, 
        config_data: StudyConfigData, 
        description: str = None,
        custom_code: str = None
    ) -> Study:
        """创建新问卷"""
        # 生成或验证短代码
        if custom_code:
            code = normalize_short_code(custom_code)
            if not validate_short_code(code):
                raise ValueError("短代码格式无效")
            # 检查是否已存在
            existing = self.get_study_by_code(code)
            if existing:
                raise ValueError(f"短代码 '{code}' 已被使用")
        else:
            code = generate_unique_short_code(self.db)
            if not code:
                raise ValueError("无法生成唯一短代码")
        
        # 创建问卷
        study = Study(
            code=code,
            name=name,
            description=description or name,
            config_json=json.dumps(config_data.model_dump(), ensure_ascii=False),
            status="active"
        )
        self.db.add(study)
        self.db.commit()
        self.db.refresh(study)
        
        return study
    
    def update_study(self, study_id: str, updates: Dict[str, Any]) -> Optional[Study]:
        """更新问卷信息"""
        study = self.get_study_by_id(study_id)
        if not study:
            return None
        
        if "name" in updates:
            study.name = updates["name"]
        if "description" in updates:
            study.description = updates["description"]
        if "status" in updates:
            study.status = updates["status"]
        if "config" in updates and isinstance(updates["config"], StudyConfigData):
            study.config_json = json.dumps(updates["config"].model_dump(), ensure_ascii=False)
        
        study.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(study)
        
        return study
    
    def delete_study(self, study_id: str) -> bool:
        """删除问卷（及其所有数据）"""
        study = self.get_study_by_id(study_id)
        if not study:
            return False
        
        self.db.delete(study)  # 级联删除参与者
        self.db.commit()
        return True
    
    def get_study_config(self, study: Study) -> Optional[StudyConfigData]:
        """获取问卷的配置"""
        try:
            config_dict = json.loads(study.config_json)
            return StudyConfigData(**config_dict)
        except (json.JSONDecodeError, ValueError):
            return None
    
    def get_study_stats(self, study_id: str) -> Dict[str, Any]:
        """获取问卷统计信息"""
        total_participants = self.db.query(Participant).filter(
            Participant.study_id == study_id
        ).count()
        
        completed_participants = self.db.query(Participant).filter(
            Participant.study_id == study_id,
            Participant.completed_at.isnot(None)
        ).count()
        
        total_responses = self.db.query(Response).join(Participant).filter(
            Participant.study_id == study_id
        ).count()
        
        completion_rate = (
            (completed_participants / total_participants * 100)
            if total_participants > 0 else 0
        )
        
        return {
            "total_participants": total_participants,
            "completed_participants": completed_participants,
            "completion_rate": round(completion_rate, 2),
            "total_responses": total_responses
        }
    
    # ==================== 参与者管理（支持多问卷） ====================
    
    def create_participant(self, data: ParticipantCreate, study_id: str = None) -> Participant:
        """创建新参与者"""
        participant = Participant(
            study_id=study_id,
            ip_address=data.ip_address,
            user_agent=data.user_agent
        )
        self.db.add(participant)
        self.db.commit()
        self.db.refresh(participant)
        return participant
    
    def get_participant(self, participant_id: str, study_id: str = None) -> Optional[Participant]:
        """获取参与者（可选：验证是否属于指定问卷）"""
        query = self.db.query(Participant).filter(Participant.id == participant_id)
        if study_id:
            query = query.filter(Participant.study_id == study_id)
        return query.first()
    
    def get_participant_progress(self, participant_id: str, config: StudyConfigData) -> int:
        """获取参与者的答题进度（下一题索引）"""
        answered_count = self.db.query(Response).filter(
            Response.participant_id == participant_id
        ).count()
        return min(answered_count, len(config.questions))
    
    def get_study_participants(self, study_id: str, skip: int = 0, limit: int = 100) -> List[Participant]:
        """获取问卷的所有参与者"""
        return self.db.query(Participant).filter(
            Participant.study_id == study_id
        ).order_by(Participant.started_at.desc()).offset(skip).limit(limit).all()
    
    def mark_participant_completed(self, participant_id: str) -> None:
        """标记参与者已完成"""
        participant = self.get_participant(participant_id)
        if participant:
            participant.completed_at = datetime.utcnow()
            self.db.commit()
    
    # ==================== 答题逻辑 ====================
    
    def submit_answer(self, qidx: int, data: AnswerSubmit, config: StudyConfigData, study_id: str = None) -> AnswerResult:
        """提交答案"""
        # 验证参与者存在（并验证是否属于指定问卷）
        participant = self.get_participant(data.participant_id, study_id=study_id)
        if not participant:
            return AnswerResult(
                success=False,
                message="参与者不存在或无权访问此问卷"
            )
        
        # 验证问题索引
        if qidx < 0 or qidx >= len(config.questions):
            return AnswerResult(
                success=False,
                message="问题索引无效"
            )
        
        question = config.questions[qidx]
        
        # 检查是否已回答过此题（更新或创建）
        existing = self.db.query(Response).filter(
            Response.participant_id == data.participant_id,
            Response.question_id == data.question_id
        ).first()
        
        if existing:
            # 更新已有回答（保留最新）
            existing.selected_index = data.selected_index
            existing.rating = data.rating
            existing.comment = data.comment
            existing.time_spent = data.time_spent
            existing.created_at = datetime.utcnow()
        else:
            # 创建新回答
            response = Response(
                participant_id=data.participant_id,
                question_id=data.question_id,
                selected_index=data.selected_index,
                rating=data.rating,
                comment=data.comment,
                time_spent=data.time_spent
            )
            self.db.add(response)
        
        self.db.commit()
        
        # 计算下一题
        next_idx = qidx + 1
        is_completed = next_idx >= len(config.questions)
        
        if is_completed:
            self.mark_participant_completed(data.participant_id)
        
        return AnswerResult(
            success=True,
            next_question_idx=next_idx if not is_completed else None,
            is_completed=is_completed,
            message="答题完成" if is_completed else "提交成功"
        )
    
    def get_question_data(
        self, 
        qidx: int, 
        participant_id: str, 
        config: StudyConfigData
    ) -> Optional[QuestionPageData]:
        """获取问题页面数据"""
        if qidx < 0 or qidx >= len(config.questions):
            return None
        
        question = config.questions[qidx]
        
        # 构建图片列表（带索引）
        images = [(path, idx) for idx, path in enumerate(question.images)]
        
        # 随机打乱（如果配置允许）
        if config.randomize:
            random.shuffle(images)
        
        return QuestionPageData(
            title=config.title,
            qidx=qidx,
            total_questions=len(config.questions),
            question_id=question.id,
            prompt=question.prompt,
            images=images,
            participant_id=participant_id,
            progress_percent=((qidx) / len(config.questions)) * 100
        )
    
    def check_participant_completed(self, participant_id: str, total_questions: int, study_id: str = None) -> bool:
        """检查参与者是否已完成所有题目"""
        query = self.db.query(Response).filter(Response.participant_id == participant_id)
        
        # 如果提供了study_id，验证参与者是否属于该问卷
        if study_id:
            participant = self.get_participant(participant_id, study_id=study_id)
            if not participant:
                return False
        
        response_count = query.count()
        return response_count >= total_questions
