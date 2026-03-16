# 工具脚本使用说明

本目录包含用户研究平台的辅助工具脚本，用于数据处理、配置生成、数据分析和系统维护。

## 📁 脚本分类

### 1. 图片处理 (Image Processing)

#### `prepare_images.py` - 图片预处理流水线
整合图片挑选、重命名、压缩的全流程处理。

```bash
# 完整流程
python scripts/prepare_images.py --source-dir "G:\\source" --target-dir "uploads"

# 仅执行特定步骤
python scripts/prepare_images.py --step rename    # 仅重命名
python scripts/prepare_images.py --step process   # 仅压缩处理
```

**功能**:
- 从各模型目录挑选图片
- 按情感和内容组织目录结构
- 中心裁剪为正方形
- 压缩并统一格式

---

### 2. 配置生成 (Configuration)

#### `generate_config.py` - 生成研究配置
扫描图片目录结构，自动生成 `study_config.json`。

```bash
# 基本用法
python scripts/generate_config.py

# 指定源目录
python scripts/generate_config.py --content-root "G:\\emoemo_results\\挑图\\user_study"

# 指定输出文件
python scripts/generate_config.py --output "configs/study_v2.json"
```

**输出**:
- 生成符合格式要求的 JSON 配置文件
- 自动生成中英双语提示
- 为每个内容-情感组合生成两个问题（情感维度 + 内容维度）

---

### 3. 数据分析 (Data Analysis)

#### `export_data.py` - 数据导出
将数据库内容导出为 CSV 或 Excel 格式。

```bash
# 导出为 CSV
python scripts/export_data.py --format csv

# 导出为 Excel（多 Sheet）
python scripts/export_data.py --format excel --output "analysis/results.xlsx"

# 导出特定问卷的数据
python scripts/export_data.py --study-code abc123
```

#### `analyze_results.py` - 结果分析
分析用户响应数据，生成统计报告。

```bash
# 完整分析
python scripts/analyze_results.py

# 仅特定分析
python scripts/analyze_results.py --analysis preference    # 偏好分析
python scripts/analyze_results.py --analysis consistency   # 一致性分析
python scripts/analyze_results.py --analysis completion    # 完成率分析

# 分析特定问卷
python scripts/analyze_results.py --study-code abc123
```

**输出报告**:
- 问卷完成率统计
- 模型偏好对比（情感维度 vs 内容维度）
- 用户选择一致性分析
- 按模型的胜率统计

#### `read_database.py` - 数据库读取
直接在控制台查看数据库内容，并导出为 CSV。

```bash
python scripts/read_database.py
```

**输出**:
- 控制台打印 responses 和 participants 表内容
- 导出到 `exports/responses_backup.csv`
- 导出到 `exports/participants_backup.csv`

---

### 4. 系统维护 (Maintenance)

#### `migrate_to_multi_study.py` - 多问卷迁移
将单问卷版本的数据库迁移到多问卷架构。

```bash
# 自动迁移
python scripts/migrate_to_multi_study.py

# 检查迁移状态
python scripts/migrate_to_multi_study.py --check

# 强制重新迁移（谨慎使用）
python scripts/migrate_to_multi_study.py --force
```

**迁移内容**:
1. 创建 `studies` 表
2. 创建默认问卷（code: default）
3. 更新 `participants` 表添加 `study_id` 列
4. 将所有参与者关联到默认问卷
5. 更新 `responses` 表添加 `study_id` 列

**注意**: 迁移前会自动备份数据库到 `user_study.db.backup`

#### `check_db.py` - 数据库检查
检查数据库结构和数据完整性。

```bash
# 基本检查
python scripts/check_db.py

# 详细检查
python scripts/check_db.py --verbose
```

**检查项**:
- 表结构完整性
- 外键约束
- 数据一致性
- 索引状态

#### `fix_database.py` - 数据库修复
修复常见的数据库问题。

```bash
# 自动修复
python scripts/fix_database.py

# 仅检查不修复
python scripts/fix_database.py --check-only
```

**修复内容**:
- 修复损坏的索引
- 清理孤立记录
- 重建外键关系
- 优化表结构

#### `optimize_database.py` - 数据库优化
优化数据库性能。

```bash
python scripts/optimize_database.py
```

**优化内容**:
- 重建索引
- 分析表统计信息
- 清理空闲空间
- VACUUM 操作

---

## 🔧 快速工作流程

### 首次部署流程

