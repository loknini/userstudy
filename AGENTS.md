# AGENTS.md - 可控情感图像生成用户研究项目

## 项目概述

这是一个用于**可控情感图像内容生成**的用户研究平台。项目通过 Flask/FastAPI Web 应用收集用户对不同模型生成图像的评价，评估图像在情感表达准确性和内容语义一致性方面的表现。

### 核心功能

- **Web 用户界面**: 参与者可以浏览说明、查看示例，并对不同模型生成的图像进行选择评价
- **双维度评估**: 每个图像组需回答两个问题：
  1. 哪张图最能唤起指定情感？
  2. 哪张图最符合内容描述？
- **多模型对比**: 支持对比 SDXL、Textual Inversion (TI)、EmoGen 和本研究团队模型 (Ours)
- **多问卷支持 (v3.0)**: 支持创建多个独立问卷，每个问卷有独立的短代码、配置和数据
- **数据收集与统计**: SQLite 数据库存储用户响应，支持 CSV 导出和可视化分析
- **管理后台**: 提供问卷管理、配置上传、数据统计、图表分析等管理功能

### 技术栈

- **后端**: Python + FastAPI (v2.0+), 早期为 Flask (v1.0)
- **数据库**: SQLite (user_study.db)
- **前端**: Bootstrap 5 + Chart.js
- **数据处理**: Pandas, NumPy, PIL

---

## 项目结构

```
D:\project\userstudy\
├── run.py                          # 主入口（启动脚本）
├── study_config.json               # 研究配置文件（题目、图片路径、模型映射）
├── user_study.db                   # SQLite 数据库（用户响应数据）
├── .env / .env.example             # 环境变量配置
├── requirements.txt                # Python 依赖
├── app/                            # FastAPI 应用代码
│   ├── main.py                     # FastAPI 应用入口
│   ├── config.py                   # 配置管理 (Pydantic Settings)
│   ├── database.py                 # 数据库连接和会话管理
│   ├── models.py                   # SQLAlchemy 数据模型
│   ├── schemas.py                  # Pydantic 数据验证模型
│   ├── routers/                    # API 路由
│   │   ├── public.py               # 公共路由（问卷页面、答题、提交）
│   │   ├── admin.py                # 管理后台路由（问卷管理、统计）
│   │   └── api.py                  # RESTful API 路由
│   ├── services/                   # 业务逻辑服务
│   │   ├── study.py                # 问卷服务（创建、查询、答题逻辑）
│   │   ├── stats.py                # 统计服务（数据分析、图表）
│   │   ├── export.py               # 导出服务（CSV/Excel）
│   │   ├── cleanup.py              # 清理服务
│   │   └── cleanup_strategies.py   # 清理策略
│   ├── templates/                  # Jinja2 HTML 模板
│   │   ├── base.html               # 基础模板
│   │   ├── index.html              # 首页/问卷首页
│   │   ├── question.html           # 答题页面
│   │   ├── completed.html          # 完成页面
│   │   ├── admin.html              # 管理后台首页
│   │   ├── admin_login.html        # 管理登录页
│   │   ├── admin_studies.html      # 问卷列表页
│   │   ├── admin_study_create.html # 创建问卷页
│   │   ├── admin_study_detail.html # 问卷详情页
│   │   └── analysis.html           # 数据分析页
│   └── utils/                      # 工具函数
│       └── short_code.py           # 短代码生成工具
├── scripts/                        # 工具脚本
│   ├── prepare_images.py           # 图片预处理流水线
│   ├── generate_config.py          # 根据图片目录生成研究配置
│   ├── export_data.py              # 导出数据为 CSV/Excel
│   ├── analyze_results.py          # 数据分析脚本
│   ├── analyze_data.py             # 数据分析（旧版）
│   ├── read_database.py            # 数据库读取与 CSV 导出
│   ├── migrate_to_multi_study.py   # 多问卷架构迁移脚本
│   ├── migrate_cleanup_strategy.py # 清理策略迁移
│   ├── migrate.py                  # 数据库迁移（旧版）
│   ├── check_config.py             # 配置检查
│   ├── check_db.py                 # 数据库检查
│   ├── fix_database.py             # 数据库修复
│   ├── optimize_database.py        # 数据库优化
│   ├── process_images.py           # 图片处理
│   ├── choose_picture.py           # 图片挑选
│   ├── choose_picture_new.py       # 图片挑选（新版）
│   ├── rename.py                   # 图片重命名
│   └── README.md                   # 脚本使用说明
├── tests/                          # 测试文件
│   ├── conftest.py                 # 测试配置
│   ├── test_api.py                 # API 测试
│   ├── test_services.py            # 服务测试
│   ├── stress_test.py              # 压力测试
│   └── locustfile.py               # Locust 性能测试
├── exports/                        # 导出数据目录
│   ├── responses_backup.csv        # 响应数据导出
│   └── participants_backup.csv     # 参与者数据导出
├── static/                         # 静态资源
│   └── examples/                   # 示例图片
├── uploads/                        # 上传的图片数据（按情感和内容组织）
│   ├── amusement/                  # 愉悦情感类别
│   ├── anger/                      # 生气情感类别
│   ├── awe/                        # 敬畏情感类别
│   ├── contentment/                # 满足情感类别
│   ├── disgust/                    # 厌恶情感类别
│   ├── excitement/                 # 激动情感类别
│   ├── fear/                       # 恐惧情感类别
│   └── sadness/                    # 悲伤情感类别
└── uploads_backup/                 # 图片备份目录
```

