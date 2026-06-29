"""
管理后台路由 - 配置管理和数据导出
"""

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter,
    Request,
    Body,
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
import hmac
import hashlib
import time
from apscheduler.triggers.cron import CronTrigger
from app.database import get_db
from app.config import get_settings
from app.schemas import StudyConfigData
from app.services.study import StudyService
from app.services.stats import StatsService
from app.services.export import export_manager
from app.services.cleanup import CleanupService, run_cleanup_job
from app.services.cleanup_strategies import strategy_manager, StrategyType
from app.services.zip_handler import ZipHandler, EMOTION_CN_MAP
from app.services import translation_db
from app.template_manager import get_templates

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

# Session cookie 有效期：7 天
SESSION_MAX_AGE = 60 * 60 * 24 * 7
SESSION_COOKIE_NAME = "admin_session"


def _resolve_study_config(study_code: Optional[str], service: StudyService) -> Optional[StudyConfigData]:
    """根据 study_code 解析问卷配置。有 study_code 则查指定问卷，否则用全局激活配置。"""
    if study_code:
        study = service.get_study_by_code(study_code)
        if study:
            config = service.get_study_config(study)
            if config:
                return config
    return service.get_active_config()


def _resolve_study_id(study_code: Optional[str], service: StudyService) -> Optional[str]:
    """根据 study_code 解析 study_id。返回 None 表示无法定位到具体问卷。"""
    if study_code:
        study = service.get_study_by_code(study_code)
        if study:
            return study.id
    return None


def verify_admin(password: Optional[str] = None) -> bool:
    """通过密码直接验证（API 调用后备）"""
    if not password:
        return False
    settings = get_settings()
    return password == settings.ADMIN_PASSWORD


def _create_session_token() -> str:
    """生成签名的会话令牌：timestamp:signature"""
    settings = get_settings()
    ts = str(int(time.time()))
    msg = f"{settings.ADMIN_PASSWORD}:{ts}"
    sig = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{ts}:{sig}"


def _verify_session_token(token: str) -> bool:
    """验证会话令牌是否有效且在有效期内"""
    settings = get_settings()
    try:
        parts = token.split(":", 1)
        if len(parts) != 2:
            return False
        ts_str, sig = parts
        ts = int(ts_str)

        # 检查是否过期
        if time.time() - ts > SESSION_MAX_AGE:
            return False

        # 验证签名
        msg = f"{settings.ADMIN_PASSWORD}:{ts_str}"
        expected = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            msg.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(sig, expected)
    except (ValueError, TypeError):
        return False


def verify_admin_session(request: Request) -> bool:
    """通过 Cookie 会话验证（浏览器登录）"""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        return False
    return _verify_session_token(cookie)


def verify_admin_or_401(request: Request, pw: Optional[str] = None) -> None:
    """统一的验证入口：先查 Cookie，再查 pw 参数。未通过则 401。"""
    if verify_admin_session(request):
        return
    if verify_admin(pw):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_admin_or_login(
    request: Request, pw: Optional[str] = None
) -> Optional[HTMLResponse]:
    """验证并返回登录页（用于 HTML 页面路由）。None = 验证通过。"""
    if verify_admin_session(request):
        return None
    if verify_admin(pw):
        return None
    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {"request": request, "error": "密码错误，请重试" if pw else None},
        status_code=401 if pw else 200,
    )


def get_study_service(db: Session = Depends(get_db)) -> StudyService:
    return StudyService(db)


def get_stats_service(db: Session = Depends(get_db)) -> StatsService:
    return StatsService(db)


