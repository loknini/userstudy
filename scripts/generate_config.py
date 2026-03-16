import os
import json
import argparse

# --- 配置 ---

# 与 choose_picture.py 保持一致
EMOTIONS = [
    "amusement",
    "anger",
    "awe",
    "contentment",
    "disgust",
    "excitement",
    "fear",
    "sadness",
]

# 挑图脚本的输出根目录
DEFAULT_CONTENT_ROOT = "G:\\emoemo_results\\挑图\\user_study"

# Flask App 中用于存放上传/收集图片的目录名
# 图片的 Web 路径将是 /<UPLOADS_DIR_NAME>/...
UPLOADS_DIR_NAME = "uploads"

# --- 脚本主体 ---
model_list = [
    # "sd",
    "sdxl",
    "ti",
    # "db",
    # "llm4gen",
    # "pixart",
    # "omnigen2",
    "emogen",
    # "emoticrafter",
    "ours",
]

emotion_translate = {
    "amusement": "愉悦",
    "awe": "敬畏",
    "contentment": "满足",
    "excitement": "激动",
    "anger": "生气",
    "disgust": "厌恶",
    "fear": "恐惧",
    "sadness": "悲伤",
}

content_translate = {
    "bus": "公共汽车",
    "A dog on the ground": "地上的一只狗",
    "A tree in the park": "公园里的一棵树",
    "Food placed on the plate": "放在盘子里的食物",
    "grass": "草",
    "wall": "墙",
    "A bird flying in the sky": "一只鸟在天空中飞翔",
    "A mountain under the sky": "天空下的山",
    "car": "车",
    "leaves": "树叶",
    "beach": "海滩",
    "couple": "夫妻",
    "ocean": "海洋",
    "A cake on the table": "桌子上放着一块蛋糕",
    "A person is walking on a street": "一个人正在街上行走",
    "A person on the stage": "舞台上的人",
    "dress": "裙子",
    "food": "食物",
    "People walking on a beach": "人们在海滩上散步",
    "street": "街道",
    "A car on the road": "路上的一辆汽车",
    "Bus on the street": "街上的公交车",
    "stage": "舞台",
    "A house in a garden": "花园里的房子",
    "cake": "蛋糕",
    "sign": "标志",
    "Clouds in the sky": "天空中的云",
    "park": "公园",
    "Trees on the mountain": "山上的树木",
    "blanket": "毯子",
    "A toy on the floor": "地板上的玩具",
    "A beach is with rocks": "海滩上遍布岩石",
    "sky": "天空",
    "toy": "玩具",
    "A cup on a table": "桌子上的杯子",
    "room": "房间",
    "branch": "树枝",
    "garden": "花园",
    "child": "孩子",
    "person": "人",
    "A couple walking in a park": "一对情侣在公园散步",
    "ground": "地面",
}


