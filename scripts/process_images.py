import os
from PIL import Image
import shutil

# --- 配置 ---
# 目标文件夹：包含所有需要处理的图片，例如 'uploads' 或 'static'
SOURCE_FOLDER = "uploads"
# 备份文件夹：处理前会将原始图片备份到这里
BACKUP_FOLDER = "uploads_backup"
# 图像处理参数
TARGET_SIZE = 256  # 裁剪后的正方形尺寸（像素）
JPEG_QUALITY = 85  # JPEG 压缩质量 (1-100, 越高越好，文件越大)


def center_crop_and_resize(image_path, output_path, size, quality):
    """
    以中心裁剪图像为正方形，然后缩放到指定尺寸并保存。
    """
    try:
        with Image.open(image_path) as img:
            # 1. 转换为 RGB 以处理 PNG 等格式
            if img.mode != "RGB":
                img = img.convert("RGB")

            # 2. 计算中心裁剪区域
            width, height = img.size
            short_side = min(width, height)
            left = (width - short_side) / 2
            top = (height - short_side) / 2
            right = (width + short_side) / 2
            bottom = (height + short_side) / 2

            img_cropped = img.crop((left, top, right, bottom))

            # 3. 缩放到目标尺寸
            img_resized = img_cropped.resize((size, size), Image.Resampling.LANCZOS)

            # 4. 保存为压缩后的 JPEG
            img_resized.save(output_path, "jpeg", quality=quality)

            original_size = os.path.getsize(image_path)
            new_size = os.path.getsize(output_path)
            print(
                f"处理完成: {image_path} -> {output_path} ({original_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB)"
            )

    except Exception as e:
        print(f"处理失败: {image_path}, 错误: {e}")


def process_all_images():
    """
    遍历源文件夹，备份并处理所有图片。
    """
    if not os.path.exists(SOURCE_FOLDER):
        print(f"错误: 源文件夹 '{SOURCE_FOLDER}' 不存在。")
        return

    # 1. 备份原始图片
    if os.path.exists(BACKUP_FOLDER):
        print(f"警告: 备份文件夹 '{BACKUP_FOLDER}' 已存在。跳过备份。")
    else:
        print(f"正在备份原始图片到 '{BACKUP_FOLDER}'...")
        shutil.copytree(SOURCE_FOLDER, BACKUP_FOLDER)
        print("备份完成。")

    # 2. 遍历并处理图片
    print("\n开始处理图片...")
    for subdir, _, files in os.walk(SOURCE_FOLDER):
        for file in files:
            if file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                image_path = os.path.join(subdir, file)
                # 直接在原位置覆盖保存为 .jpg 格式
                output_path = os.path.splitext(image_path)[0] + ".png"
                center_crop_and_resize(
                    image_path, output_path, TARGET_SIZE, JPEG_QUALITY
                )
                # 如果原文件不是 .jpg，处理后删除原文件以避免混淆
                if (
                    os.path.splitext(image_path)[1].lower() != ".png"
                    and image_path != output_path
                ):
                    os.remove(image_path)


if __name__ == "__main__":
    process_all_images()
    print("\n所有图片处理完毕！")