### 情感类别 (8种)

- `amusement` (愉悦)
- `anger` (生气)
- `awe` (敬畏)
- `contentment` (满足)
- `disgust` (厌恶)
- `excitement` (激动)
- `fear` (恐惧)
- `sadness` (悲伤)

### 对比模型

- `sdxl` - Stable Diffusion XL
- `ti` - Textual Inversion
- `emogen` - EmoGen 模型
- `ours` - 本研究团队模型

---

## 多问卷架构 (v3.0)

### 核心概念

- **问卷 (Study)**: 一个独立的研究项目，有自己的配置、参与者和数据
- **短代码 (Short Code)**: 6位字符（小写字母+数字），用于访问特定问卷
- **数据隔离**: 每个问卷的数据通过 `study_id` 外键隔离

### 数据库表结构

#### studies 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | String | UUID 主键 |
| code | String | 短代码，唯一索引 |
| name | String | 问卷名称 |
| description | Text | 问卷描述 |
| config_json | Text | 配置JSON |
| status | String | 状态: active/paused/archived |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### participants 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | String | UUID 主键 |
| study_id | String | 外键 → studies.id |
| started_at | DateTime | 开始时间 |
| ip_address | String | IP 地址 |
| user_agent | Text | 浏览器 User-Agent |
| completed_at | DateTime | 完成时间 |

#### responses 表
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 自增主键 |
| participant_id | String | 外键 → participants.id |
| study_id | String | 外键 → studies.id |
| question_id | String | 问题标识 (如 q1-1, q1-2) |
| selected_index | Integer | 选择的图片索引 (0-3) |
| rating | Integer | 评分 (可选) |
| comment | Text | 评论 (可选) |
| time_spent | Real | 答题用时 (秒) |
| created_at | DateTime | 提交时间 |

### URL 路由结构

#### 多问卷路由（新）
- `/study/{code}` - 问卷首页
- `/study/{code}/start` - 开始问卷
- `/study/{code}/question/{idx}` - 第 idx 题
- `/study/{code}/submit/{idx}` - 提交第 idx 题答案
- `/study/{code}/completed` - 完成页面

#### 管理路由
- `/admin` - 管理后台首页
- `/admin/studies` - 问卷列表
- `/admin/studies/create` - 创建问卷
- `/admin/study/{code}` - 问卷详情
- `/admin/api/studies` - 问卷列表 API

#### 向后兼容（旧路由重定向）
- `/start` → `/study/default/start`
- `/question/{idx}` → `/study/default/question/{idx}`
- `/completed` → `/study/default/completed`

### 短代码系统

- **长度**: 6位字符（可配置）
- **字符集**: 小写字母 + 数字（排除 0, O, 1, I, l）
- **生成**: 自动随机生成或自定义
- **唯一性**: 数据库唯一索引约束

---

## 快速开始

### 1. 启动 Web 服务

```bash
python run.py
```

服务默认运行在 `http://127.0.0.1:8888`

- **首页**: http://127.0.0.1:8888（输入短代码访问问卷）
- **默认问卷**: http://127.0.0.1:8888/study/default
- **管理后台**: http://127.0.0.1:8888/admin?pw=admin (默认密码: admin)
- **问卷列表**: http://127.0.0.1:8888/admin/studies

