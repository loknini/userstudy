"""
模板引擎管理模块
"""
from fastapi.templating import Jinja2Templates
from app.config import get_settings

# 全局模板引擎实例
_templates = None


def get_templates() -> Jinja2Templates:
    """获取全局模板引擎实例"""
    global _templates
    if _templates is None:
        settings = get_settings()
        _templates = Jinja2Templates(directory=str(settings.templates_path))
        _templates.env.cache = None
    return _templates