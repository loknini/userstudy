"""
公共路由 - 问卷页面和答题逻辑
"""

from typing import Optional

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import get_settings
from app.schemas import ParticipantCreate, AnswerSubmit, AnswerResult
from app.services.study import StudyService
from app.utils.short_code import normalize_short_code
from app.template_manager import get_templates

router = APIRouter(tags=["public"])


def get_study_service(db: Session = Depends(get_db)) -> StudyService:
    """获取研究服务依赖"""
    return StudyService(db)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, service: StudyService = Depends(get_study_service)):
    """首页 - 问卷代码输入"""
    templates = get_templates()
    return templates.TemplateResponse(request, "index.html", {"request": request})


# ==================== 多问卷路由（新） ====================


@router.get("/study/{study_code}", response_class=HTMLResponse)
async def study_index(
    request: Request,
    study_code: str,
    service: StudyService = Depends(get_study_service),
):
    """问卷首页 - 实验说明"""
    # 规范化短代码
    code = normalize_short_code(study_code)

    # 获取问卷
    study = service.get_study_by_code(code)
    if not study:
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "error_title": "问卷不存在",
                "error_message": f"问卷代码 '{study_code}' 不存在，请检查后重试。",
                "back_url": "/",
            },
            status_code=404,
        )

    if study.status != "active":
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "error_title": "问卷不可用",
                "error_message": "该问卷未激活或已暂停，请联系管理员。",
                "back_url": "/",
            },
            status_code=403,
        )

    # 获取配置
    config = service.get_study_config(study)
    if not config:
        templates = get_templates()
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "request": request,
                "error_title": "配置加载失败",
                "error_message": "问卷配置加载失败，请联系管理员。",
                "back_url": "/",
            },
            status_code=500,
        )

    templates = get_templates()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "study": study,
            "title": config.title,
            "instructions": config.instructions,
            "examples": config.examples,
            "study_code": code,
        },
    )


@router.post("/study/{study_code}/start")
async def start_study_by_code(
    request: Request,
    study_code: str,
    service: StudyService = Depends(get_study_service),
):
    """开始实验（指定问卷）- 创建参与者并重定向到第一题"""
    # 规范化短代码
    code = normalize_short_code(study_code)

    # 获取问卷
    study = service.get_study_by_code(code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    if study.status != "active":
        raise HTTPException(status_code=403, detail="问卷未激活")

    # 获取客户端信息
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # 创建参与者（关联到问卷）
    participant_data = ParticipantCreate(ip_address=ip_address, user_agent=user_agent)
    participant = service.create_participant(participant_data, study_id=study.id)

    # 重定向到第一题
    return RedirectResponse(
        url=f"/study/{code}/question/0?pid={participant.id}", status_code=303
    )


@router.get("/study/{study_code}/question/{qidx}", response_class=HTMLResponse)
async def show_question_by_code(
    request: Request,
    study_code: str,
    qidx: int,
    pid: str,  # participant_id
    service: StudyService = Depends(get_study_service),
):
    """显示问题页面（指定问卷）"""
    # 规范化短代码
    code = normalize_short_code(study_code)

    # 获取问卷
    study = service.get_study_by_code(code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    # 验证参与者（必须属于该问卷）
    participant = service.get_participant(pid, study_id=study.id)
    if not participant:
        raise HTTPException(status_code=404, detail="参与者不存在或无权访问此问卷")

    # 获取配置
    config = service.get_study_config(study)
    if not config:
        raise HTTPException(status_code=500, detail="配置未加载")

    # 获取问题数据
    question_data = service.get_question_data(qidx, pid, config)
    templates = get_templates()
    if not question_data:
        # 所有问题完成
        return templates.TemplateResponse(
            request,
            "completed.html",
            {"request": request, "study": study, "title": config.title},
        )

    return templates.TemplateResponse(
        request,
        "question.html",
        {
            "request": request,
            "study": study,
            "study_code": code,
            **question_data.model_dump(),
        },
    )


@router.post("/study/{study_code}/submit/{qidx}")
async def submit_answer_by_code(
    study_code: str,
    qidx: int,
    participant_id: str = Form(...),
    question_id: str = Form(...),
    selected_index: int = Form(...),
    rating: Optional[int] = Form(None),
    comment: Optional[str] = Form(None),
    time_spent: Optional[float] = Form(None),
    service: StudyService = Depends(get_study_service),
):
    """提交答案（指定问卷）"""
    # 规范化短代码
    code = normalize_short_code(study_code)

    # 获取问卷
    study = service.get_study_by_code(code)
    if not study:
        raise HTTPException(status_code=404, detail="问卷不存在")

    # 获取配置
    config = service.get_study_config(study)
    if not config:
        raise HTTPException(status_code=500, detail="配置未加载")

    # 构建提交数据
    answer_data = AnswerSubmit(
        participant_id=participant_id,
        question_id=question_id,
        selected_index=selected_index,
        rating=rating,
        comment=comment,
        time_spent=time_spent,
    )

    # 提交答案（传入study_id进行验证）
    result = service.submit_answer(qidx, answer_data, config, study_id=study.id)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    if result.is_completed:
        # 完成所有问题
        return RedirectResponse(url=f"/study/{code}/completed", status_code=303)

    # 继续下一题
    return RedirectResponse(
        url=f"/study/{code}/question/{result.next_question_idx}?pid={participant_id}",
        status_code=303,
    )


@router.get("/study/{study_code}/completed", response_class=HTMLResponse)
async def study_completed_by_code(
    request: Request,
    study_code: str,
    service: StudyService = Depends(get_study_service),
):
    """完成页面（指定问卷）"""
    code = normalize_short_code(study_code)

    study = service.get_study_by_code(code)
    config = service.get_study_config(study) if study else None
    title = config.title if config else "User Study"

    templates = get_templates()
    return templates.TemplateResponse(
        request, "completed.html", {"request": request, "study": study, "title": title}
    )


# ==================== 旧路由（向后兼容） ====================


@router.post("/start")
async def start_study_legacy(
    request: Request, service: StudyService = Depends(get_study_service)
):
    """开始实验（向后兼容）- 重定向到默认问卷"""
    # 重定向到新的问卷路由（使用默认问卷代码）
    return RedirectResponse(
        url="/study/default/start",
        status_code=307,  # 307保持POST方法
    )


@router.get("/question/{qidx}", response_class=HTMLResponse)
async def show_question_legacy(
    request: Request,
    qidx: int,
    pid: str,
    service: StudyService = Depends(get_study_service),
):
    """显示问题页面（向后兼容）- 重定向到默认问卷"""
    return RedirectResponse(
        url=f"/study/default/question/{qidx}?pid={pid}", status_code=301
    )


@router.post("/submit/{qidx}")
async def submit_answer_legacy(
    qidx: int,
    participant_id: str = Form(...),
    question_id: str = Form(...),
    selected_index: int = Form(...),
    rating: Optional[int] = Form(None),
    comment: Optional[str] = Form(None),
    time_spent: Optional[float] = Form(None),
):
    """提交答案（向后兼容）- 重定向到默认问卷"""
    # POST重定向需要307保持方法
    return RedirectResponse(url=f"/study/default/submit/{qidx}", status_code=307)


@router.get("/completed", response_class=HTMLResponse)
async def study_completed_legacy(
    request: Request, service: StudyService = Depends(get_study_service)
):
    """完成页面（向后兼容）- 重定向到默认问卷"""
    return RedirectResponse(url="/study/default/completed", status_code=301)
