"""
FastAPI 应用入口
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.database import init_db
from app.routers import public, admin, api
from app.services.cleanup import run_cleanup_job


class CachedStaticFiles(StaticFiles):
    """带缓存控制的静态文件服务"""

    def __init__(self, directory: str, cache_max_age: int = 604800):
        super().__init__(directory=directory)
        self.cache_max_age = cache_max_age

    async def get_response(self, path: str, scope):
        """重写响应方法，添加缓存头"""
        response = await super().get_response(path, scope)

        # 添加缓存控制头
        if hasattr(response, "headers"):
            response.headers["Cache-Control"] = f"public, max-age={self.cache_max_age}"

        return response


# 全局调度器实例
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global scheduler

    # 启动时执行
    settings = get_settings()

    # 确保必要目录存在
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.static_path.mkdir(parents=True, exist_ok=True)
    (settings.BASE_DIR / "exports").mkdir(parents=True, exist_ok=True)

    # 初始化数据库
    init_db()

    # 启动定时任务调度器
    scheduler = BackgroundScheduler()

    # 每天凌晨2点执行数据清理
    scheduler.add_job(
        run_cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="cleanup_job",
        name="数据清理任务",
        replace_existing=True,
    )

    # 也可以添加一个测试任务（每5分钟执行一次，仅调试用）
    # scheduler.add_job(
    #     run_cleanup_job,
    #     trigger='interval',
    #     minutes=5,
    #     id='cleanup_test',
    #     name='数据清理测试'
    # )

    scheduler.start()
    print(f"⏰ 定时任务已启动，每天凌晨2:00执行数据清理")

    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动成功！")
    print(f"📊 管理后台: http://{settings.HOST}:{settings.PORT}/admin")
    print(f"📚 API 文档: http://{settings.HOST}:{settings.PORT}/docs")

    yield

    # 关闭时执行
    if scheduler:
        scheduler.shutdown()
        print("⏰ 定时任务已停止")
    print("👋 应用关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="可控情感图像内容生成 - 用户研究平台",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # 中间件
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # 生产环境关闭 CORS
    if settings.DEBUG:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # 静态文件服务（带缓存控制）
    app.mount(
        "/static", CachedStaticFiles(directory=str(settings.static_path)), name="static"
    )
    app.mount(
        "/uploads",
        CachedStaticFiles(directory=str(settings.upload_path)),
        name="uploads",
    )

    # 注册路由
    app.include_router(public.router)
    app.include_router(admin.router)
    app.include_router(api.router)

    return app


# 应用实例（用于导入）
app = create_app()
