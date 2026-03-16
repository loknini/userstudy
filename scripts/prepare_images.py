#!/usr/bin/env python3
"""
图片预处理流水线

整合图片挑选、重命名、压缩的全流程处理

Usage:
    python scripts/prepare_images.py --source-dir "G:\\source" --target-dir "uploads"
    python scripts/prepare_images.py --step rename    # 仅重命名
    python scripts/prepare_images.py --step process   # 仅压缩处理
"""
import os
import shutil
import argparse
from pathlib import Path
from typing import List, Optional

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("警告: 未安装 Pillow，图片处理功能不可用")
    print("安装: pip install Pillow")


# 情感类别
EMOTIONS = [
    "amusement", "anger", "awe", "contentment",
    "disgust", "excitement", "fear", "sadness"
]

# 支持的图片格式
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}


class ImageProcessor:
    """图片处理器"""
    
    def __init__(
        self,
        source_dir: str,
        target_dir: str = "uploads",
        target_size: int = 256,
        quality: int = 85
    ):
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.target_size = target_size
        self.quality = quality
        self.backup_dir = Path(f"{target_dir}_backup")
        
    def organize_images(self) -> None:
        """按情感-内容结构组织图片"""
        print(f"📁 组织图片从 {self.source_dir} 到 {self.target_dir}")
        
        if not self.source_dir.exists():
            raise FileNotFoundError(f"源目录不存在: {self.source_dir}")
        
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        for emotion in EMOTIONS:
            emotion_dir = self.source_dir / emotion
            if not emotion_dir.exists():
                continue
            
            target_emotion_dir = self.target_dir / emotion
            target_emotion_dir.mkdir(exist_ok=True)
            
            for content_dir in emotion_dir.iterdir():
                if not content_dir.is_dir():
                    continue
                
                target_content_dir = target_emotion_dir / content_dir.name
                target_content_dir.mkdir(exist_ok=True)
                
                # 复制图片
                for img_file in content_dir.iterdir():
                    if img_file.suffix.lower() in IMAGE_EXTENSIONS:
                        shutil.copy2(img_file, target_content_dir / img_file.name)
                        print(f"  ✓ 复制: {img_file.name}")
        
        print(f"✅ 图片组织完成")
    
    def backup_images(self) -> None:
        """备份原始图片"""
        if self.backup_dir.exists():
            print(f"⚠️ 备份目录已存在，跳过备份")
            return
        
        print(f"💾 备份图片到 {self.backup_dir}")
        shutil.copytree(self.target_dir, self.backup_dir)
        print(f"✅ 备份完成")
    
    def process_images(self) -> None:
        """处理图片：裁剪、压缩"""
        if not HAS_PIL:
            raise RuntimeError("需要安装 Pillow 才能处理图片")
        
        print(f"🔧 处理图片 (目标尺寸: {self.target_size}x{self.target_size})")
        
        self.backup_images()
        
        for img_path in self.target_dir.rglob("*"):
            if img_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            
            try:
                self._process_single_image(img_path)
            except Exception as e:
                print(f"  ❌ 处理失败 {img_path}: {e}")
        
        print(f"✅ 图片处理完成")
    
    def _process_single_image(self, img_path: Path) -> None:
        """处理单张图片"""
        with Image.open(img_path) as img:
            # 转换为 RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 中心裁剪
            width, height = img.size
            short_side = min(width, height)
            left = (width - short_side) // 2
            top = (height - short_side) // 2
            img = img.crop((left, top, left + short_side, top + short_side))
            
            # 缩放
            img = img.resize((self.target_size, self.target_size), Image.Resampling.LANCZOS)
            
            # 保存
            output_path = img_path.with_suffix('.jpg')
            img.save(output_path, 'JPEG', quality=self.quality)
            
            # 删除原文件（如果不是 jpg）
            if img_path != output_path:
                img_path.unlink()
            
            print(f"  ✓ 处理: {img_path.name} -> {output_path.name}")


def main():
    parser = argparse.ArgumentParser(description="图片预处理流水线")
    parser.add_argument("--source-dir", help="源图片目录")
    parser.add_argument("--target-dir", default="uploads", help="目标目录")
    parser.add_argument("--step", choices=["organize", "backup", "process", "all"], 
                        default="all", help="执行步骤")
    parser.add_argument("--size", type=int, default=256, help="目标尺寸")
    parser.add_argument("--quality", type=int, default=85, help="JPEG质量")
    
    args = parser.parse_args()
    
    processor = ImageProcessor(
        source_dir=args.source_dir or "uploads",
        target_dir=args.target_dir,
        target_size=args.size,
        quality=args.quality
    )
    
    if args.step in ("organize", "all"):
        if not args.source_dir:
            print("❌ 组织图片需要提供 --source-dir")
            return
        processor.organize_images()
    
    if args.step in ("backup", "all"):
        processor.backup_images()
    
    if args.step in ("process", "all"):
        processor.process_images()


if __name__ == "__main__":
    main()
