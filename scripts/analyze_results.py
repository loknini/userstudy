#!/usr/bin/env python3
"""
结果分析工具

分析用户响应数据，生成统计报告

Usage:
    python scripts/analyze_results.py
    python scripts/analyze_results.py --analysis preference
    python scripts/analyze_results.py --output analysis/
"""
import argparse
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from app.config import get_settings
from app.database import SessionLocal
from app.services.study import StudyService
from app.services.stats import StatsService


# 模型索引映射
METHOD_MAP = {
    0: "sdxl",
    1: "ti",
    2: "emogen",
    3: "ours",
}


class ResultAnalyzer:
    """结果分析器"""
    
    def __init__(self, output_dir: Path = None):
        self.db = SessionLocal()
        self.study_service = StudyService(self.db)
        self.stats_service = StatsService(self.db)
        self.config = self.study_service.get_active_config()
        
        self.output_dir = output_dir or Path("analysis")
        self.output_dir.mkdir(exist_ok=True)
        
        self.report_lines = []
    
    def _log(self, message: str) -> None:
        """记录日志"""
        print(message)
        self.report_lines.append(message)
    
    def analyze_completion(self) -> None:
        """分析完成率"""
        self._log("\n" + "="*60)
        self._log("📊 问卷完成情况分析")
        self._log("="*60)
        
        if not self.config:
            self._log("❌ 未找到研究配置")
            return
        
        total_questions = len(self.config.questions)
        stats = self.stats_service.get_overall_stats(self.config)
        
        self._log(f"\n问卷总题数: {total_questions}")
        self._log(f"总参与者: {stats.total_participants}")
        self._log(f"已完成: {stats.completed_participants}")
        self._log(f"完成率: {stats.completion_rate:.2f}%")
        
        if stats.average_response_time:
            self._log(f"平均答题时间: {stats.average_response_time:.2f} 秒")
    
    def analyze_preferences(self) -> None:
        """分析模型偏好"""
        self._log("\n" + "="*60)
        self._log("🏆 模型偏好分析")
        self._log("="*60)
        
        if not self.config:
            return
        
        stats = self.stats_service.get_overall_stats(self.config)
        
        self._log("\n总体得票排名:")
        for model_stat in sorted(stats.per_model, key=lambda x: x.total_picks, reverse=True):
            self._log(f"  {model_stat.model_name:12} : {model_stat.total_picks:4} 票 ({model_stat.pick_rate:5.2f}%)")
        
        self._log("\n情感维度得票:")
        for model_stat in sorted(stats.per_model, key=lambda x: x.emotion_picks, reverse=True):
            self._log(f"  {model_stat.model_name:12} : {model_stat.emotion_picks:4} 票")
        
        self._log("\n内容维度得票:")
        for model_stat in sorted(stats.per_model, key=lambda x: x.content_picks, reverse=True):
            self._log(f"  {model_stat.model_name:12} : {model_stat.content_picks:4} 票")
    
    def analyze_consistency(self) -> None:
        """分析一致性"""
        self._log("\n" + "="*60)
        self._log("🔄 用户选择一致性分析")
        self._log("="*60)
        
        if not self.config:
            return
        
        analysis = self.stats_service.get_participant_consistency_analysis(self.config)
        
        self._log(f"\n有效参与者: {analysis['total_participants']}")
        self._log(f"平均一致性率: {analysis['average_consistency_rate']*100:.2f}%")
        
        # 一致性分布
        rates = [d['consistency_rate'] for d in analysis['details']]
        if rates:
            self._log(f"一致性率中位数: {np.median(rates)*100:.2f}%")
            self._log(f"一致性率标准差: {np.std(rates)*100:.2f}%")
    
    def generate_report(self) -> Path:
        """生成分析报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"analysis_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.report_lines))
        
        print(f"\n✅ 报告已保存: {report_file}")
        return report_file
    
    def export_chart_data(self) -> Path:
        """导出图表数据"""
        if not self.config:
            return None
        
        chart_data = self.stats_service.get_chart_data(self.config)
        
        data_file = self.output_dir / "chart_data.json"
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(chart_data.model_dump(), f, ensure_ascii=False, indent=2)
        
        print(f"✅ 图表数据已保存: {data_file}")
        return data_file
    
    def close(self) -> None:
        """关闭数据库连接"""
        self.db.close()


def main():
    parser = argparse.ArgumentParser(description="结果分析工具")
    parser.add_argument("--analysis", choices=["completion", "preference", "consistency", "all"],
                        default="all", help="分析类型")
    parser.add_argument("--output", help="输出目录")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output) if args.output else Path("analysis")
    analyzer = ResultAnalyzer(output_dir)
    
    try:
        if args.analysis in ("completion", "all"):
            analyzer.analyze_completion()
        
        if args.analysis in ("preference", "all"):
            analyzer.analyze_preferences()
        
        if args.analysis in ("consistency", "all"):
            analyzer.analyze_consistency()
        
        # 生成报告
        analyzer.generate_report()
        analyzer.export_chart_data()
        
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
