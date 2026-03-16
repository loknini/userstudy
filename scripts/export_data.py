#!/usr/bin/env python3
"""
数据导出工具

将数据库内容导出为 CSV 或 Excel 格式

Usage:
    python scripts/export_data.py --format csv
    python scripts/export_data.py --format excel --output "results.xlsx"
"""
import argparse
import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

from app.config import get_settings


def export_to_csv(output_dir: Path = None) -> None:
    """导出为 CSV"""
    settings = get_settings()
    db_path = settings.BASE_DIR / "user_study.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    output_dir = output_dir or settings.BASE_DIR
    output_dir.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    
    # 导出 participants
    participants_df = pd.read_sql_query("SELECT * FROM participants", conn)
    participants_file = output_dir / "export_participants.csv"
    participants_df.to_csv(participants_file, index=False, encoding='utf-8-sig')
    print(f"✅ 导出参与者数据: {participants_file}")
    
    # 导出 responses
    responses_df = pd.read_sql_query("SELECT * FROM responses", conn)
    responses_file = output_dir / "export_responses.csv"
    responses_df.to_csv(responses_file, index=False, encoding='utf-8-sig')
    print(f"✅ 导出响应数据: {responses_file}")
    
    conn.close()
    print(f"📊 总计: {len(participants_df)} 参与者, {len(responses_df)} 响应")


def export_to_excel(output_path: Path = None) -> None:
    """导出为 Excel（多 Sheet）"""
    settings = get_settings()
    db_path = settings.BASE_DIR / "user_study.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = settings.BASE_DIR / f"export_{timestamp}.xlsx"
    
    conn = sqlite3.connect(db_path)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # Participants
        df = pd.read_sql_query("SELECT * FROM participants", conn)
        df.to_excel(writer, sheet_name='Participants', index=False)
        
        # Responses
        df = pd.read_sql_query("SELECT * FROM responses", conn)
        df.to_excel(writer, sheet_name='Responses', index=False)
        
        # 统计摘要
        stats_df = pd.DataFrame({
            '指标': ['总参与者', '已完成', '总响应'],
            '数值': [
                pd.read_sql_query("SELECT COUNT(*) FROM participants", conn).iloc[0, 0],
                pd.read_sql_query("SELECT COUNT(*) FROM participants WHERE completed_at IS NOT NULL", conn).iloc[0, 0],
                pd.read_sql_query("SELECT COUNT(*) FROM responses", conn).iloc[0, 0]
            ]
        })
        stats_df.to_excel(writer, sheet_name='Summary', index=False)
    
    conn.close()
    print(f"✅ 导出 Excel: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="数据导出工具")
    parser.add_argument("--format", choices=["csv", "excel"], default="csv",
                        help="导出格式")
    parser.add_argument("--output", help="输出文件路径")
    
    args = parser.parse_args()
    
    if args.format == "csv":
        output_dir = Path(args.output) if args.output else None
        export_to_csv(output_dir)
    else:
        output_path = Path(args.output) if args.output else None
        export_to_excel(output_path)


if __name__ == "__main__":
    main()
