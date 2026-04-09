"""
管理后台路由 - 配置管理和数据导出
"""

from typing import Optional

from fastapi import (
    APIRouter,
    Request,
    Depends,
    Form,
    UploadFile,
    File,
    HTTPException,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import json
import os
from apscheduler.triggers.cron import CronTrigger
from app.database import get_db
from app.config import get_settings
from app.schemas import StudyConfigData
from app.services.study import StudyService
from app.services.stats import StatsService
from app.services.export import export_manager
from app.services.cleanup import CleanupService, run_cleanup_job
from app.services.cleanup_strategies import strategy_manager, StrategyType
from app.template_manager import get_templates

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin(password: Optional[str] = None) -> bool:
    """验证管理员密码"""
    if not password:
        return False
    settings = get_settings()
    return password == settings.ADMIN_PASSWORD


def get_study_service(db: Session = Depends(get_db)) -> StudyService:
    return StudyService(db)


def get_stats_service(db: Session = Depends(get_db)) -> StatsService:
    return StatsService(db)


@router.get("/", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """管理后台首页"""
    templates = get_templates()
    if not verify_admin(pw):
        return templates.TemplateResponse(
            request, "admin_login.html", {"request": request, "error": None}
        )

    config = service.get_active_config()
    config_text = (
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2)
        if config
        else "未加载"
    )

    return templates.TemplateResponse(
        request,
        "admin.html",
        {"request": request, "pw": pw, "config_text": config_text},
    )


@router.post("/upload-config")
async def upload_config(
    request: Request,
    pw: str = Form(...),
    configfile: UploadFile = File(...),
    service: StudyService = Depends(get_study_service),
):
    """上传研究配置"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        content = await configfile.read()
        config_dict = json.loads(content.decode("utf-8"))
        config_data = StudyConfigData(**config_dict)

        # 保存到数据库
        config_record = service.save_config(config_data, uploaded_by="admin")

        # 同时保存到文件（兼容旧版本）
        settings = get_settings()
        with open(settings.study_config_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        return RedirectResponse(url=f"/admin/?pw={pw}", status_code=303)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/analysis", response_class=HTMLResponse)
async def analysis_page(
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """数据分析页面"""
    templates = get_templates()
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    config = service.get_active_config()
    title = config.title if config else "User Study"

    return templates.TemplateResponse(
        request, "analysis.html", {"request": request, "pw": pw, "title": title}
    )


@router.get("/stats")
async def get_stats(
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取统计数据 (JSON)"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    stats = stats_service.get_overall_stats(config)
    return stats


@router.get("/dashboard")
async def get_dashboard(
    pw: Optional[str] = None, stats_service: StatsService = Depends(get_stats_service)
):
    """获取仪表盘数据"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    dashboard_data = stats_service.get_dashboard_stats()
    return dashboard_data


@router.get("/chart-data")
async def get_chart_data(
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取图表数据"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    chart_data = stats_service.get_chart_data(config)
    return chart_data


@router.get("/detailed-analysis")
async def get_detailed_analysis(
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取详细分析数据"""
    import numpy as np
    from collections import defaultdict

    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    # 获取基本统计
    overall_stats = stats_service.get_overall_stats(config)

    # 获取一致性分析
    consistency_analysis = stats_service.get_participant_consistency_analysis(config)

    # 计算详细的偏好分析
    model_stats = sorted(
        overall_stats.per_model, key=lambda x: x.total_picks, reverse=True
    )

    # 获取所有模型名称
    all_models = ["sdxl", "ti", "emogen", "ours"]

    # 计算每个用户的偏好率（用于计算标准差和百分位数）
    from app.models import Participant, Response

    # 获取已完成的参与者
    completed_participants = (
        stats_service.db.query(Participant)
        .filter(Participant.completed_at.isnot(None))
        .all()
    )

    user_cnt = len(completed_participants)

    # 初始化用户偏好数据
    user_emo_prefs = {model: [] for model in all_models}
    user_content_prefs = {model: [] for model in all_models}
    user_consistency_rates = {model: [] for model in all_models}

    # 统计情感和内容问题数量
    num_emo_questions = sum(1 for q in config.questions if q.id.endswith("-1"))
    num_content_questions = sum(1 for q in config.questions if q.id.endswith("-2"))

    # 计算每个用户的偏好率
    for participant in completed_participants:
        responses = (
            stats_service.db.query(Response)
            .filter(Response.participant_id == participant.id)
            .all()
        )

        response_map = {r.question_id: r for r in responses}

        # 情感和内容偏好计数
        emo_counts = {model: 0 for model in all_models}
        content_counts = {model: 0 for model in all_models}
        consistent_counts = {model: 0 for model in all_models}

        for question in config.questions:
            r = response_map.get(question.id)
            if (
                r
                and r.selected_index is not None
                and r.selected_index < len(question.models)
            ):
                model_name = question.models[r.selected_index]

                if question.id.endswith("-1"):
                    emo_counts[model_name] += 1
                elif question.id.endswith("-2"):
                    content_counts[model_name] += 1

        # 计算偏好率
        for model in all_models:
            if num_emo_questions > 0:
                user_emo_prefs[model].append(emo_counts[model] / num_emo_questions)
            if num_content_questions > 0:
                user_content_prefs[model].append(
                    content_counts[model] / num_content_questions
                )

        # 计算一致性
        total_consistent = 0
        for question in config.questions:
            if question.id.endswith("-1"):
                base_id = question.id[:-2]
                content_id = base_id + "-2"

                emo_r = response_map.get(question.id)
                content_r = response_map.get(content_id)

                if (
                    emo_r
                    and content_r
                    and emo_r.selected_index is not None
                    and content_r.selected_index is not None
                    and emo_r.selected_index == content_r.selected_index
                    and emo_r.selected_index < len(question.models)
                ):
                    model_name = question.models[emo_r.selected_index]
                    consistent_counts[model_name] += 1
                    total_consistent += 1

        # 计算一致性率
        if total_consistent > 0:
            for model in all_models:
                user_consistency_rates[model].append(
                    consistent_counts[model] / total_consistent
                )

    # 计算统计指标
    def calc_stats(values):
        if not values:
            return {"mean": 0, "std": 0, "p25": 0, "p75": 0}
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "p25": float(np.percentile(values, 25)),
            "p75": float(np.percentile(values, 75)),
        }

    # 准备详细分析数据
    # 计算总体偏好统计
    overall_prefs = []
    for stat in model_stats:
        # 合并情感和内容偏好数据
        combined_prefs = []
        emo_list = user_emo_prefs.get(stat.model_name, [])
        content_list = user_content_prefs.get(stat.model_name, [])
        max_len = max(len(emo_list), len(content_list))
        for i in range(max_len):
            emo_val = emo_list[i] if i < len(emo_list) else 0
            content_val = content_list[i] if i < len(content_list) else 0
            # 计算情感和内容的平均值作为平衡性
            average_val = (emo_val + content_val) / 2
            combined_prefs.append(average_val)

        overall_prefs.append(
            {
                "model": stat.model_name,
                "picks": stat.total_picks,
                "rate": stat.pick_rate,
                "stats": calc_stats(combined_prefs),
            }
        )

    # 计算情感维度统计
    emotion_prefs = []
    for stat in sorted(model_stats, key=lambda x: x.emotion_picks, reverse=True):
        emotion_prefs.append(
            {
                "model": stat.model_name,
                "picks": stat.emotion_picks,
                "stats": calc_stats(user_emo_prefs.get(stat.model_name, [])),
            }
        )

    # 计算内容维度统计
    content_prefs = []
    for stat in sorted(model_stats, key=lambda x: x.content_picks, reverse=True):
        content_prefs.append(
            {
                "model": stat.model_name,
                "picks": stat.content_picks,
                "stats": calc_stats(user_content_prefs.get(stat.model_name, [])),
            }
        )

    # 计算一致性统计
    model_consistency_stats = []
    for model in all_models:
        consistent_count = sum(
            1
            for d in consistency_analysis.get("details", [])
            if d.get("consistent_count", 0) > 0
        )
        model_consistency_stats.append(
            {
                "model": model,
                "count": consistent_count,
                "stats": calc_stats(user_consistency_rates.get(model, [])),
            }
        )

    detailed_analysis = {
        "overall_stats": {
            "total_participants": overall_stats.total_participants,
            "completed_participants": overall_stats.completed_participants,
            "completion_rate": overall_stats.completion_rate,
            "average_response_time": overall_stats.average_response_time,
        },
        "model_preferences": {
            "overall": overall_prefs,
            "emotion": emotion_prefs,
            "content": content_prefs,
        },
        "consistency": {
            "total_participants": consistency_analysis.get("total_participants", 0),
            "average_consistency_rate": consistency_analysis.get(
                "average_consistency_rate", 0
            ),
            "details": consistency_analysis.get("details", []),
            "model_stats": model_consistency_stats,
        },
    }

    return detailed_analysis


@router.post("/export")
async def start_export(
    pw: str = Form(...),
    background: bool = Form(True),  # 是否异步导出
):
    """启动数据导出"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    task_id = export_manager.create_task()

    if background:
        settings = get_settings()
        export_manager.start_export_csv(task_id, settings.BASE_DIR / "exports")
        return {"task_id": task_id, "status": "processing"}
    else:
        # 同步导出（小数据量）
        # ...
        pass


@router.get("/export/{task_id}/status")
async def check_export_status(task_id: str, pw: Optional[str] = None):
    """检查导出任务状态"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    task = export_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.get("/export/{task_id}/download")
async def download_export(task_id: str, pw: Optional[str] = None):
    """下载导出文件"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    task = export_manager.get_task(task_id)
    if not task or task["status"] != "completed":
        raise HTTPException(status_code=404, detail="Export not ready")

    file_path = task.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=file_path, filename=f"responses_{task_id}.csv", media_type="text/csv"
    )


# ========== 数据清理相关端点 ==========


@router.get("/cleanup/preview")
async def preview_cleanup(pw: Optional[str] = None, zero_hours: int = 24):
    """预览将要清理的数据（不实际删除）"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    service = CleanupService()
    try:
        preview = service.get_cleanup_preview(zero_hours)
        return preview
    finally:
        service.close()


@router.post("/cleanup/run")
async def run_cleanup_api(pw: str = Form(...), zero_hours: int = Form(24)):
    """手动执行数据清理"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    result = run_cleanup_job(zero_hours)
    return result


@router.get("/cleanup/schedule")
async def get_cleanup_schedule(pw: Optional[str] = None):
    """获取清理任务的定时计划"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.main import scheduler

    if not scheduler:
        return {"status": "not_initialized", "message": "定时任务未启动"}

    job = scheduler.get_job("cleanup_job")
    if job:
        return {
            "status": "active",
            "job_id": job.id,
            "job_name": job.name,
            "next_run_time": job.next_run_time.isoformat()
            if job.next_run_time
            else None,
            "trigger": str(job.trigger),
        }
    else:
        return {"status": "not_found", "message": "清理任务未找到"}


@router.post("/cleanup/update-schedule")
async def update_cleanup_schedule(
    pw: str = Form(...),
    zero_hours: int = Form(24),
    hour: int = Form(2),
    minute: int = Form(0),
):
    """更新定时清理任务的参数"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.main import scheduler

    if not scheduler:
        raise HTTPException(status_code=500, detail="定时任务未启动")

    # 更新任务
    job = scheduler.get_job("cleanup_job")
    if job:
        # 移除旧任务
        scheduler.remove_job("cleanup_job")

    # 添加新任务
    scheduler.add_job(
        run_cleanup_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="cleanup_job",
        name="数据清理任务",
        args=[zero_hours],
        replace_existing=True,
    )

    job = scheduler.get_job("cleanup_job")

    return {
        "status": "updated",
        "message": "定时任务已更新",
        "settings": {
            "zero_progress_timeout_hours": zero_hours,
            "run_time": f"{hour:02d}:{minute:02d}",
        },
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
    }


# ========== 策略管理相关端点 ==========


@router.get("/cleanup/strategies")
async def get_available_strategies(pw: Optional[str] = None):
    """获取所有可用的清理策略类型"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    strategies = strategy_manager.get_available_strategies()
    custom_strategies = strategy_manager.get_custom_strategies()

    return {"built_in": strategies, "custom": custom_strategies}


@router.post("/cleanup/strategies/custom")
async def create_custom_strategy(
    pw: str = Form(...),
    name: str = Form(...),
    description: str = Form(...),
    strategy_type: str = Form(...),
    params: str = Form(...),  # JSON字符串
):
    """创建自定义清理策略"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        import json

        params_dict = json.loads(params)
        strategy_type_enum = StrategyType(strategy_type)

        strategy = strategy_manager.create_custom_strategy(
            name=name,
            description=description,
            strategy_type=strategy_type_enum,
            params=params_dict,
        )

        return strategy.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/cleanup/strategies/custom/{strategy_id}")
async def update_custom_strategy(
    strategy_id: str,
    pw: str = Form(...),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
    enabled: Optional[bool] = Form(None),
):
    """更新自定义策略"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    updates = {}
    if name is not None:
        updates["name"] = name
    if description is not None:
        updates["description"] = description
    if params is not None:
        import json

        updates["params"] = json.loads(params)
    if enabled is not None:
        updates["enabled"] = enabled

    strategy = strategy_manager.update_custom_strategy(strategy_id, updates)

    if not strategy:
        raise HTTPException(status_code=404, detail="策略未找到")

    return strategy.to_dict()


@router.delete("/cleanup/strategies/custom/{strategy_id}")
async def delete_custom_strategy(strategy_id: str, pw: str = Form(...)):
    """删除自定义策略"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    success = strategy_manager.delete_custom_strategy(strategy_id)

    if not success:
        raise HTTPException(status_code=404, detail="策略未找到")

    return {"status": "deleted", "strategy_id": strategy_id}


@router.post("/cleanup/strategies/{strategy_id}/preview")
async def preview_strategy(
    strategy_id: str,
    pw: str = Form(...),
    params: str = Form(...),  # JSON字符串
):
    """预览策略执行结果"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        import json

        params_dict = json.loads(params)

        result = strategy_manager.preview_strategy(strategy_id, params_dict)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cleanup/strategies/{strategy_id}/execute")
async def execute_strategy(
    strategy_id: str, pw: str = Form(...), params: Optional[str] = Form(None)
):
    """执行指定策略"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        params_dict = {}
        if params:
            import json

            params_dict = json.loads(params)

        result = strategy_manager.execute_strategy(strategy_id, params_dict)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 多问卷管理 API ====================


@router.get("/api/studies")
async def get_studies_api(
    pw: Optional[str] = None, service: StudyService = Depends(get_study_service)
):
    """获取问卷列表 API"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    studies = service.get_all_studies()
    return {
        "success": True,
        "studies": [
            {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in studies
        ],
    }


@router.get("/studies", response_class=HTMLResponse)
async def studies_list_page(
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """问卷列表页面"""
    templates = get_templates()
    if not verify_admin(pw):
        return templates.TemplateResponse(
            request, "admin_login.html", {"request": request, "error": None}
        )

    studies = service.get_all_studies()
    return templates.TemplateResponse(
        request,
        "admin_studies.html",
        {"request": request, "pw": pw, "studies": studies},
    )


@router.get("/studies/create", response_class=HTMLResponse)
async def create_study_page(request: Request, pw: Optional[str] = None):
    """创建问卷页面"""
    templates = get_templates()
    if not verify_admin(pw):
        return templates.TemplateResponse(
            request, "admin_login.html", {"request": request, "error": None}
        )

    return templates.TemplateResponse(
        request, "admin_study_create.html", {"request": request, "pw": pw}
    )


@router.post("/studies/create")
async def create_study(
    request: Request,
    pw: str = Form(...),
    name: str = Form(...),
    code: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    configfile: UploadFile = File(...),
    service: StudyService = Depends(get_study_service),
):
    """创建问卷"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # 读取配置文件
        content = await configfile.read()
        config_dict = json.loads(content.decode("utf-8"))
        config_data = StudyConfigData(**config_dict)

        # 创建问卷
        study = service.create_study(
            name=name,
            config_data=config_data,
            description=description,
            custom_code=code,
        )

        return RedirectResponse(url=f"/admin/studies?pw={pw}", status_code=303)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/study/{study_code}", response_class=HTMLResponse)
async def study_detail_page(
    request: Request,
    study_code: str,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """问卷详情页面"""
    templates = get_templates()
    if not verify_admin(pw):
        return templates.TemplateResponse(
            request, "admin_login.html", {"request": request, "error": None}
        )

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    stats = service.get_study_stats(study.id)

    return templates.TemplateResponse(
        request,
        "admin_study_detail.html",
        {"request": request, "pw": pw, "study": study, "stats": stats},
    )


@router.put("/api/studies/{study_code}/status")
async def update_study_status(
    study_code: str,
    status: dict,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """更新问卷状态"""
    if not verify_admin(pw):
        raise HTTPException(status_code=401, detail="Unauthorized")

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    new_status = status.get("status")
    if new_status not in ["active", "paused", "archived"]:
        raise HTTPException(status_code=400, detail="无效的状态值")

    study.status = new_status
    service.db.commit()

    return {"success": True, "status": new_status}
