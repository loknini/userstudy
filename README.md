# 可控情感图像生成 - 用户研究平台

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

一个用于收集用户对情感图像生成模型主观评价的研究平台。支持多模型对比（SDXL、Textual Inversion、EmoGen、Ours），双维度评估（情感准确性、内容一致性），以及多问卷管理。

## ✨ 主要特性

- 🎯 **双维度评估**: 同时评估情感表达准确性和内容语义一致性
- 📝 **多问卷管理**: 支持创建多个独立问卷，每个有独立配置和数据
- 🔗 **短代码系统**: 6位字符短代码，方便分享和访问
- 📊 **实时统计**: 数据可视化、图表分析、CSV导出
- 🚀 **高性能**: FastAPI异步框架，支持50+并发用户
- 🔒 **数据隔离**: 问卷间数据完全隔离，保证研究独立性

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境

```bash
cp .env.example .env
# 编辑 .env 设置 ADMIN_PASSWORD
```

### 启动服务

```bash
# 开发模式
python run.py --mode dev

# 生产模式
python run.py --mode prod --workers 4
```

### 访问应用

- **首页**: http://localhost:8888/
- **管理后台**: http://localhost:8888/admin?pw=your-password
- **API文档**: http://localhost:8888/docs

## 📖 使用指南

### 创建问卷

1. 访问管理后台 `/admin/studies`
2. 点击"创建新问卷"
3. 填写名称、描述，上传配置文件
4. 获得短代码（如 `abc123`）
5. 分享链接：`http://your-domain.com/study/abc123`

### 准备图片数据

```bash
# 处理图片并生成配置
python scripts/prepare_images.py --source-dir "path/to/images" --target-dir uploads
python scripts/generate_config.py --output study_config.json
```

### 数据分析

```bash
# 导出数据
python scripts/export_data.py

# 运行分析
python scripts/analyze_results.py
```

## 📁 项目结构

```
.
├── app/                    # FastAPI 应用
│   ├── routers/           # 路由（公共/管理/API）
│   ├── services/          # 业务逻辑
│   ├── templates/         # HTML 模板
│   └── utils/             # 工具函数
├── scripts/               # 工具脚本
├── tests/                 # 测试文件
├── uploads/               # 上传图片
├── exports/               # 导出数据
└── static/                # 静态资源
```

## 📚 文档

- [PRD.md](PRD.md) - 产品需求文档
- [README_FASTAPI.md](README_FASTAPI.md) - 详细使用指南
- [AGENTS.md](AGENTS.md) - 项目架构说明
- [scripts/README.md](scripts/README.md) - 工具脚本使用说明

## 🧪 测试

```bash
python -m pytest tests/ -v
```

## 🔄 从旧版本升级

```bash
# 运行迁移脚本
python scripts/migrate_to_multi_study.py
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📄 许可证

MIT License
