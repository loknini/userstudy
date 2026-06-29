import os
from pathlib import Path


def rename_ours_images():
    """
    批量重命名以数字开头的图片文件，添加 _ours 后缀
    例如: 55-A house in a garden.-amusement.jpg -> 55-A house in a garden.-amusement_ours.jpg
    """
    uploads_dir = Path("uploads")
    renamed_count = 0

    for emotion_dir in uploads_dir.iterdir():
        if not emotion_dir.is_dir():
            continue

        for content_dir in emotion_dir.iterdir():
            if not content_dir.is_dir():
                continue

            for img_file in content_dir.iterdir():
                if not img_file.suffix.lower() in (".jpg", ".jpeg", ".png"):
                    continue

                # 检查是否以数字开头且不包含 _ours
                stem = img_file.stem
                if stem[0].isdigit() and not stem.endswith("_ours"):
                    # 构建新文件名
                    new_name = f"{stem}_ours{img_file.suffix}"
                    new_path = img_file.parent / new_name

                    # 重命名
                    print(f"重命名: {img_file.name} -> {new_name}")
                    img_file.rename(new_path)
                    renamed_count += 1

    print(f"\n✅ 完成！共重命名 {renamed_count} 个文件")


if __name__ == "__main__":
    rename_ours_images()
