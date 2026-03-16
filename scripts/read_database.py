import sqlite3
import pandas as pd
import os

# --- 配置 ---
DATABASE_FILE = "user_study.db"
# 设置为 True 可以将数据表导出为 CSV 文件
EXPORT_TO_CSV = True
OUTPUT_RESPONSES_CSV = "exports/responses_backup.csv"
OUTPUT_PARTICIPANTS_CSV = "exports/participants_backup.csv"


def read_and_export_data():
    """
    连接到 SQLite 数据库，读取 'responses' 和 'participants' 表，
    在控制台打印数据，并可以选择将其导出为 CSV 文件。
    """
    if not os.path.exists(DATABASE_FILE):
        print(f"错误: 数据库文件 '{DATABASE_FILE}' 不存在。")
        print("请先运行主应用 run.py 以生成数据库。")
        return

    try:
        # 连接到数据库
        conn = sqlite3.connect(DATABASE_FILE)
        print(f"成功连接到数据库: {DATABASE_FILE}\n")

        # --- 读取 'responses' 表 ---
        print("--- 表: responses ---")
        # 使用 pandas 读取 SQL 查询结果为 DataFrame
        responses_df = pd.read_sql_query("SELECT * FROM responses", conn)
        if responses_df.empty:
            print("responses 表中没有数据。")
        else:
            # to_string() 可以确保打印所有行和列
            print(responses_df.to_string())
            if EXPORT_TO_CSV:
                responses_df.to_csv(
                    OUTPUT_RESPONSES_CSV, index=False, encoding="utf-8-sig"
                )
                print(f"\n -> 已将 responses 表数据导出到: {OUTPUT_RESPONSES_CSV}")

        print("\n" + "=" * 50 + "\n")

        # --- 读取 'participants' 表 ---
        print("--- 表: participants ---")
        participants_df = pd.read_sql_query("SELECT * FROM participants", conn)
        if participants_df.empty:
            print("participants 表中没有数据。")
        else:
            print(participants_df.to_string())
            if EXPORT_TO_CSV:
                participants_df.to_csv(
                    OUTPUT_PARTICIPANTS_CSV, index=False, encoding="utf-8-sig"
                )
                print(
                    f"\n -> 已将 participants 表数据导出到: {OUTPUT_PARTICIPANTS_CSV}"
                )

    except Exception as e:
        print(f"读取数据库时发生错误: {e}")
    finally:
        if "conn" in locals() and conn:
            conn.close()
            print(f"\n数据库连接已关闭。")


if __name__ == "__main__":
    read_and_export_data()
