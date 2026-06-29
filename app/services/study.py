"""
研究核心服务 - 处理业务逻辑
"""

import json
import os
import random
import shutil
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Participant, Response, StudyConfig, Study, generate_uuid
from app.schemas import (
    StudyConfigData,
    StudyConfigOut,
    ParticipantCreate,
    AnswerSubmit,
    AnswerResult,
    QuestionPageData,
)
from app.utils.short_code import (
    generate_unique_short_code,
    validate_short_code,
    normalize_short_code,
    RESERVED_CODES,
)


class StudyService:
    """研究服务类"""

    def __init__(self, db: Session):
        self.db = db

    # ==================== 配置管理 ====================

    def get_active_config(self) -> Optional[StudyConfigData]:
        """获取当前激活的研究配置"""
        # 首先从数据库获取
        config_record = (
            self.db.query(StudyConfig)
            .filter(StudyConfig.is_active == 1)
            .order_by(StudyConfig.uploaded_at.desc())
            .first()
        )

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
                with open(settings.study_config_path, "r", encoding="utf-8") as f:
                    config_dict = json.load(f)
                    return StudyConfigData(**config_dict)
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            pass

        return None

    def save_config(
        self, config_data: StudyConfigData, uploaded_by: Optional[str] = None
    ) -> StudyConfig:
        """保存新的研究配置"""
        # 先将所有配置设为非激活
        self.db.query(StudyConfig).update({StudyConfig.is_active: 0})

        # 创建新配置
        config_record = StudyConfig(
            config_json=json.dumps(config_data.model_dump(), ensure_ascii=False),
            version=config_data.title,  # 使用标题作为版本标识
            uploaded_by=uploaded_by,
            is_active=1,
        )
        self.db.add(config_record)
        self.db.commit()
        self.db.refresh(config_record)

        return config_record

    def get_config_history(self, limit: int = 10) -> List[StudyConfig]:
        """获取配置历史"""
        return (
            self.db.query(StudyConfig)
            .order_by(StudyConfig.uploaded_at.desc())
            .limit(limit)
            .all()
        )

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
        return (
            self.db.query(Study)
            .order_by(Study.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_active_studies(self) -> List[Study]:
        """获取所有激活状态的问卷"""
        return self.db.query(Study).filter(Study.status == "active").all()

    def create_study(
        self,
        name: str,
        config_data: StudyConfigData,
        description: str = None,
        custom_code: str = None,
    ) -> Study:
        """创建新问卷"""
        # 生成或验证短代码
        if custom_code:
            # 规范化输入
            normalized_input = normalize_short_code(custom_code)

            # 检查是否是保留字（将保留字也进行规范化比较）
            normalized_reserved = {
                normalize_short_code(code) for code in RESERVED_CODES
            }
            if normalized_input in normalized_reserved:
                raise ValueError(f"短代码 '{custom_code}' 是保留字")

            code = normalized_input
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
            status="active",
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
            study.config_json = json.dumps(
                updates["config"].model_dump(), ensure_ascii=False
            )

        study.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(study)

        return study

    def delete_study(self, study_id: str) -> bool:
        """删除问卷（及其所有数据），并清理不再被引用的图像文件"""
        study = self.get_study_by_id(study_id)
        if not study:
            return False

        # 先提取该问卷引用的所有图像路径
        own_paths = self._extract_image_paths(study)

        # 删除数据库记录（级联删除参与者、回答）
        self.db.delete(study)
        self.db.commit()

        # 收集其他问卷引用的图像路径（排除刚删除的那个）
        all_refs = self._collect_all_referenced_images(exclude_study_id=study_id)

        # 清理不再被任何问卷引用的图像文件
        self._cleanup_orphan_images(own_paths, all_refs)

        return True

    def _extract_image_paths(self, study) -> Set[str]:
        """从问卷配置中提取所有图像路径"""
        paths: Set[str] = set()
        try:
            config = json.loads(study.config_json)
        except (json.JSONDecodeError, TypeError):
            return paths

        for question in config.get("questions", []):
            for img_path in question.get("images", []):
                if img_path and isinstance(img_path, str):
                    paths.add(img_path)
        return paths

    def _collect_all_referenced_images(self, exclude_study_id: str) -> Set[str]:
        """收集所有问卷（排除某个）引用的图像路径"""
        all_paths: Set[str] = set()
        studies = self.db.query(Study).filter(Study.id != exclude_study_id).all()
        for s in studies:
            all_paths |= self._extract_image_paths(s)
        return all_paths

    def _cleanup_orphan_images(self, own_paths: Set[str], all_refs: Set[str]) -> int:
        """删除不被任何问卷引用的图像文件，并清理空目录。返回删除的文件数。"""
        from app.config import get_settings

        settings = get_settings()
        upload_root = settings.upload_path
        deleted_count = 0

        for rel_path in own_paths:
            # own_paths 中的路径如 "/uploads/amusement/cake/xxx.jpg"
            if rel_path not in all_refs:
                # 没人引用了，删除文件
                abs_path = upload_root.parent / rel_path.lstrip("/")
                try:
                    if abs_path.exists() and abs_path.is_file():
                        abs_path.unlink()
                        deleted_count += 1
                except OSError:
                    pass  # 文件可能已被删除或无权限

        # 清理空目录：从被删除问卷涉及的情感目录往上扫
        if own_paths:
            self._remove_empty_dirs(own_paths, upload_root)

        return deleted_count

    def _remove_empty_dirs(self, paths: Set[str], upload_root: Path) -> None:
        """删除 paths 涉及到的空目录链"""
        # 收集所有可能受影响的目录
        dirs_to_check: Set[Path] = set()
        for rel_path in paths:
            abs_path = upload_root.parent / rel_path.lstrip("/")
            # 往上走两级：prompt 目录 + emotion 目录
            parent = abs_path.parent  # prompt 目录
            if parent.is_relative_to(upload_root):
                dirs_to_check.add(parent)
                grandparent = parent.parent  # emotion 目录
                if grandparent.is_relative_to(upload_root) and grandparent != upload_root:
                    dirs_to_check.add(grandparent)

        # 按路径长度降序排列（先删深层目录）
        for d in sorted(dirs_to_check, key=lambda p: len(str(p)), reverse=True):
            try:
                if d.exists() and d.is_dir():
                    # 检查是否为空
                    if not any(d.iterdir()):
                        d.rmdir()
            except OSError:
                pass  # 非空目录删不掉，跳过

    def get_study_config(self, study: Study) -> Optional[StudyConfigData]:
        """获取问卷的配置"""
        try:
            config_dict = json.loads(study.config_json)
            return StudyConfigData(**config_dict)
        except (json.JSONDecodeError, ValueError):
            return None

    def get_study_stats(self, study_id: str) -> Dict[str, Any]:
        """获取问卷统计信息"""
        total_participants = (
            self.db.query(Participant).filter(Participant.study_id == study_id).count()
        )

        completed_participants = (
            self.db.query(Participant)
            .filter(
                Participant.study_id == study_id, Participant.completed_at.isnot(None)
            )
            .count()
        )

        in_progress_participants = total_participants - completed_participants

        total_responses = (
            self.db.query(Response)
            .join(Participant)
            .filter(Participant.study_id == study_id)
            .count()
        )

        completion_rate = (
            (completed_participants / total_participants * 100)
            if total_participants > 0
            else 0
        )

        return {
            "total_participants": total_participants,
            "completed_participants": completed_participants,
            "completed_count": completed_participants,  # 兼容模板字段名
            "in_progress_count": in_progress_participants,  # 兼容模板字段名
            "completion_rate": round(completion_rate, 2),
            "total_responses": total_responses,
        }

    # ==================== 参与者管理（支持多问卷） ====================

    def create_participant(
        self, data: ParticipantCreate, study_id: str = None
    ) -> Participant:
        """创建新参与者"""
        # 生成固定的随机种子，确保该参与者的题目顺序始终一致
        # 使用时间戳和UUID的组合生成种子
        seed_str = f"{time.time()}_{generate_uuid()}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**31)

        participant = Participant(
            study_id=study_id,
            ip_address=data.ip_address,
            user_agent=data.user_agent,
            random_seed=seed,
        )
        self.db.add(participant)
        self.db.commit()
        self.db.refresh(participant)
        return participant

    def get_participant(
        self, participant_id: str, study_id: str = None
    ) -> Optional[Participant]:
        """获取参与者（可选：验证是否属于指定问卷）"""
        query = self.db.query(Participant).filter(Participant.id == participant_id)
        if study_id:
            query = query.filter(Participant.study_id == study_id)
        return query.first()

    def get_participant_progress(
        self, participant_id: str, config: StudyConfigData
    ) -> int:
        """获取参与者的答题进度（下一题索引）"""
        answered_count = (
            self.db.query(Response)
            .filter(Response.participant_id == participant_id)
            .count()
        )
        return min(answered_count, len(config.questions))

    def get_study_participants(
        self, study_id: str, skip: int = 0, limit: int = 100
    ) -> List[Participant]:
        """获取问卷的所有参与者"""
        return (
            self.db.query(Participant)
            .filter(Participant.study_id == study_id)
            .order_by(Participant.started_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def mark_participant_completed(self, participant_id: str) -> None:
        """标记参与者已完成"""
        participant = self.get_participant(participant_id)
        if participant:
            participant.completed_at = datetime.utcnow()
            self.db.commit()

    # ==================== 答题逻辑 ====================

    def submit_answer(
        self,
        qidx: int,
        data: AnswerSubmit,
        config: StudyConfigData,
        study_id: str = None,
    ) -> AnswerResult:
        """提交答案"""
        # 验证参与者存在（并验证是否属于指定问卷）
        participant = self.get_participant(data.participant_id, study_id=study_id)
        if not participant:
            return AnswerResult(success=False, message="参与者不存在或无权访问此问卷")

        # 验证问题索引
        if qidx < 0 or qidx >= len(config.questions):
            return AnswerResult(success=False, message="问题索引无效")

        question = config.questions[qidx]

        # 检查是否已回答过此题（更新或创建）
        existing = (
            self.db.query(Response)
            .filter(
                Response.participant_id == data.participant_id,
                Response.question_id == data.question_id,
            )
            .first()
        )

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
                time_spent=data.time_spent,
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
            message="答题完成" if is_completed else "提交成功",
        )

    def get_question_data(
        self, qidx: int, participant_id: str, config: StudyConfigData
    ) -> Optional[QuestionPageData]:
        """获取问题页面数据"""
        if qidx < 0 or qidx >= len(config.questions):
            return None

        question = config.questions[qidx]

        # 构建图片列表（带索引）
        images = [(path, idx) for idx, path in enumerate(question.images)]

        # 随机打乱（如果配置允许）
        if config.randomize:
            # 获取参与者的随机种子
            participant = self.get_participant(participant_id)
            if participant and participant.random_seed is not None:
                # 使用参与者的固定随机种子 + 题目索引作为种子
                # 这样同一参与者在不同时间访问同一题时，看到的顺序都是一样的
                seed = participant.random_seed + qidx
                rng = random.Random(seed)
                rng.shuffle(images)

        return QuestionPageData(
            title=config.title,
            qidx=qidx,
            total_questions=len(config.questions),
            question_id=question.id,
            prompt=question.prompt,
            images=images,
            participant_id=participant_id,
            progress_percent=((qidx) / len(config.questions)) * 100,
        )

    def check_participant_completed(
        self, participant_id: str, total_questions: int, study_id: str = None
    ) -> bool:
        """检查参与者是否已完成所有题目"""
        query = self.db.query(Response).filter(
            Response.participant_id == participant_id
        )

        # 如果提供了study_id，验证参与者是否属于该问卷
        if study_id:
            participant = self.get_participant(participant_id, study_id=study_id)
            if not participant:
                return False

        response_count = query.count()
        return response_count >= total_questions
