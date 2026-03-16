import os
import sys
import shutil
import argparse

EMOTIONS = [
    "amusement",
    "anger",
    "awe",
    "contentment",
    "disgust",
    "excitement",
    "fear",
    "sadness",
]  # "amusement"

# 源内容根目录（含各情感子目录与 content=... 子文件夹）
# CONTENT_ROOT = "G:\emoemo_results\挑图\zjx"
CONTENT_ROOT = "G:\\emoemo_results\\挑图\\user_study"
# 模型目录映射与文件名前缀规则
MODELS = {
    # key: { base: 模型根目录, prefix: 文件名前缀 }
    # "db": {
    #     "base": "G:\emoemo_results\comparative/db/db_inference_2.0-1106",
    #     "prefix": "emo",
    # },
    # "emogen": {
    #     "base": "G:\emoemo_results\comparative/emogen/img_1106",
    #     "prefix": "emo",
    # },
    # "emoticrafter": {
    #     "base": "G:\emoemo_results\comparative/emoticrafter/emoticrafter_inference_retrain_4.5-1106",
    #     "prefix": "emo",
    # },
    # "llm4gen": {
    #     "base": "G:\emoemo_results\comparative/llm4gen/inference_1.0-1106",
    #     "prefix": "emo",
    # },
    # "omnigen2": {
    #     "base": "G:\emoemo_results\comparative/omnigen2/output_t2i_lora_1.5-1106",
    #     "prefix": "emo",
    # },
    # "pixart-lora": {
    #     "base": "G:\emoemo_results\comparative/pixart-lora/pixart_inference_1.5-1106",
    #     "prefix": "emo",
    # },
    # "sd-lora": {
    #     "base": "G:\emoemo_results\comparative/sd_lora/sd_inference_7.5-1106",
    #     "prefix": "sd",
    # },
    "sdxl": {
        "base": "G:\emoemo_results\comparative/sdxl_inference/sdxl_inference_7.5-1106",
        "prefix": "sdxl",
    },
    # "ti": {
    #     "base": "G:\emoemo_results\comparative/ti/ti_inference_7.5-1106",
    #     "prefix": "emo",
    # },
}


def build_expected_filename(prefix: str, content: str, emotion: str) -> str:
    """构造源文件名，如 emo-{content}-{emotion}.png / sd-{...}.png / sdxl-{...}.png"""
    return f"{prefix}-{content}-{emotion}.png"


def build_target_filename(
    prefix: str, content: str, emotion: str, model_key: str
) -> str:
    """构造复制后的目标文件名，附加模型后缀"""
    return f"{prefix}-{content}-{emotion}_{model_key}.png"


def process_one_content_folder(
    emotion: str,
    content_dir: str,
    content_text: str,
    dry_run: bool = False,
    overwrite: bool = False,
) -> tuple[int, int]:
    """
    在各模型目录中查找对应文件并复制到 content_dir。
    返回 (found_count, missing_count)
    """
    found = 0
    missing = 0

    for model_key, cfg in MODELS.items():
        prefix = cfg["prefix"]
        model_emotion_dir = os.path.join(cfg["base"], emotion)
        expected_name = build_expected_filename(prefix, content_text, emotion)
        src_path = os.path.join(model_emotion_dir, expected_name)

        if os.path.isfile(src_path):
            target_name = build_target_filename(
                prefix, content_text, emotion, model_key
            )
            dst_path = os.path.join(content_dir, target_name)

            if os.path.exists(dst_path) and not overwrite:
                print(f"[SKIP] 已存在，跳过: {dst_path}")
            else:
                if dry_run:
                    print(f"[DRY] 复制: {src_path} -> {dst_path}")
                else:
                    os.makedirs(content_dir, exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    print(f"[COPY] {src_path} -> {dst_path}")
            found += 1
        else:
            print(f"[MISS] 未找到: {src_path}")
            missing += 1

    return found, missing


def walk_and_collect(
    content_root: str,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    total_found = 0
    total_missing = 0

    for emotion in EMOTIONS:
        emo_dir = os.path.join(content_root, emotion)

        if not os.path.isdir(emo_dir):
            print(f"[WARN] 情感目录不存在: {emo_dir}")
            continue

        # 遍历 content=... 子目录
        for name in os.listdir(emo_dir):
            subdir = os.path.join(emo_dir, name)
            # print(subdir)
            if not os.path.isdir(subdir):
                print("continue")
                continue
            if " " in name:
                name = name + "."

            print(f"\n[PROC] emotion={emotion} | content={name}")
            f, m = process_one_content_folder(
                emotion=emotion,
                content_dir=subdir,
                content_text=name,
                dry_run=dry_run,
                overwrite=overwrite,
            )
            total_found += f
            total_missing += m

    print("\n==== 汇总 ====")
    print(f"命中: {total_found}, 未命中: {total_missing}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从比较目录收集图片到挑图内容目录，并按模型添加文件名后缀"
    )
    parser.add_argument(
        "--content-root",
        default=CONTENT_ROOT,
        help=f"挑图根目录 (默认: {CONTENT_ROOT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印计划操作，不实际复制",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="若目标已存在则覆盖",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    walk_and_collect(
        content_root=args.content_root,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    main()