### 2. 环境变量配置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ADMIN_PASSWORD` | `admin` | 管理后台密码 |
| `SECRET_KEY` | `devsecret` | Flask 密钥 |

### 3. 创建新问卷

1. 访问 `/admin/studies`
2. 点击"创建新问卷"
3. 填写名称、描述，可选自定义短代码
4. 上传 `study_config.json` 配置文件
5. 获得短代码链接，分享给参与者

### 4. 配置文件结构

配置文件 `study_config.json` 结构:

```json
{
  "title": "User Study: 可控的情感图像内容生成",
  "instructions": "实验说明文本...",
  "randomize": true,
  "examples": [
    {
      "text": "理想特点1：情感表达准确",
      "images": ["/static/examples/example_good_emotion.png"]
    }
  ],
  "questions": [
    {
      "id": "q1-1",
      "prompt": "选择最能唤起'amusement'的图片",
      "images": [
        "/uploads/amusement/.../sdxl-xxx.png",
        "/uploads/amusement/.../ti-xxx.png",
        "/uploads/amusement/.../emogen-xxx.png",
        "/uploads/amusement/.../ours-xxx.png"
      ],
      "models": ["sdxl", "ti", "emogen", "ours"],
      "type": "choose_one"
    }
  ]
}
```

### 5. 自动生成配置

根据图片目录结构自动生成配置文件:

```bash
python scripts/generate_config.py --content-root "G:\emoemo_results\挑图\user_study" --output study_config.json
```

---

## 数据分析

### 导出数据

```bash
# 导出数据库到 CSV
python scripts/export_data.py

# 导出特定问卷数据
python scripts/export_data.py --study-code abc123
```

生成文件:
- `exports/responses_backup.csv` - 用户响应数据
- `exports/participants_backup.csv` - 参与者信息

### 运行分析

```bash
python scripts/analyze_results.py
```

分析内容包括:
1. **完成率分析** - 统计完成所有题目的用户比例
2. **偏好分析** - 各模型在情感维度和内容维度的得票率
3. **一致性分析** - 用户在两个维度选择相同模型的比例

---

## 图片处理

### 批量处理图片

```bash
python scripts/prepare_images.py --source-dir "G:\source" --target-dir "uploads"
```

处理流程:
1. 从源目录挑选图片
2. 按情感-内容结构组织
3. 中心裁剪为正方形
4. 缩放到 256x256 像素
5. 保存为 JPEG 格式（质量 85）

---

## 数据迁移

### 从旧版本迁移

如果是从 v2.0（单问卷）迁移到 v3.0（多问卷）:

```bash
python scripts/migrate_to_multi_study.py
```

迁移内容:
1. 创建 `studies` 表
2. 创建默认问卷（code: default）
3. 更新 `participants` 表添加 `study_id` 列
4. 将所有参与者关联到默认问卷
5. 更新 `responses` 表添加 `study_id` 列

---

## 管理后台功能

访问 `/admin?pw=ADMIN_PASS`:

1. **问卷管理**
   - 查看所有问卷列表
   - 创建新问卷
   - 查看问卷详情和统计
   - 更新问卷状态（激活/暂停/归档）

2. **配置上传** - 上传新的 study_config.json

3. **数据统计** - 查看问卷统计数据

4. **导出数据** - 下载 CSV 导出文件

5. **图表分析** - 可视化分析界面 (`/analysis`)
   - 模型总得票数柱状图
   - 情感维度得票数
   - 内容维度得票数

---

## 测试

运行测试套件:

```bash
python -m pytest tests/ -v
```

测试覆盖:
- API 路由测试
- 服务层测试
- 多问卷功能测试
- 短代码生成测试

---

## 相关文档

- **PRD**: `PRD.md` - 产品需求文档
- **README**: `README_FASTAPI.md` - FastAPI 版本使用说明
- **Scripts**: `scripts/README.md` - 工具脚本使用指南

---

## 外部访问

如需公网访问，可使用以下工具:

```bash
# ngrok
ngrok http 8888

# cloudflared
cloudflared tunnel --url http://localhost:8888
```

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0 | - | Flask单文件版本 |
| v2.0 | 2024-03 | FastAPI重构，解决并发问题 |
| v3.0 | 2024-03 | 多问卷支持，短代码系统，数据隔离 |

---

**文档结束**