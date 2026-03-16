"""
应用配置管理 - 使用 Pydantic Settings
"""
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # 应用基础配置
    APP_NAME: str = Field(default="User Study Platform", description="应用名称")
    APP_VERSION: str = Field(default="2.0.0", description="应用版本")
    DEBUG: bool = Field(default=False, description="调试模式")
    
    # 服务器配置
    HOST: str = Field(default="0.0.0.0", description="监听地址")
    PORT: int = Field(default=8888, description="监听端口")
    WORKERS: int = Field(default=1, description="工作进程数")
    
    # 安全配置
    ADMIN_PASSWORD: str = Field(default="admin", description="管理员密码")
    SECRET_KEY: str = Field(default="your-secret-key-change-in-production", description="密钥")
    
    # 数据库配置
    DATABASE_URL: str = Field(
        default="sqlite:///./user_study.db",
        description="数据库连接URL"
    )
    DB_POOL_SIZE: int = Field(default=10, description="连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=20, description="连接池溢出上限")
    
    # 文件路径配置
    BASE_DIR: Path = Field(default=Path(__file__).resolve().parent.parent, description="项目根目录")
    UPLOAD_FOLDER: str = Field(default="uploads", description="上传文件夹")
    STATIC_FOLDER: str = Field(default="static", description="静态文件夹")
    TEMPLATES_FOLDER: str = Field(default="app/templates", description="模板文件夹")
    
    # 研究配置
    STUDY_CONFIG_FILE: str = Field(default="study_config.json", description="研究配置文件")
    CONFIG_VERSION: str = Field(default="1.0", description="配置版本")
    
    # 性能配置
    ENABLE_CACHE: bool = Field(default=True, description="启用缓存")
    CACHE_TTL: int = Field(default=300, description="缓存过期时间(秒)")
    
    @property
    def upload_path(self) -> Path:
        """获取上传目录路径"""
        return self.BASE_DIR / self.UPLOAD_FOLDER
    
    @property
    def static_path(self) -> Path:
        """获取静态目录路径"""
        return self.BASE_DIR / self.STATIC_FOLDER
    
    @property
    def templates_path(self) -> Path:
        """获取模板目录路径"""
        return self.BASE_DIR / self.TEMPLATES_FOLDER
    
    @property
    def study_config_path(self) -> Path:
        """获取研究配置文件路径"""
        return self.BASE_DIR / self.STUDY_CONFIG_FILE


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
