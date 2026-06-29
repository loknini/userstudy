"""
统计服务 - 处理数据分析和统计
"""

from typing import Dict, List, Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Participant, Response
from app.schemas import (
    StudyConfigData,
    OverallStats,
    QuestionStats,
    ModelStats,
    ChartData,
    ChartDataSet,
)


class StatsService:
    """统计服务类"""

    def __init__(self, db: Session):
        self.db = db

    # ---- helper ----

    def _participant_query(self, study_id: Optional[str] = None):
        """构建参与者查询，可选按 study_id 过滤"""
        q = self.db.query(Participant)
        if study_id:
            q = q.filter(Participant.study_id == study_id)
        return q

    def _response_query(self, study_id: Optional[str] = None):
        """构建回答查询，可选通过 Participant 按 study_id 过滤"""
        q = self.db.query(Response)
        if study_id:
            q = q.join(Participant).filter(Participant.study_id == study_id)
        return q

    # ---- stats ----

    def get_overall_stats(self, config: StudyConfigData, study_id: Optional[str] = None) -> OverallStats:
        """获取整体统计"""
        # 基础统计
        total_participants = self._participant_query(study_id).count()
        completed_participants = (
            self._participant_query(study_id)
            .filter(Participant.completed_at.isnot(None))
            .count()
        )

        total_responses = self._response_query(study_id).count()

        # 平均答题时间
        avg_time = (
            self._response_query(study_id)
            .with_entities(func.avg(Response.time_spent))
            .filter(Response.time_spent.isnot(None))
            .scalar()
        )
        
        # 如果没有 time_spent 数据，使用参与者的完成时间差计算
        if not avg_time:
            completed_participants_with_time = (
                self._participant_query(study_id)
                .filter(
                    Participant.completed_at.isnot(None),
                    Participant.started_at.isnot(None)
                )
                .all()
            )
            
            if completed_participants_with_time:
                total_time = 0
                for p in completed_participants_with_time:
                    delta = p.completed_at - p.started_at
                    total_time += delta.total_seconds()
                avg_time = total_time / len(completed_participants_with_time)

        # 每个问题的统计
        per_question = self._get_question_stats(config, study_id)

        # 每个模型的统计
        per_model = self._get_model_stats(config, study_id)

        completion_rate = (
            completed_participants / total_participants * 100
            if total_participants > 0
            else 0
        )

        return OverallStats(
            total_participants=total_participants,
            completed_participants=completed_participants,
            completion_rate=round(completion_rate, 2),
            total_responses=total_responses,
            average_response_time=round(avg_time, 2) if avg_time else None,
            per_question=per_question,
            per_model=per_model,
        )

    def _get_question_stats(self, config: StudyConfigData, study_id: Optional[str] = None) -> List[QuestionStats]:
        """获取每个问题的统计"""
        stats = []

        for question in config.questions:
            # 查询该问题的所有回答
            q = self._response_query(study_id).filter(Response.question_id == question.id)
            responses = q.all()

            if not responses:
                continue

            # 按索引统计选择次数
            picks_by_index: Dict[int, int] = defaultdict(int)
            picks_by_model: Dict[str, int] = defaultdict(int)
            total_time = 0.0
            time_count = 0

            for r in responses:
                if r.selected_index is not None:
                    picks_by_index[r.selected_index] += 1

                    # 映射到模型名
                    if r.selected_index < len(question.models):
                        model_name = question.models[r.selected_index]
                        picks_by_model[model_name] += 1

                if r.time_spent:
                    total_time += r.time_spent
                    time_count += 1

            stats.append(
                QuestionStats(
                    question_id=question.id,
                    prompt=question.prompt[:100] + "..."
                    if len(question.prompt) > 100
                    else question.prompt,
                    total_responses=len(responses),
                    picks_by_index=dict(picks_by_index),
                    picks_by_model=dict(picks_by_model),
                    average_time_spent=round(total_time / time_count, 2)
                    if time_count > 0
                    else None,
                )
            )

        return stats

    def _get_model_stats(self, config: StudyConfigData, study_id: Optional[str] = None) -> List[ModelStats]:
        """获取每个模型的统计"""
        # 收集所有模型
        all_models = set()
        for q in config.questions:
            all_models.update(q.models)

        model_stats = {
            model: {"total": 0, "emotion": 0, "content": 0} for model in all_models
        }

        # 统计每个模型的选择
        for question in config.questions:
            q = self._response_query(study_id).filter(Response.question_id == question.id)
            responses = q.all()

            is_emotion_question = question.id.endswith("-1")
            is_content_question = question.id.endswith("-2")

            for r in responses:
                if r.selected_index is not None and r.selected_index < len(
                    question.models
                ):
                    model_name = question.models[r.selected_index]
                    model_stats[model_name]["total"] += 1

                    if is_emotion_question:
                        model_stats[model_name]["emotion"] += 1
                    elif is_content_question:
                        model_stats[model_name]["content"] += 1

        # 计算选择率
        total_picks = sum(s["total"] for s in model_stats.values())

        result = []
        for model_name, stats in model_stats.items():
            pick_rate = (stats["total"] / total_picks * 100) if total_picks > 0 else 0
            result.append(
                ModelStats(
                    model_name=model_name,
                    total_picks=stats["total"],
                    emotion_picks=stats["emotion"],
                    content_picks=stats["content"],
                    pick_rate=round(pick_rate, 2),
                )
            )

        # 按总得票数排序
        result.sort(key=lambda x: x.total_picks, reverse=True)
        return result

    def get_chart_data(self, config: StudyConfigData, study_id: Optional[str] = None) -> ChartDataSet:
        """获取图表数据"""
        # 获取模型统计
        model_stats = self._get_model_stats(config, study_id)

        # 总体投票
        overall_votes = ChartData(
            labels=[s.model_name for s in model_stats],
            data=[s.total_picks for s in model_stats],
        )

        # 情感维度投票 (-1 结尾的问题)
        emotion_votes = ChartData(
            labels=[s.model_name for s in model_stats],
            data=[s.emotion_picks for s in model_stats],
        )

        # 内容维度投票 (-2 结尾的问题)
        content_votes = ChartData(
            labels=[s.model_name for s in model_stats],
            data=[s.content_picks for s in model_stats],
        )

        return ChartDataSet(
            overall_votes=overall_votes,
            emotion_votes=emotion_votes,
            content_votes=content_votes,
        )

    def get_dashboard_stats(self, study_id: Optional[str] = None) -> Dict:
        """获取仪表盘统计数据"""
        from datetime import datetime, timedelta

        # 今日统计
        today = datetime.now().date()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        today_participants = (
            self._participant_query(study_id)
            .filter(
                Participant.started_at >= today_start,
                Participant.started_at <= today_end,
            )
            .count()
        )

        # 总体统计
        total_participants = self._participant_query(study_id).count()
        completed_count = (
            self._participant_query(study_id)
            .filter(Participant.completed_at.isnot(None))
            .count()
        )

        total_responses = self._response_query(study_id).count()

        # 平均答题时间
        avg_time = (
            self._response_query(study_id)
            .with_entities(func.avg(Response.time_spent))
            .filter(Response.time_spent.isnot(None))
            .scalar()
        )

        # 初始化completed_participants变量
        completed_participants = []

        # 如果没有 time_spent 数据，使用参与者的完成时间差计算
        if not avg_time:
            # 查询所有已完成的参与者及其完成时间差
            completed_participants = (
                self._participant_query(study_id)
                .filter(
                    Participant.completed_at.isnot(None),
                    Participant.started_at.isnot(None),
                )
                .all()
            )

            if completed_participants:
                total_time = 0
                for p in completed_participants:
                    if p.completed_at and p.started_at:
                        delta = p.completed_at - p.started_at
                        total_time += delta.total_seconds()

                if total_time > 0:
                    avg_time = total_time / len(completed_participants)

        # 完成率
        completion_rate = (
            completed_count / total_participants * 100 if total_participants > 0 else 0
        )

        # 最近7天趋势
        daily_stats = []
        for i in range(6, -1, -1):
            date = today - timedelta(days=i)
            date_start = datetime.combine(date, datetime.min.time())
            date_end = datetime.combine(date, datetime.max.time())

            count = (
                self._participant_query(study_id)
                .filter(
                    Participant.started_at >= date_start,
                    Participant.started_at <= date_end,
                )
                .count()
            )

            daily_stats.append({"date": date.strftime("%m-%d"), "count": count})

        # 最近参与的用户（最近10个）
        recent_participants = (
            self._participant_query(study_id)
            .order_by(Participant.started_at.desc())
            .limit(10)
            .all()
        )

        # 批量查询 response 计数（避免 N+1）
        recent_ids = [p.id for p in recent_participants]
        response_counts = {}
        if recent_ids:
            from sqlalchemy import func as sqlfunc
            counts = (
                self.db.query(
                    Response.participant_id,
                    sqlfunc.count(Response.id).label("cnt"),
                )
                .filter(Response.participant_id.in_(recent_ids))
                .group_by(Response.participant_id)
                .all()
            )
            response_counts = {pid: cnt for pid, cnt in counts}

        recent_list = []
        for p in recent_participants:
            progress = response_counts.get(p.id, 0)

            recent_list.append(
                {
                    "id": p.id[:8] + "...",
                    "created_at": p.started_at.strftime("%m-%d %H:%M")
                    if p.started_at
                    else "",
                    "progress": progress,
                    "completed": p.completed_at is not None,
                }
            )

        return {
            "summary": {
                "total_participants": total_participants,
                "completed_participants": completed_count,
                "completion_rate": round(completion_rate, 1),
                "total_responses": total_responses,
                "today_participants": today_participants,
                "average_time": round(avg_time, 1) if avg_time else 0,
            },
            "daily_trend": daily_stats,
            "recent_participants": recent_list,
        }

    def export_responses_csv(self, study_id: Optional[str] = None) -> List[Dict]:
        """导出所有响应为长格式 CSV（每行 = 一次答题）"""
        responses = self._response_query(study_id).all()

        data = []
        for r in responses:
            data.append(
                {
                    "id": r.id,
                    "participant_id": r.participant_id,
                    "question_id": r.question_id,
                    "selected_index": r.selected_index,
                    "rating": r.rating,
                    "comment": r.comment,
                    "time_spent": r.time_spent,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )

        return data

    def export_participants_wide(self, config: StudyConfigData, study_id: Optional[str] = None) -> List[Dict]:
        """导出为宽表格式（每行 = 一个参与者的完整问卷）

        包含参与者元信息 + 每题各维度列：
        - {q_id}_selected: 选择的图片序号（0-based）
        - {q_id}_model: 选择的模型名
        - {q_id}_time: 该题耗时（秒）
        - {q_id}_rating: 该题评分
        - {q_id}_comment: 该题评语
        """
        from app.models import Participant

        # 获取所有已完成参与者
        participants = (
            self._participant_query(study_id)
            .filter(Participant.completed_at.isnot(None))
            .order_by(Participant.started_at)
            .all()
        )

        if not participants:
            return []

        # 批量查询所有 responses
        participant_ids = [p.id for p in participants]
        all_responses = (
            self.db.query(Response)
            .filter(Response.participant_id.in_(participant_ids))
            .all()
        )

        # 按 participant_id 分组
        response_groups = defaultdict(list)
        for r in all_responses:
            response_groups[r.participant_id].append(r)

        # 构建问题列表（按 config 里的顺序）
        question_ids = [q.id for q in config.questions]

        data = []
        for p in participants:
            responses = response_groups.get(p.id, [])
            response_map = {r.question_id: r for r in responses}

            # 参与者基本信息
            row = {
                "participant_id": p.id,
                "started_at": p.started_at.isoformat() if p.started_at else "",
                "completed_at": p.completed_at.isoformat() if p.completed_at else "",
                "total_time_seconds": (
                    (p.completed_at - p.started_at).total_seconds()
                    if p.completed_at and p.started_at
                    else ""
                ),
                "ip_address": p.ip_address or "",
                "screen_resolution": p.screen_resolution or "",
                "language": p.language or "",
                "timezone": p.timezone or "",
                "platform": p.platform or "",
                "cookies_enabled": p.cookies_enabled or "",
                "do_not_track": p.do_not_track or "",
            }

            # 每题数据
            for qid in question_ids:
                r = response_map.get(qid)
                question = next((q for q in config.questions if q.id == qid), None)

                if r and r.selected_index is not None:
                    row[f"{qid}_selected"] = r.selected_index
                    # 映射到模型名
                    if question and r.selected_index < len(question.models):
                        row[f"{qid}_model"] = question.models[r.selected_index]
                    else:
                        row[f"{qid}_model"] = ""
                else:
                    row[f"{qid}_selected"] = ""
                    row[f"{qid}_model"] = ""

                row[f"{qid}_time"] = r.time_spent if r and r.time_spent else ""
                row[f"{qid}_rating"] = r.rating if r else ""
                row[f"{qid}_comment"] = r.comment if r and r.comment else ""

            data.append(row)

        return data

    def get_participant_consistency_analysis(self, config: StudyConfigData, study_id: Optional[str] = None) -> Dict:
        """分析参与者选择一致性"""
        # 获取所有已完成用户
        participants = (
            self._participant_query(study_id)
            .filter(Participant.completed_at.isnot(None))
            .all()
        )

        consistency_data = []

        # 批量查询所有 responses（避免 N+1）
        participant_ids = [p.id for p in participants]
        all_responses = (
            self.db.query(Response)
            .filter(Response.participant_id.in_(participant_ids))
            .all()
        ) if participant_ids else []

        # 按 participant_id 分组
        response_groups = defaultdict(list)
        for r in all_responses:
            response_groups[r.participant_id].append(r)

        for p in participants:
            # 获取该用户的所有回答
            responses = response_groups.get(p.id, [])

            # 按问题组分析（q1-1 和 q1-2 是一组）
            response_map = {r.question_id: r for r in responses}

            consistent_count = 0
            total_groups = 0

            for question in config.questions:
                qid = question.id
                if qid.endswith("-1"):  # 情感问题
                    base_id = qid[:-2]  # q1
                    content_id = base_id + "-2"  # q1-2

                    if content_id in response_map and qid in response_map:
                        total_groups += 1
                        if (
                            response_map[qid].selected_index
                            == response_map[content_id].selected_index
                        ):
                            consistent_count += 1

            if total_groups > 0:
                consistency_rate = consistent_count / total_groups
                consistency_data.append(
                    {
                        "participant_id": p.id,
                        "consistency_rate": consistency_rate,
                        "consistent_count": consistent_count,
                        "total_groups": total_groups,
                    }
                )

        return {
            "total_participants": len(consistency_data),
            "average_consistency_rate": sum(
                d["consistency_rate"] for d in consistency_data
            )
            / len(consistency_data)
            if consistency_data
            else 0,
            "details": consistency_data,
        }