def generate_config(content_root: str, output_path: str):
    """
    扫描 content_root 目录，生成 study_config.json 文件。
    """
    print(f"正在扫描目录: {content_root}")

    instructions = """
    我们的任务是“可控的情感图像内容生成”，旨在根据文本描述，生成不仅内容准确，而且能唤起指定情感体验的图像。\n
    在接下来的问卷中，每个问题会给出一个文本描述和目标情感，并展示由不同模型生成的多张图像。\n
    请您思考并回答以下两个核心问题：\n
    1. 问题一：哪张图最能让您感受到指定的情感？\n
    2. 问题二：哪张图最符合内容描述？\n
    本次实验预计耗时约10分钟，感谢您的认真参与！
    """

    # 基础配置模板
    config = {
        "title": "User Study: 可控的情感图像内容生成",
        "instructions": instructions,
        "randomize": True,
        "examples": [
            {
                "text": "理想特点1：情感表达准确",
                "images": [
                    "/static/examples/example_good_emotion.png",
                ],
            },
            {
                "text": "理想特点2：内容语义一致",
                "images": [
                    "/static/examples/example_good_content.png",
                ],
            },
            {
                "text": "理想特点3：语义清晰明确",
                "images": [
                    "/static/examples/example_clear_prompt.png",
                ],
            },
        ],
        "questions": [],
    }

    question_counter = 1
    total_images_found = 0

    # 遍历每个情感目录
    for emotion in EMOTIONS:
        emotion_dir = os.path.join(content_root, emotion)
        if not os.path.isdir(emotion_dir):
            continue

        print(f"\n处理情感: {emotion}")

        # 遍历每个 content 子目录
        for content_folder_name in sorted(os.listdir(emotion_dir)):
            content_dir_path = os.path.join(emotion_dir, content_folder_name)
            if not os.path.isdir(content_dir_path):
                continue

            all_image_files_in_dir = os.listdir(content_dir_path)
            image_files = []
            found_models = []
            # 根据 model_list 筛选图片，每个模型一张
            for model in model_list:
                found_file = None
                for fname in all_image_files_in_dir:
                    name, ext = os.path.splitext(fname)
                    if ext.lower() in (
                        ".png",
                        ".jpg",
                        ".jpeg",
                    ) and (
                        name.lower().endswith(f"_{model}")
                        or name.lower().endswith(f"_{model}-lora")
                    ):
                        found_file = fname
                        break
                if found_file:
                    image_files.append(found_file)
                    found_models.append(model)
            # 检查是否有缺失的模型并输出警告
            if len(found_models) < len(model_list):
                missing_models = set(model_list) - set(found_models)
                print(
                    f"  - [警告] 目录 '{content_folder_name}' 缺少模型: {', '.join(sorted(list(missing_models)))}"
                )

            if not image_files:
                print(
                    f"  - [跳过] 目录 '{content_folder_name}' 中没有与模型列表匹配的图片。"
                )
                continue

            # 为 Web App 构建图片路径
            # 例如: /uploads/sadness/a sad cat/emo-a sad cat-sadness_db.png
            image_web_paths = [
                f"/{UPLOADS_DIR_NAME}/{emotion}/{content_folder_name}/{fname}"
                for fname in image_files
            ]
            print(image_web_paths)

            # 创建问题对象
            question = {
                "id": f"q{question_counter}-1",
                "prompt": f"""
<strong>内容:</strong> '{content_folder_name}' ({content_translate.get(content_folder_name, content_folder_name)})<br>
<strong>情感:</strong> '{emotion}' ({emotion_translate.get(emotion, emotion)})
<hr style="margin: 1rem 0;">
请从以下图片中选择<strong>最能唤起'{emotion}' （{emotion_translate.get(emotion, emotion)}）</strong>的一张。
                """,
                "images": image_web_paths,
                "models": found_models,
                "type": "choose_one",
            }
            config["questions"].append(question)

            question = {
                "id": f"q{question_counter}-2",
                "prompt": f"""
<strong>内容:</strong> '{content_folder_name}'  ({content_translate.get(content_folder_name, content_folder_name)})<br>
<strong>情感:</strong> '{emotion}' ({emotion_translate.get(emotion, emotion)})
<hr style="margin: 1rem 0;">
请从以下图片中选择<strong>最符合内容描述</strong>（如果相差无几，请选择最能唤起'{emotion}' （{emotion_translate.get(emotion, emotion)}））的一张。
                """,
                "images": image_web_paths,
                "models": found_models,
                "type": "choose_one",
            }
            config["questions"].append(question)

            print(
                f"  + [添加问题] ID: q{question_counter}, 包含 {len(image_files)} 张图片。"
            )
            question_counter += 1
            total_images_found += len(image_files)

    # 保存为 JSON 文件
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"\n==== 完成 ====")
        print(f"成功生成配置文件: {output_path}")
        print(f"总计问题数: {len(config['questions'])}")
        print(f"总计图片数: {total_images_found}")
    except Exception as e:
        print(f"\n[错误] 写入文件失败: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="根据图片目录结构生成 User Study 的 JSON 配置文件。"
    )
    parser.add_argument(
        "--content-root",
        default=DEFAULT_CONTENT_ROOT,
        help=f"包含已收集图片的内容根目录 (默认: {DEFAULT_CONTENT_ROOT})",
    )
    parser.add_argument(
        "--output",
        default="study_config.json",
        help="输出的 JSON 配置文件路径 (默认: study_config.json)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.content_root):
        print(f"[错误] 指定的 content-root 目录不存在: {args.content_root}")
        return

    generate_config(args.content_root, args.output)
    print(
        "\n下一步提醒：请将 content-root 目录下的所有内容复制到 Flask App 的 'uploads' 文件夹中。"
    )


if __name__ == "__main__":
    main()
