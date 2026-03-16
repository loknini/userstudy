"""
应用启动脚本
支持多种服务器后端
"""
import sys
import argparse


def run_development():
    """开发模式 - 使用 Uvicorn（单进程，支持热重载）"""
    import uvicorn
    from app.config import get_settings
    
    settings = get_settings()
    
    print("🔄 启动开发服务器（热重载已启用）...")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level="info"
    )


def run_production():
    """生产模式 - 使用 Uvicorn（多进程，高性能）"""
    import uvicorn
    from app.config import get_settings
    
    settings = get_settings()
    
    print("🚀 启动生产服务器...")
    print(f"   工作进程数: {settings.WORKERS}")
    print(f"   监听地址: {settings.HOST}:{settings.PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        workers=settings.WORKERS,
        log_level="warning",
        access_log=False
    )


def run_hypercorn():
    """使用 Hypercorn（支持 HTTP/2 和 ASGI 3）"""
    try:
        import asyncio
        from hypercorn.config import Config
        from hypercorn.asyncio import serve
        from app.main import app
        from app.config import get_settings
        
        settings = get_settings()
        
        config = Config()
        config.bind = [f"{settings.HOST}:{settings.PORT}"]
        config.workers = settings.WORKERS
        config.accesslog = "-"
        
        print("🚀 使用 Hypercorn 启动...")
        asyncio.run(serve(app, config))
    except ImportError:
        print("❌ 请先安装 hypercorn: pip install hypercorn")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="User Study Platform")
    parser.add_argument(
        "--mode",
        choices=["dev", "prod", "hypercorn"],
        default="dev",
        help="运行模式 (dev: 开发模式带热重载, prod: 生产多进程, hypercorn: 使用 Hypercorn)"
    )
    parser.add_argument(
        "--host",
        default=None,
        help="监听地址 (默认: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="监听端口 (默认: 8888)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="工作进程数 (仅生产模式有效)"
    )
    
    args = parser.parse_args()
    
    # 覆盖环境变量
    if args.host:
        os.environ["HOST"] = args.host
    if args.port:
        os.environ["PORT"] = str(args.port)
    if args.workers:
        os.environ["WORKERS"] = str(args.workers)
    
    # 根据模式启动
    if args.mode == "dev":
        run_development()
    elif args.mode == "prod":
        run_production()
    elif args.mode == "hypercorn":
        run_hypercorn()


if __name__ == "__main__":
    import os
    main()