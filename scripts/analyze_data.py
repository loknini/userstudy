import pandas as pd
import os
import json  # 导入 json 库用于读取配置文件
import numpy as np

# --- 配置 ---
# 指定由 read_database.py 生成的参与者数据文件
PARTICIPANTS_FILE = "exports/participants_backup.csv"
RESPONSES_FILE = "exports/responses_backup.csv"
CONFIG_FILE = "study_config.json"  # 新增配置文件路径
# 将选项索引映射到方法名称
# 假设 0: Ours, 1: BD, 2: P2P0, 3: SDEdit
# 注意：根据您的原始代码，A,B,C,D的顺序是固定的。请确保这里的映射正确。
# 如果您的问卷中选项顺序是随机的，这里的分析逻辑需要调整。
METHOD_MAP = {
    0: "sdxl",
    1: "ti",
    2: "emogen",
    3: "ours",
}


def check_files():
    """检查所需文件是否存在"""
    required_files = [PARTICIPANTS_FILE, RESPONSES_FILE, CONFIG_FILE]
    for f in required_files:
        if not os.path.exists(f):
            print(f"错误: 找不到必要文件 '{f}'。")
            print(
                "请确保 'study_config.json' 存在，并已运行 'python read_database.py' 生成了 CSV 文件。"
            )
            return False
    return True


def analyze_completion_status():
    """
    读取参与者和响应数据文件，分析问卷的完成情况。
    """
    print("--- 用户问卷完成情况分析 ---")

    # 检查所有需要的文件是否存在
    required_files = [PARTICIPANTS_FILE, RESPONSES_FILE, CONFIG_FILE]
    for f in required_files:
        if not os.path.exists(f):
            print(f"错误: 找不到必要文件 '{f}'。")
            print(
                "请确保 'study_config.json' 存在，并已运行 'python read_database.py' 生成了 CSV 文件。"
            )
            return

    try:
        # 1. 读取配置文件，获取总问题数
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        total_questions = len(config.get("questions", []))

        if total_questions == 0:
            print("警告: 配置文件中没有找到问题，无法计算完成率。")
            return

        print(f"问卷总共有 {total_questions} 道题目。\n")

        # 2. 读取参与者和响应数据
        participants_df = pd.read_csv(PARTICIPANTS_FILE)
        responses_df = pd.read_csv(RESPONSES_FILE)

        total_started_users = len(participants_df)
        print(f"总共有 {total_started_users} 位用户开始了问卷。")

        # 3. 统计每个参与者的答题数
        # 使用 nunique() 来处理用户可能重复回答同一题的情况
        responses_per_participant = responses_df.groupby("participant_id")[
            "question_id"
        ].nunique()

        # 4. 筛选出完成所有题目的参与者
        completed_mask = responses_per_participant >= total_questions
        completed_participants = responses_per_participant[completed_mask]

        num_completed = len(completed_participants)
        num_incomplete = total_started_users - num_completed

        print(f"其中，有 {num_completed} 位用户完成了所有题目。")
        print(f"有 {num_incomplete} 位用户未完成所有题目。")

        if total_started_users > 0:
            completion_rate = (num_completed / total_started_users) * 100
            print(f"\n问卷完成率: {completion_rate:.2f}%")

    except Exception as e:
        print(f"分析数据时发生错误: {e}")


