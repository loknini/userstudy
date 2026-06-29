"""
图片处理服务 - 压缩、缩放、格式转换
"""
import os
import uuid
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from PIL import Image


@dataclass
class ImageSettings:
    """图片处理设置"""
    compress: bool = True
    max_size: int = 512  # 最大边长（像素），保证问卷加载速度
    quality: int = 85     # JPEG 质量


class ImageProcessor:
    """图片处理器"""

    @staticmethod
    def process_image(
        source_path: str,
        target_dir: str,
        method: str,
        settings: ImageSettings,
    ) -> str:
        """
        处理单张图片：缩放 + 压缩 + 格式统一为 JPEG

        Args:
            source_path: 源图片路径
            target_dir: 目标目录
            method: 方法名（用于生成文件名）
            settings: 图片处理设置

        Returns:
            最终文件名（如 "sd-a1b2c3d4.jpg"）
        """
        img = Image.open(source_path)

        # 转换 RGBA/P → RGB
        original_mode = img.mode
        if img.mode in ("RGBA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode not in ("RGB",):
            img = img.convert("RGB")

        # 缩放
        if settings.compress:
            w, h = img.size
            max_dim = max(w, h)
            if max_dim > settings.max_size:
                ratio = settings.max_size / max_dim
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img = img.resize((new_w, new_h), Image.LANCZOS)

        # 生成文件名
        filename = f"{method}-{uuid.uuid4().hex[:8]}.jpg"
        target_path = os.path.join(target_dir, filename)

        # 确保目录存在
        os.makedirs(target_dir, exist_ok=True)

        # 保存为 JPEG
        img.save(target_path, "JPEG", quality=settings.quality, optimize=True)

        return filename

    @staticmethod
    def get_image_info(file_path: str) -> dict:
        """获取图片信息（而不修改图片）"""
        with Image.open(file_path) as img:
            return {
                "width": img.width,
                "height": img.height,
                "mode": img.mode,
                "format": img.format,
                "file_size": os.path.getsize(file_path),
            }