@router.get("/", response_class=HTMLResponse)
async def admin_index(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """管理后台首页"""
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    config = _resolve_study_config(study_code, service)
    config_text = (
        json.dumps(config.model_dump(), ensure_ascii=False, indent=2)
        if config
        else "未加载"
    )

    return get_templates().TemplateResponse(
        request,
        "admin.html",
        {"request": request, "config_text": config_text, "study_code": study_code or ""},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return get_templates().TemplateResponse(
        request,
        "admin_login.html",
        {"request": request, "error": None},
    )


@router.post("/login")
async def login(request: Request, password: str = Form(...)):
    """处理登录请求"""
    if not verify_admin(password):
        return get_templates().TemplateResponse(
            request,
            "admin_login.html",
            {"request": request, "error": "密码错误，请重试"},
            status_code=401,
        )

    token = _create_session_token()
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # 本地开发用 HTTP
    )
    return response


@router.post("/logout")
async def logout():
    """登出"""
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/upload-config")
async def upload_config(
    request: Request,
    pw: Optional[str] = Form(None),
    configfile: UploadFile = File(...),
    service: StudyService = Depends(get_study_service),
):
    """上传研究配置"""
    verify_admin_or_401(request, pw)

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

        return RedirectResponse(url="/admin/", status_code=303)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/analysis", response_class=HTMLResponse)
async def analysis_page(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """数据分析页面"""
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    config = None
    if study_code:
        study = service.get_study_by_code(study_code)
        if study:
            config = service.get_study_config(study)
    if not config:
        config = service.get_active_config()
    title = config.title if config else "User Study"

    return get_templates().TemplateResponse(
        request, "analysis.html", {"request": request, "title": title, "study_code": study_code or ""}
    )


@router.get("/stats")
async def get_stats(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取统计数据 (JSON)"""
    verify_admin_or_401(request, pw)

    config = _resolve_study_config(study_code, service)
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    study_id = _resolve_study_id(study_code, service)
    stats = stats_service.get_overall_stats(config, study_id)
    return stats


@router.get("/dashboard")
async def get_dashboard(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取仪表盘数据"""
    verify_admin_or_401(request, pw)

    study_id = _resolve_study_id(study_code, service)
    dashboard_data = stats_service.get_dashboard_stats(study_id)
    return dashboard_data


@router.get("/chart-data")
async def get_chart_data(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取图表数据"""
    verify_admin_or_401(request, pw)

    config = _resolve_study_config(study_code, service)
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    study_id = _resolve_study_id(study_code, service)
    chart_data = stats_service.get_chart_data(config, study_id)
    return chart_data


@router.get("/detailed-analysis")
async def get_detailed_analysis(
    request: Request,
    pw: Optional[str] = None,
    study_code: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
    stats_service: StatsService = Depends(get_stats_service),
):
    """获取详细分析数据"""
    import numpy as np
    from collections import defaultdict

    verify_admin_or_401(request, pw)

    config = _resolve_study_config(study_code, service)
    if not config:
        raise HTTPException(status_code=500, detail="No config loaded")

    study_id = _resolve_study_id(study_code, service)

    # 获取基本统计
    overall_stats = stats_service.get_overall_stats(config, study_id)

    # 获取一致性分析
    consistency_analysis = stats_service.get_participant_consistency_analysis(config, study_id)

    # 计算详细的偏好分析
    model_stats = sorted(
        overall_stats.per_model, key=lambda x: x.total_picks, reverse=True
    )

    # 从配置中动态获取所有模型名称（避免硬编码遗漏）
    all_models = sorted({m for q in config.questions for m in q.models})

    # 计算每个用户的偏好率（用于计算标准差和百分位数）
    from app.models import Participant, Response, Study

    # 获取已完成的参与者（按 study_id 过滤）
    cp_q = stats_service.db.query(Participant).filter(Participant.completed_at.isnot(None))
    if study_id:
        cp_q = cp_q.filter(Participant.study_id == study_id)
    completed_participants = cp_q.all()

    user_cnt = len(completed_participants)

    # 初始化用户偏好数据
    user_emo_prefs = {model: [] for model in all_models}
    user_content_prefs = {model: [] for model in all_models}
    user_consistency_rates = {model: [] for model in all_models}

    # 统计情感和内容问题数量
    num_emo_questions = sum(1 for q in config.questions if q.id.endswith("-1"))
    num_content_questions = sum(1 for q in config.questions if q.id.endswith("-2"))

    # 批量查询所有已完成参与者的 responses（避免 N+1）
    participant_ids = [p.id for p in completed_participants]
    all_responses = (
        (
            stats_service.db.query(Response)
            .filter(Response.participant_id.in_(participant_ids))
            .all()
        )
        if participant_ids
        else []
    )

    # 按 participant_id 分组
    response_groups = defaultdict(list)
    for r in all_responses:
        response_groups[r.participant_id].append(r)

    # 计算每个用户的偏好率
    for participant in completed_participants:
        responses = response_groups.get(participant.id, [])

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
    request: Request,
    pw: Optional[str] = Form(None),
    background: bool = Form(True),  # 是否异步导出
):
    """启动数据导出"""
    verify_admin_or_401(request, pw)

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
async def check_export_status(request: Request, task_id: str, pw: Optional[str] = None):
    """检查导出任务状态"""
    verify_admin_or_401(request, pw)

    task = export_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.get("/export/{task_id}/download")
async def download_export(request: Request, task_id: str, pw: Optional[str] = None):
    """下载导出文件"""
    verify_admin_or_401(request, pw)

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
async def preview_cleanup(
    request: Request, pw: Optional[str] = None, zero_hours: int = 24
):
    """预览将要清理的数据（不实际删除）"""
    verify_admin_or_401(request, pw)

    service = CleanupService()
    try:
        preview = service.get_cleanup_preview(zero_hours)
        return preview
    finally:
        service.close()


@router.post("/cleanup/run")
async def run_cleanup_api(
    request: Request, pw: Optional[str] = Form(None), zero_hours: int = Form(24)
):
    """手动执行数据清理"""
    verify_admin_or_401(request, pw)

    result = run_cleanup_job(zero_hours)
    return result


@router.get("/cleanup/schedule")
async def get_cleanup_schedule(request: Request, pw: Optional[str] = None):
    """获取清理任务的定时计划"""
    verify_admin_or_401(request, pw)

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
    request: Request,
    pw: Optional[str] = Form(None),
    zero_hours: int = Form(24),
    hour: int = Form(2),
    minute: int = Form(0),
):
    """更新定时清理任务的参数"""
    verify_admin_or_401(request, pw)

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
async def get_available_strategies(request: Request, pw: Optional[str] = None):
    """获取所有可用的清理策略类型"""
    verify_admin_or_401(request, pw)

    strategies = strategy_manager.get_available_strategies()
    custom_strategies = strategy_manager.get_custom_strategies()

    return {"built_in": strategies, "custom": custom_strategies}


@router.post("/cleanup/strategies/custom")
async def create_custom_strategy(
    request: Request,
    pw: Optional[str] = Form(None),
    name: str = Form(...),
    description: str = Form(...),
    strategy_type: str = Form(...),
    params: str = Form(...),  # JSON字符串
):
    """创建自定义清理策略"""
    verify_admin_or_401(request, pw)

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
    request: Request,
    pw: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
    enabled: Optional[bool] = Form(None),
):
    """更新自定义策略"""
    verify_admin_or_401(request, pw)

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
async def delete_custom_strategy(
    strategy_id: str, request: Request, pw: Optional[str] = Form(None)
):
    """删除自定义策略"""
    verify_admin_or_401(request, pw)

    success = strategy_manager.delete_custom_strategy(strategy_id)

    if not success:
        raise HTTPException(status_code=404, detail="策略未找到")

    return {"status": "deleted", "strategy_id": strategy_id}


@router.post("/cleanup/strategies/{strategy_id}/preview")
async def preview_strategy(
    strategy_id: str,
    request: Request,
    pw: Optional[str] = Form(None),
    params: str = Form(...),  # JSON字符串
):
    """预览策略执行结果"""
    verify_admin_or_401(request, pw)

    try:
        import json

        params_dict = json.loads(params)

        result = strategy_manager.preview_strategy(strategy_id, params_dict)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cleanup/strategies/{strategy_id}/execute")
async def execute_strategy(
    strategy_id: str,
    request: Request,
    pw: Optional[str] = Form(None),
    params: Optional[str] = Form(None),
):
    """执行指定策略"""
    verify_admin_or_401(request, pw)

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


# ==================== Zip 上传创建问卷 ====================


@router.post("/studies/upload-zip")
async def upload_zip(
    request: Request,
    zipfile: UploadFile = File(...),
    emotion: str = Form(None),
):
    """
    上传 zip 并返回分析结果。

    两阶段模式：
    - 不传 emotion → 仅检测情感类别，返回 {upload_id, emotions, emotion_cn_map}
    - 传 emotion → 分析该情感下的 prompt 结构，返回完整分析
    """
    verify_admin_or_401(request)

    if not zipfile.filename or not zipfile.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 文件")

    # 保存 zip 到临时文件
    import tempfile

    settings = get_settings()
    temp_dir = settings.upload_path / "_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".zip", dir=str(temp_dir)
    ) as tmp:
        content = await zipfile.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        handler = ZipHandler()
        result = handler.process_upload(tmp_path, emotion)

        # 阶段 1：仅检测情感类别
        if emotion is None:
            return result

        # 阶段 2：完整分析 - 合并翻译信息
        prompts_names = [p["name"] for p in result["prompts"]]
        existing_translations = translation_db.batch_get_translations(prompts_names)

        # 分离已缓存和缺失的 prompt
        translations = {}
        translation_sources = {}
        missing_prompts = []
        for p in prompts_names:
            cached = existing_translations.get(p)
            if cached:
                translations[p] = cached
                translation_sources[p] = "cache"
            else:
                missing_prompts.append(p)

        # 自动翻译缺失的 prompt
        if missing_prompts:
            from app.services.translator import get_translator

            auto_translator = get_translator()
            auto_results = auto_translator.batch_translate(missing_prompts)
            new_db_entries = {}
            for p in missing_prompts:
                auto_t = auto_results.get(p)
                if auto_t:
                    translations[p] = auto_t
                    translation_sources[p] = "auto"
                    new_db_entries[p] = auto_t
                else:
                    translations[p] = ""
                    translation_sources[p] = "none"

            # 持久化保存到翻译缓存文件
            if new_db_entries:
                translation_db.batch_add_translations(new_db_entries)

            none_count = sum(1 for s in translation_sources.values() if s == "none")
            if none_count == len(missing_prompts) and missing_prompts:
                logger.warning(f"upload_zip: MyMemory 翻译全部失败 ({len(missing_prompts)} 个 prompt)，"
                               f"可能是网络不通或 API 限流。失败的词: {missing_prompts[:5]}")
            elif missing_prompts:
                logger.info(f"upload_zip: 自动翻译 {len(new_db_entries)}/{len(missing_prompts)} 个新 prompt")

        result["translations"] = translations
        result["translation_sources"] = translation_sources

        return result
    finally:
        # 清理临时 zip
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.post("/studies/analyze-zip")
async def analyze_zip(
    request: Request,
    data: dict = Body(...),
):
    """
    对已解压的 zip 分析指定情感类别（不重新上传 zip）。

    支持两种模式：
    - 单情感: {upload_id: str, emotion: str}
    - 批量:   {upload_id: str, emotions: [str, ...]}

    批量模式下，所有情感共用一次翻译请求，避免重复调用 API。
    """
    verify_admin_or_401(request)

    upload_id = data.get("upload_id")
    emotion = data.get("emotion")
    emotions = data.get("emotions")

    if not upload_id:
        raise HTTPException(status_code=400, detail="缺少 upload_id")

    handler = ZipHandler()

    # ===== 批量模式 =====
    if emotions and isinstance(emotions, list):
        try:
            results, all_prompt_names = handler.analyze_emotions(upload_id, emotions)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # 一次性翻译所有唯一 prompt 名称
        existing_translations = translation_db.batch_get_translations(all_prompt_names)

        translations = {}
        translation_sources = {}
        missing_prompts = []
        for p in all_prompt_names:
            cached = existing_translations.get(p)
            if cached:
                translations[p] = cached
                translation_sources[p] = "cache"
            else:
                missing_prompts.append(p)

        if missing_prompts:
            from app.services.translator import get_translator

            auto_translator = get_translator()
            auto_results = auto_translator.batch_translate(missing_prompts)
            new_db_entries = {}
            for p in missing_prompts:
                auto_t = auto_results.get(p)
                if auto_t:
                    translations[p] = auto_t
                    translation_sources[p] = "auto"
                    new_db_entries[p] = auto_t
                else:
                    translations[p] = ""
                    translation_sources[p] = "none"

            if new_db_entries:
                translation_db.batch_add_translations(new_db_entries)

            none_count = sum(1 for s in translation_sources.values() if s == "none")
            if none_count == len(missing_prompts) and missing_prompts:
                logger.warning(f"analyze_zip(batch): MyMemory 翻译全部失败 ({len(missing_prompts)} 个 prompt)，"
                               f"可能是网络不通或 API 限流。失败的词: {missing_prompts[:5]}")
            elif missing_prompts:
                logger.info(f"analyze_zip(batch): 自动翻译 {len(new_db_entries)}/{len(missing_prompts)} 个新 prompt")

        # 将翻译结果分发到每个情感的结果中
        for r in results:
            if r.get("_error"):
                continue
            r["translations"] = {
                p["name"]: translations.get(p["name"], "")
                for p in r.get("prompts", [])
            }
            r["translation_sources"] = {
                p["name"]: translation_sources.get(p["name"], "none")
                for p in r.get("prompts", [])
            }

        return {"results": results, "batch": True}

    # ===== 单情感模式（兼容旧前端） =====
    if not emotion:
        raise HTTPException(status_code=400, detail="缺少 emotion 或 emotions")

    try:
        result = handler.analyze_emotion(upload_id, emotion)

        prompts_names = [p["name"] for p in result["prompts"]]
        existing_translations = translation_db.batch_get_translations(prompts_names)

        translations = {}
        translation_sources = {}
        missing_prompts = []
        for p in prompts_names:
            cached = existing_translations.get(p)
            if cached:
                translations[p] = cached
                translation_sources[p] = "cache"
            else:
                missing_prompts.append(p)

        if missing_prompts:
            from app.services.translator import get_translator

            auto_translator = get_translator()
            auto_results = auto_translator.batch_translate(missing_prompts)
            new_db_entries = {}
            for p in missing_prompts:
                auto_t = auto_results.get(p)
                if auto_t:
                    translations[p] = auto_t
                    translation_sources[p] = "auto"
                    new_db_entries[p] = auto_t
                else:
                    translations[p] = ""
                    translation_sources[p] = "none"

            if new_db_entries:
                translation_db.batch_add_translations(new_db_entries)

            none_count = sum(1 for s in translation_sources.values() if s == "none")
            if none_count == len(missing_prompts) and missing_prompts:
                logger.warning(f"analyze_zip(single): MyMemory 翻译全部失败 ({len(missing_prompts)} 个 prompt)，"
                               f"可能是网络不通或 API 限流。失败的词: {missing_prompts[:5]}")
            elif missing_prompts:
                logger.info(f"analyze_zip(single): 自动翻译 {len(new_db_entries)}/{len(missing_prompts)} 个新 prompt")

        result["translations"] = translations
        result["translation_sources"] = translation_sources

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/studies/preview/{upload_id}/{emotion}/{prompt}/{filename}")
async def preview_image(
    upload_id: str,
    emotion: str,
    prompt: str,
    filename: str,
    request: Request,
):
    """返回缩略图（用于确认页面预览）"""
    verify_admin_or_401(request)

    from PIL import Image
    from io import BytesIO
    from fastapi.responses import StreamingResponse

    handler = ZipHandler()
    file_path = handler.get_preview_image(upload_id, emotion, prompt, filename)

    if not file_path:
        raise HTTPException(status_code=404, detail="图片未找到")

    try:
        img = Image.open(file_path)
        # 生成缩略图（200x200）
        img.thumbnail((200, 200), Image.LANCZOS)

        # RGBA → RGB
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            img = background

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=80)
        buf.seek(0)

        return StreamingResponse(buf, media_type="image/jpeg")
    except Exception:
        raise HTTPException(status_code=500, detail="图片处理失败")


@router.post("/studies/confirm-zip")
async def confirm_zip(
    request: Request,
    data: dict = Body(...),
    service: StudyService = Depends(get_study_service),
):
    """确认方法映射，处理图片，生成问卷（支持多情感合并到一个 Study）"""
    verify_admin_or_401(request)

    from app.services.image_processor import ImageProcessor, ImageSettings
    import json as json_mod

    upload_id = data.get("upload_id")
    study_name = data.get("study_name", "")
    study_code = data.get("study_code", "")
    emotions = data.get("emotions", [])  # list of {emotion, emotion_cn, methods, prompt_translations}
    description = data.get("description", "")
    instructions_override = data.get("instructions", "")
    title_override = data.get("title", "User Study")
    question_types = data.get("question_types", ["emotion", "content"])
    save_translations = data.get("save_translations", True)
    image_settings_raw = data.get("image_settings", {})
    duplicate_action = data.get("duplicate_action", "rename")

    if not upload_id or not emotions:
        raise HTTPException(status_code=400, detail="缺少必要参数（upload_id 或 emotions）")

    handler = ZipHandler()

    # 图片处理设置
    img_settings = ImageSettings(
        compress=image_settings_raw.get("compress", True),
        max_size=image_settings_raw.get("max_size", 512),
        quality=image_settings_raw.get("quality", 85),
    )

    processor = ImageProcessor()
    settings_obj = get_settings()

    questions = []
    processed_count = 0
    skipped_count = 0
    skipped_details: list[dict] = []  # {file, reason}
    missing_count = 0
    missing_details: list[dict] = []  # {emotion, prompt, method, source}
    question_idx = 1
    all_translations = {}
    total_size_mb = 0.0

    for emotion_config in emotions:
        emotion = emotion_config.get("emotion", "")
        emotion_cn = emotion_config.get("emotion_cn", EMOTION_CN_MAP.get(emotion, emotion))
        methods = emotion_config.get("methods", [])
        prompt_translations = emotion_config.get("prompt_translations", {})

        if not emotion or not methods:
            continue

        # 获取情感子目录
        temp_dir = handler.get_temp_dir(upload_id, emotion)
        if not temp_dir.exists():
            continue

        # 构建 source → (method, variant) 映射
        method_map = {}
        for m in methods:
            method_map[m["source"]] = (m["method"], m.get("variant"))

        # 获取目录结构
        structure = handler._analyze_structure(str(temp_dir))
        if not structure:
            continue

        upload_base = settings_obj.upload_path / emotion

        for prompt_info in structure:
            prompt_name = prompt_info["name"]
            prompt_cn = prompt_translations.get(prompt_name) or prompt_name
            target_dir = upload_base / prompt_name

            images_in_order = []
            models_in_order = []

            for method_info in methods:
                source = method_info["source"]
                method_name = method_info["method"]
                variant = method_info.get("variant")

                if variant:
                    display_name = f"{method_name} ({variant})"
                else:
                    display_name = method_name

                found = False

                for img in prompt_info["images"]:
                    stem = os.path.splitext(img["filename"])[0]
                    # 与 _extract_methods 一致的匹配策略：优先用 _ 分割取最后一段
                    if "_" in stem:
                        candidate = stem.rsplit("_", 1)[1]
                    else:
                        # 没有 _ 时，用 prompt_name 定位边界
                        prompt_lower = prompt_name.lower().replace(" ", "")
                        stem_lower = stem.lower().replace(" ", "")
                        idx = stem_lower.rfind(prompt_lower)
                        candidate = stem[idx + len(prompt_lower):] if idx >= 0 else stem
                    if candidate == source:
                        found = True
                    elif method_name and (candidate == method_name):
                        # 文件名方法与候选 base method 匹配（如 pixart 匹配 method=pixart）
                        found = True
                    elif source.startswith(candidate + "-") or source.startswith(candidate + "_"):
                        # 文件名方法是 source 的前缀（如 pixart 匹配 pixart-lora）
                        found = True
                    if found:
                        source_file = str(temp_dir / prompt_name / img["filename"])
                        try:
                            new_filename = processor.process_image(
                                source_file,
                                str(target_dir),
                                method_name.lower().replace(" ", "_"),
                                img_settings,
                            )
                            images_in_order.append(
                                f"/uploads/{emotion}/{prompt_name}/{new_filename}"
                            )
                            models_in_order.append(display_name)
                            processed_count += 1
                        except Exception as e:
                            skipped_count += 1
                            skip_file = f"{emotion}/{prompt_name}/{img['filename']}"
                            skipped_details.append({
                                "file": skip_file,
                                "reason": str(e)[:120],
                            })
                            logger.warning(
                                f"图片处理失败 [{emotion}/{prompt_name}]: {img['filename']} - {e}"
                            )
                        break

                # 方法遍历完没找到匹配文件 → 记录缺失
                if not found:
                    missing_count += 1
                    missing_details.append({
                        "emotion": emotion,
                        "prompt": prompt_name,
                        "method": method_name,
                        "source": source,
                    })
                    logger.warning(
                        f"图片缺失 [{emotion}/{prompt_name}]: 方法 {method_name}(source={source}) 无匹配文件"
                    )

            if not images_in_order:
                continue

            # 生成问题（每个 prompt 生成情感题 + 内容题）
            for q_type in question_types:
                q_id = f"q{question_idx}-{1 if q_type == 'emotion' else 2}"

                if q_type == "emotion":
                    prompt_html = (
                        f"\n<strong>内容:</strong> '{prompt_name}' ({prompt_cn})<br>\n"
                        f"<strong>情感:</strong> '{emotion}' ({emotion_cn})\n"
                        f'<hr style="margin: 1rem 0;">\n'
                        f"请从以下图片中选择<strong>最能唤起'{emotion}'（{emotion_cn}）</strong>的一张。\n"
                    )
                else:
                    prompt_html = (
                        f"\n<strong>内容:</strong> '{prompt_name}' ({prompt_cn})<br>\n"
                        f"<strong>情感:</strong> '{emotion}' ({emotion_cn})\n"
                        f'<hr style="margin: 1rem 0;">\n'
                        f"请从以下图片中选择<strong>最符合内容描述</strong>（如果相差无几，请选择最能唤起'{emotion}'（{emotion_cn}））的一张。\n"
                    )

                questions.append(
                    {
                        "id": q_id,
                        "prompt": prompt_html,
                        "images": images_in_order,
                        "models": models_in_order,
                        "type": "choose_one",
                    }
                )

            question_idx += 1

        # 收集所有翻译
        for k, v in prompt_translations.items():
            if v.strip():
                all_translations[k] = v

    if not questions:
        handler.cleanup_temp(upload_id)
        raise HTTPException(status_code=400, detail="没有成功处理任何图片 — 请检查情感下的方法名是否与文件名匹配")

    # 构建 config.json
    default_instructions = (
        '我们的任务是"可控的情感图像内容生成"，旨在根据文本描述，生成不仅内容准确，'
        "而且能唤起指定情感体验的图像。\n\n"
        "在接下来的问卷中，每个问题会给出一个文本描述和目标情感，"
        "并展示由不同模型生成的多张图像。\n\n"
        "请您思考并回答以下问题：\n\n"
        "1. 哪张图最能让您感受到指定的情感？\n\n"
        "2. 哪张图最符合内容描述？\n\n"
        "本次实验预计耗时约10分钟，感谢您的认真参与！"
    )

    # 默认示例图——每个关注点一个分组，图文交错展示
    default_examples = [
        {
            "text": "关注点 1：内容表达准确性 — 图像是否与文字描述相符？画面中的物体、场景、细节是否准确呈现了 Prompt 的内容？",
            "images": [
                "/static/examples/example_good_content.png",
            ],
        },
        {
            "text": "关注点 2：情感表达一致性 — 图像是否成功传达了目标情感？颜色氛围、构图、人物表情等是否与目标情感一致？",
            "images": [
                "/static/examples/example_good_emotion.png",
            ],
        },
        {
            "text": "关注点 3：图像质量与 Prompt 清晰度 — 图像本身是否清晰？Prompt 的表达是否明确、可执行？",
            "images": [
                "/static/examples/example_clear_prompt.png",
            ],
        },
    ]

    config_dict = {
        "title": title_override or study_name,
        "instructions": instructions_override or default_instructions,
        "randomize": True,
        "examples": default_examples,
        "questions": questions,
    }

    # 重名处理
    if duplicate_action != "overwrite":
        existing = service.get_study_by_code(study_code) if study_code else None
        if existing:
            if duplicate_action == "abort":
                handler.cleanup_temp(upload_id)
                raise HTTPException(
                    status_code=409,
                    detail='{"error":"duplicate_name","existing":{"code":"%s","name":"%s"}}'
                    % (existing.code, existing.name),
                )
            elif duplicate_action == "rename":
                study_code = f"{study_code}_2"

    # 创建问卷
    try:
        config_data = StudyConfigData(**config_dict)

        study = service.create_study(
            name=study_name,
            config_data=config_data,
            description=description or study_name,
            custom_code=study_code or None,
        )

        # 保存翻译到词库
        if save_translations and all_translations:
            translation_db.batch_add_translations(all_translations)

        return {
            "success": True,
            "study": {
                "id": study.id,
                "code": study.code,
                "name": study.name,
                "question_count": len(questions),
                "total_size_mb": round(total_size_mb, 2),
            },
            "processed_images": processed_count,
            "skipped_images": skipped_count,
            "skipped_details": skipped_details[:20],  # 最多返回前 20 条，避免响应过大
            "missing_images": missing_count,
            "missing_details": missing_details[:20],
        }
    finally:
        # 无论成功或失败，都清理临时文件，避免 uploads/_temp 堆积
        handler.cleanup_temp(upload_id)


@router.post("/studies/translate-prompts")
async def llm_translate_prompts(
    request: Request,
    data: dict,
):
    """
    LLM 批量翻译 prompt 列表。
    此端点由 WorkBuddy LLM 在处理请求时完成翻译。
    如果 LLM 不可用，返回空结果让用户手动输入。
    """
    verify_admin_or_401(request)

    prompts = data.get("prompts", [])
    if not prompts:
        return {"translations": {}}

    # 注意：这个端点的实际翻译由 WorkBuddy LLM 完成。
    # 在非 LLM 环境下（如纯 FastAPI 运行），返回空结果。
    #
    # LLM 代理层会拦截此端点的响应，
    # 在返回前将 prompts 翻译并填充到 translations 字段。

    return {"translations": {}}


# ==================== 翻译词库管理 ====================


@router.get("/translations", response_class=HTMLResponse)
async def translations_page(request: Request):
    """翻译词库管理页面"""
    login_page = verify_admin_or_login(request)
    if login_page:
        return login_page

    return get_templates().TemplateResponse(
        request,
        "admin_translations.html",
        {"request": request},
    )


@router.get("/api/translations")
async def get_translations_api(request: Request):
    """获取全部翻译词条"""
    verify_admin_or_401(request)
    return translation_db.get_db_stats()


@router.post("/api/translations")
async def save_translations_api(request: Request, data: dict):
    """批量保存翻译词条"""
    verify_admin_or_401(request)

    translations = data.get("translations", {})
    if not translations:
        return {"success": True, "count": 0}

    updated = 0
    for prompt, chinese in translations.items():
        if chinese is None:
            translation_db.delete_translation(prompt)
        else:
            translation_db.add_translation(prompt, chinese)
            updated += 1

    return {"success": True, "count": updated}


@router.get("/api/translations/export")
async def export_translations_api(request: Request):
    """导出词库 JSON 文件"""
    verify_admin_or_401(request)

    db = translation_db.load_translation_db()
    import tempfile

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".json", mode="w", encoding="utf-8"
    ) as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
        tmp_path = f.name

    return FileResponse(
        path=tmp_path,
        filename="prompt_translations.json",
        media_type="application/json",
    )


@router.post("/api/translations/import")
async def import_translations_api(
    request: Request,
    file: UploadFile = File(...),
):
    """导入 JSON 文件合并到词库"""
    verify_admin_or_401(request)

    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 .json 文件")

    try:
        content = await file.read()
        imported = json.loads(content.decode("utf-8"))
        if not isinstance(imported, dict):
            raise ValueError("JSON 格式不正确，应为对象")

        # 合并到词库
        translation_db.batch_add_translations(imported)

        return {
            "success": True,
            "imported_count": len(imported),
            "total_count": len(translation_db.load_translation_db()),
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="无效的 JSON 格式")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ==================== 多问卷管理 API ====================


@router.get("/api/studies")
async def get_studies_api(
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """获取问卷列表 API"""
    verify_admin_or_401(request, pw)

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
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    studies = service.get_all_studies()
    return get_templates().TemplateResponse(
        request,
        "admin_studies.html",
        {"request": request, "studies": studies},
    )


@router.delete("/studies/{study_code}")
async def delete_study(
    study_code: str,
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """删除问卷及其所有数据"""
    verify_admin_or_401(request, pw)

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    success = service.delete_study(study.id)
    if not success:
        raise HTTPException(status_code=500, detail="删除失败")

    return {"status": "deleted", "message": f"问卷「{study.name}」已删除"}


@router.get("/studies/create", response_class=HTMLResponse)
async def create_study_page(request: Request, pw: Optional[str] = None):
    """创建问卷页面"""
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    return get_templates().TemplateResponse(
        request, "admin_study_create.html", {"request": request}
    )


@router.get("/studies/zip-create", response_class=HTMLResponse)
async def zip_create_page(request: Request, pw: Optional[str] = None):
    """Zip 上传创建问卷页面"""
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    return get_templates().TemplateResponse(
        request, "admin_zip_create.html", {"request": request}
    )


@router.post("/studies/create")
async def create_study(
    request: Request,
    pw: Optional[str] = Form(None),
    name: str = Form(...),
    code: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    configfile: UploadFile = File(...),
    service: StudyService = Depends(get_study_service),
):
    """创建问卷"""
    verify_admin_or_401(request, pw)

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

        return RedirectResponse(url="/admin/studies", status_code=303)
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
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    stats = service.get_study_stats(study.id)

    return get_templates().TemplateResponse(
        request,
        "admin_study_detail.html",
        {"request": request, "study": study, "stats": stats},
    )


@router.get("/study/{study_code}/edit", response_class=HTMLResponse)
async def study_edit_page(
    request: Request,
    study_code: str,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """问卷配置编辑页面"""
    login_page = verify_admin_or_login(request, pw)
    if login_page:
        return login_page

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    return get_templates().TemplateResponse(
        request,
        "admin_study_edit.html",
        {"request": request, "study": study},
    )


@router.post("/upload-example-image")
async def upload_example_image(
    request: Request,
    file: UploadFile = File(...),
    pw: Optional[str] = None,
):
    """上传示例图片到 static/examples/ 目录"""
    verify_admin_or_401(request, pw)

    settings_obj = get_settings()
    examples_dir = settings_obj.static_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)

    # 检查文件类型
    ext = os.path.splitext(file.filename or "image.png")[1].lower()
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，仅支持 {', '.join(allowed)}")

    # 生成唯一文件名（保留原始扩展名）
    safe_name = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}{ext}"
    dest_path = examples_dir / safe_name

    try:
        contents = await file.read()
        dest_path.write_bytes(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {str(e)}")

    url = f"/static/examples/{safe_name}"
    logger.info(f"示例图片已上传: {url}")
    return {"success": True, "url": url, "filename": safe_name}


@router.put("/api/studies/{study_code}/status")
async def update_study_status(
    study_code: str,
    status: dict,
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """更新问卷状态"""
    verify_admin_or_401(request, pw)

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    new_status = status.get("status")
    if new_status not in ["active", "paused", "archived"]:
        raise HTTPException(status_code=400, detail="无效的状态值")

    study.status = new_status
    service.db.commit()

    return {"success": True, "status": new_status}


# ==================== 问卷配置编辑 ====================

@router.get("/api/studies/{study_code}/config")
async def get_study_config_for_edit(
    study_code: str,
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """获取问卷配置用于编辑"""
    verify_admin_or_401(request, pw)

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    try:
        config = json.loads(study.config_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="config_json 解析失败")

    stats = service.get_study_stats(study.id)
    has_responses = stats.get("total_responses", 0) > 0

    return {
        "success": True,
        "study": {
            "id": study.id,
            "code": study.code,
            "name": study.name,
            "description": study.description or "",
            "status": study.status,
        },
        "config": config,
        "has_responses": has_responses,
        "participant_count": stats.get("total_participants", 0),
        "response_count": stats.get("total_responses", 0),
    }


@router.put("/api/studies/{study_code}/config")
async def update_study_config(
    study_code: str,
    config_update: dict,
    request: Request,
    pw: Optional[str] = None,
    service: StudyService = Depends(get_study_service),
):
    """更新问卷配置"""
    verify_admin_or_401(request, pw)

    study = service.get_study_by_code(study_code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    # 解析现有配置
    try:
        existing_config = json.loads(study.config_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="现有 config_json 解析失败")

    stats = service.get_study_stats(study.id)
    has_responses = stats.get("total_responses", 0) > 0

    # 构建更新后的配置
    new_config = {
        "title": config_update.get("title", existing_config.get("title", "")),
        "instructions": config_update.get("instructions", existing_config.get("instructions", "")),
        "randomize": config_update.get("randomize", existing_config.get("randomize", True)),
        "examples": config_update.get("examples", existing_config.get("examples", [])),
    }

    # 问题处理
    new_questions = config_update.get("questions")
    if has_responses:
        # 有回答的问卷：保持原 questions 不变
        new_config["questions"] = existing_config.get("questions", [])
        # 如果前端尝试发送不同的 questions，记录警告但不报错
        if new_questions is not None:
            existing_ids = [q.get("id") for q in existing_config.get("questions", [])]
            new_ids = [q.get("id") for q in new_questions]
            if existing_ids != new_ids:
                logger.warning(
                    f"有人尝试修改有回答问卷 {study_code} 的题目（{len(new_ids)} vs {len(existing_ids)} 题），已忽略"
                )
    else:
        # 无回答的问卷：验证问题结构
        if new_questions is None or len(new_questions) == 0:
            raise HTTPException(status_code=400, detail="问题列表不能为空")
        new_config["questions"] = new_questions

    # 更新名称和描述
    if "name" in config_update and config_update["name"]:
        study.name = config_update["name"]
    if "description" in config_update and config_update["description"] is not None:
        study.description = config_update["description"]

    # 验证并保存配置
    try:
        config_data = StudyConfigData(**new_config)
        study.config_json = json.dumps(config_data.model_dump(), ensure_ascii=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"配置验证失败: {str(e)}")

    study.updated_at = datetime.utcnow()
    service.db.commit()

    return {
        "success": True,
        "message": "配置已保存",
        "questions_locked": has_responses,
    }
