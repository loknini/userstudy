"""
API 路由 - RESTful API 接口
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.schemas import (
    ResponseBase, ParticipantOut, ResponseOut, 
    OverallStats, ChartDataSet, ExportTask
)
from app.services.study import StudyService
from app.services.stats import StatsService
from app.services.export import export_manager

router = APIRouter(prefix="/api", tags=["api"])
settings = get_settings()


def verify_api_key(api_key: Optional[str] = None) -> bool:
    """验证 API 密钥（简化版，使用 admin 密码）"""
    if not api_key:
        return False
    return api_key == settings.ADMIN_PASSWORD


def verify_api_or_session(request: Request, api_key: Optional[str] = None) -> bool:
    """验证 API 密钥或 Cookie 会话"""
    if verify_api_key(api_key):
        return True
    # 导入 admin 模块的 session 验证
    from app.routers.admin import verify_admin_session
    return verify_admin_session(request)


def require_api_auth(request: Request, api_key: Optional[str] = None):
    """统一验证入口"""
    if not verify_api_or_session(request, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "version": settings.APP_VERSION}


@router.get("/config")
async def get_config(
    request: Request,
    api_key: Optional[str] = Query(None),
    service: StudyService = Depends(lambda db: StudyService(db))
):
    """获取当前研究配置"""
    require_api_auth(request, api_key)
    
    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=404, detail="No config loaded")
    
    return ResponseBase(data=config.model_dump())


@router.get("/participants", response_model=ResponseBase)
async def list_participants(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    completed_only: bool = Query(False),
    api_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取参与者列表"""
    require_api_auth(request, api_key)
    
    from app.models import Participant
    
    query = db.query(Participant)
    if completed_only:
        query = query.filter(Participant.completed_at.isnot(None))
    
    total = query.count()
    participants = query.offset(skip).limit(limit).all()
    
    return ResponseBase(data={
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [ParticipantOut.model_validate(p).model_dump() for p in participants]
    })


@router.get("/participants/{participant_id}")
async def get_participant_detail(
    request: Request,
    participant_id: str,
    api_key: Optional[str] = Query(None),
    service: StudyService = Depends(lambda db: StudyService(db)),
    db: Session = Depends(get_db)
):
    """获取参与者详情"""
    require_api_auth(request, api_key)
    
    participant = service.get_participant(participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    
    return ResponseBase(data=ParticipantOut.model_validate(participant).model_dump())


@router.get("/responses")
async def list_responses(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    participant_id: Optional[str] = Query(None),
    question_id: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """获取响应列表"""
    require_api_auth(request, api_key)
    
    from app.models import Response
    
    query = db.query(Response)
    if participant_id:
        query = query.filter(Response.participant_id == participant_id)
    if question_id:
        query = query.filter(Response.question_id == question_id)
    
    total = query.count()
    responses = query.order_by(Response.created_at.desc()).offset(skip).limit(limit).all()
    
    return ResponseBase(data={
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [ResponseOut.model_validate(r).model_dump() for r in responses]
    })


@router.get("/stats/overall")
async def get_overall_stats(
    request: Request,
    api_key: Optional[str] = Query(None),
    service: StudyService = Depends(lambda db: StudyService(db)),
    stats_service: StatsService = Depends(lambda db: StatsService(db))
):
    """获取整体统计数据"""
    require_api_auth(request, api_key)
    
    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=404, detail="No config loaded")
    
    stats = stats_service.get_overall_stats(config)
    return ResponseBase(data=stats.model_dump())


@router.get("/stats/charts")
async def get_chart_data(
    request: Request,
    api_key: Optional[str] = Query(None),
    service: StudyService = Depends(lambda db: StudyService(db)),
    stats_service: StatsService = Depends(lambda db: StatsService(db))
):
    """获取图表数据"""
    require_api_auth(request, api_key)
    
    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=404, detail="No config loaded")
    
    chart_data = stats_service.get_chart_data(config)
    return ResponseBase(data=chart_data.model_dump())


@router.get("/stats/consistency")
async def get_consistency_analysis(
    request: Request,
    api_key: Optional[str] = Query(None),
    service: StudyService = Depends(lambda db: StudyService(db)),
    stats_service: StatsService = Depends(lambda db: StatsService(db))
):
    """获取一致性分析数据"""
    require_api_auth(request, api_key)
    
    config = service.get_active_config()
    if not config:
        raise HTTPException(status_code=404, detail="No config loaded")
    
    analysis = stats_service.get_participant_consistency_analysis(config)
    return ResponseBase(data=analysis)


@router.post("/export", response_model=ResponseBase)
async def create_export_task(
    request: Request,
    api_key: Optional[str] = Query(None),
    fmt: Optional[str] = Query("responses", description="导出格式: responses=长格式, participants=宽表")
):
    """创建导出任务"""
    require_api_auth(request, api_key)
    
    if fmt not in ("responses", "participants"):
        raise HTTPException(status_code=400, detail="无效的格式参数，可选: responses, participants")
    
    task_id = export_manager.create_task()
    export_manager.start_export_csv(task_id, settings.BASE_DIR / "exports", fmt=fmt)
    
    return ResponseBase(data={"task_id": task_id, "status": "processing", "format": fmt})


@router.get("/export/{task_id}")
async def get_export_task(
    request: Request,
    task_id: str,
    api_key: Optional[str] = Query(None)
):
    """获取导出任务状态"""
    require_api_auth(request, api_key)
    
    task = export_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return ResponseBase(data=task)