```bash
# 1. 准备图片数据
python scripts/prepare_images.py --source-dir "G:\\source" --target-dir "uploads"

# 2. 生成研究配置
python scripts/generate_config.py --output "study_config.json"

# 3. 启动应用验证
python run.py --mode dev

# 4. 在管理后台创建问卷
# 访问 http://localhost:8888/admin/studies

# 5. 收集数据后分析
python scripts/export_data.py
python scripts/analyze_results.py
```

### 日常数据分析流程

```bash
# 导出最新数据
python scripts/export_data.py

# 运行分析
python scripts/analyze_results.py

# 查看输出报告（保存在 analysis/ 目录）
```

### 从旧版本升级流程

```bash
# 1. 备份数据（自动）
cp user_study.db user_study.db.manual-backup

# 2. 运行迁移脚本
python scripts/migrate_to_multi_study.py

# 3. 检查迁移结果
python scripts/check_db.py --verbose

# 4. 启动应用验证
python run.py --mode dev

# 5. 访问 http://localhost:8888/study/default 验证数据
```

---

## ⚙️ 配置说明

### 环境变量

在 `.env` 文件中配置脚本参数：

```bash
# 数据源目录
SOURCE_IMAGES_DIR=G:\emoemo_results\挑图\user_study

# 图片处理参数
TARGET_IMAGE_SIZE=256
JPEG_QUALITY=85

# 分析参数
MIN_COMPLETE_QUESTIONS=10  # 视为完成的最少答题数

# 导出路径
EXPORT_DIR=exports
```

### 自定义模型映射

编辑 `scripts/generate_config.py` 添加新的对比模型：

```python
model_list = ["sdxl", "ti", "emogen", "ours", "new_model"]

model_folders = {
    "new_model": "new_model_results",
}
```

---

## 📊 输出文件说明

### 分析脚本输出

运行分析后生成以下文件：

```
analysis/
├── summary_report.txt          # 文本摘要报告
├── model_comparison.csv        # 模型对比数据
├── participant_stats.csv       # 参与者统计
└── charts/
    ├── overall_votes.png       # 总体投票图
    ├── emotion_dimension.png   # 情感维度图
    └── content_dimension.png   # 内容维度图
```

### 导出文件位置

```
exports/
├── responses_backup.csv        # 响应数据备份
├── participants_backup.csv     # 参与者数据备份
└── study_abc123_data.xlsx      # 特定问卷导出（Excel格式）
```

---

## 🐛 故障排除

### 图片处理失败

**问题**: PIL 无法读取某些图片
```bash
# 检查图片完整性
python scripts/prepare_images.py --verify-only
```

### 配置生成失败

**问题**: 找不到模型输出
- 检查 `CONTENT_ROOT` 路径是否正确
- 确认模型输出目录命名符合规范

### 分析脚本报错

**问题**: 缺少 CSV 文件
```bash
# 先导出数据
python scripts/export_data.py

# 再运行分析
python scripts/analyze_results.py
```

### 迁移失败

**问题**: 数据库锁定或损坏
```bash
# 1. 确保应用已停止
# 2. 手动备份
cp user_study.db user_study.db.emergency-backup

# 3. 尝试修复
python scripts/fix_database.py

# 4. 重新迁移
python scripts/migrate_to_multi_study.py --force
```

---

## 📝 开发新脚本

如需添加新脚本，请遵循以下规范：

1. **文件命名**: 使用下划线命名法，如 `my_script.py`
2. **命令行接口**: 使用 `argparse` 提供 `--help`
3. **配置读取**: 优先从 `.env` 读取，其次命令行参数
4. **输出目录**: 统一输出到 `exports/` 或 `analysis/`
5. **错误处理**: 提供有意义的错误信息
6. **日志输出**: 使用 `print()` 输出进度信息

示例模板:

```python
#!/usr/bin/env python3
"""
脚本功能简述

Usage:
    python scripts/my_script.py --input file.txt
"""
import argparse
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings

def main():
    parser = argparse.ArgumentParser(description="脚本描述")
    parser.add_argument("--input", required=True, help="输入文件")
    parser.add_argument("--output", default="exports/output.csv", help="输出文件")
    args = parser.parse_args()
    
    settings = get_settings()
    
    # 脚本逻辑...
    print(f"处理中: {args.input}")
    
if __name__ == "__main__":
    main()
```

---

## 📚 相关文档

- [PRD.md](../PRD.md) - 产品需求文档
- [README_FASTAPI.md](../README_FASTAPI.md) - 快速开始指南
- [AGENTS.md](../AGENTS.md) - 项目架构说明