def analyze_preferences_and_consistency():
    """
    迁移并适配旧的分析逻辑：
    1. 分析用户对不同方法的偏好（情感 vs 结构）。
    2. 分析用户选择的一致性。
    """
    if not check_files():
        return

    print("--- 详细偏好与一致性分析 ---")

    try:
        # --- 数据准备 ---
        responses_df = pd.read_csv(RESPONSES_FILE)

        # --- 新增：数据清洗 ---
        # 问题：用户可能重复提交同一题的答案，导致 pivot 失败。
        # 解决：对于每个用户和每个问题的组合，只保留时间戳最新的那条记录。
        # 1. 确保 'created_at' 是日期时间类型，以便正确排序
        responses_df["created_at"] = pd.to_datetime(responses_df["created_at"])
        # 2. 按时间排序，并删除重复项，保留最后一条
        responses_df.sort_values("created_at", inplace=True)
        responses_df.drop_duplicates(
            subset=["participant_id", "question_id"], keep="last", inplace=True
        )
        # --------------------

        # 过滤掉未完成所有题目的用户数据，以保证分析的公平性
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        total_questions = len(config.get("questions", []))
        print(total_questions)

        responses_per_participant = responses_df.groupby("participant_id")[
            "question_id"
        ].nunique()
        print(f"responses_per_participant: {responses_per_participant}")
        completed_participant_ids = responses_per_participant[
            responses_per_participant >= total_questions
        ].index

        # 只保留已完成问卷的用户数据
        df = responses_df[
            responses_df["participant_id"].isin(completed_participant_ids)
        ].copy()

        user_cnt = len(completed_participant_ids)
        print(f"Completed participant IDs: {completed_participant_ids.tolist()}")
        if user_cnt == 0:
            print("没有找到已完成问卷的用户，无法进行分析。")
            return

        print(f"找到 {user_cnt} 位有效用户（已完成所有问卷）。\n")

        # 提取问题的前缀（如 'q1', 'q2'）和类型（'1' for emotion, '2' for structure）
        df[["q_group", "q_type"]] = df["question_id"].str.split("-", expand=True)

        # 将数据从长格式转换为宽格式，以便于按用户进行分析
        # 每个用户一行，每列是一个问题的答案
        df_wide = df.pivot(
            index="participant_id", columns="question_id", values="selected_index"
        )

        # --- 1. 偏好分析 (Preference Analysis) ---
        print("--- 1. 偏好分析 (Preference Analysis) ---")

        # 初始化计数器和列表
        methods = METHOD_MAP.values()
        emo_counts = {method: 0 for method in methods}
        stru_counts = {method: 0 for method in methods}
        user_emo_prefs = {method: [] for method in methods}
        user_stru_prefs = {method: [] for method in methods}

        # 获取所有情感和结构问题ID
        emo_questions = sorted([q for q in df_wide.columns if q.endswith("-1")])
        stru_questions = sorted([q for q in df_wide.columns if q.endswith("-2")])
        num_emo_questions = len(emo_questions)
        num_stru_questions = len(stru_questions)

        # 遍历每个用户
        for participant_id, row in df_wide.iterrows():
            user_emo_counts = {method: 0 for method in methods}
            user_stru_counts = {method: 0 for method in methods}

            # 统计情感偏好
            for q_id in emo_questions:
                choice = row[q_id]
                if not pd.isna(choice):
                    method_name = METHOD_MAP[int(choice)]
                    emo_counts[method_name] += 1
                    user_emo_counts[method_name] += 1

            # 统计结构偏好
            for q_id in stru_questions:
                choice = row[q_id]
                if not pd.isna(choice):
                    method_name = METHOD_MAP[int(choice)]
                    stru_counts[method_name] += 1
                    user_stru_counts[method_name] += 1

            # 记录每个用户的偏好率
            for method in methods:
                user_emo_prefs[method].append(
                    user_emo_counts[method] / num_emo_questions
                    if num_emo_questions > 0
                    else 0
                )
                user_stru_prefs[method].append(
                    user_stru_counts[method] / num_stru_questions
                    if num_stru_questions > 0
                    else 0
                )

        print("Emotion Preference:")
        for method in methods:
            total_choices = num_emo_questions * user_cnt
            pref_rate = emo_counts[method] / total_choices if total_choices > 0 else 0
            std_dev = np.std(user_emo_prefs[method])
            p25 = np.percentile(user_emo_prefs[method], 25)
            p75 = np.percentile(user_emo_prefs[method], 75)
            print(
                f"{method:>8}: Count={emo_counts[method]}, Rate={pref_rate:.2%}, Std={std_dev:.4f}, P25={p25:.4f}, P75={p75:.4f}"
            )

        print("\nStructure Preference:")
        for method in methods:
            total_choices = num_stru_questions * user_cnt
            pref_rate = stru_counts[method] / total_choices if total_choices > 0 else 0
            std_dev = np.std(user_stru_prefs[method])
            p25 = np.percentile(user_stru_prefs[method], 25)
            p75 = np.percentile(user_stru_prefs[method], 75)
            print(
                f"{method:>8}: Count={stru_counts[method]}, Rate={pref_rate:.2%}, Std={std_dev:.4f}, P25={p25:.4f}, P75={p75:.4f}"
            )

        # --- 2. 一致性分析 (Consistency Analysis) ---
        print("\n--- 2. 一致性分析 (Consistency Analysis) ---")

        consistent_counts = {method: 0 for method in methods}
        user_consistency_rates = {method: [] for method in methods}
        total_consistent_choices = 0

        # 遍历每个用户
        for participant_id, row in df_wide.iterrows():
            user_consistent_counts = {method: 0 for method in methods}

            # 遍历每个问题组 (q1, q2, ...)
            q_groups = sorted(list(set(df["q_group"])))
            for group in q_groups:
                emo_choice = row.get(f"{group}-1")
                stru_choice = row.get(f"{group}-2")

                # 检查情感和结构选择是否相同且非空
                if pd.notna(emo_choice) and emo_choice == stru_choice:
                    method_name = METHOD_MAP[int(emo_choice)]
                    consistent_counts[method_name] += 1
                    user_consistent_counts[method_name] += 1

            total_user_consistent = sum(user_consistent_counts.values())
            total_consistent_choices += total_user_consistent

            # 记录每个用户的一致性选择分布率
            for method in methods:
                rate = (
                    user_consistent_counts[method] / total_user_consistent
                    if total_user_consistent > 0
                    else 0
                )
                user_consistency_rates[method].append(rate)

        print(f"Total consistent choices across all users: {total_consistent_choices}")
        for method in methods:
            consistency_rate = (
                consistent_counts[method] / total_consistent_choices
                if total_consistent_choices > 0
                else 0
            )
            std_dev = np.std(user_consistency_rates[method])
            p25 = np.percentile(user_consistency_rates[method], 25)
            p75 = np.percentile(user_consistency_rates[method], 75)
            print(
                f"{method:>8}: Count={consistent_counts[method]}, Rate={consistency_rate:.2%}, Std={std_dev:.4f}, P25={p25:.4f}, P75={p75:.4f}"
            )

    except Exception as e:
        print(f"分析数据时发生错误: {e}")


if __name__ == "__main__":
    # 您可以取消注释下面这行来运行之前的完成度分析
    # analyze_completion_status()

    # 运行新的详细分析
    analyze_preferences_and_consistency()
