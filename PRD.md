# Product Requirements Document (PRD)
# 可控情感图像内容生成 - 用户研究平台

**版本**: v3.0  
**日期**: 2024-03  
**状态**: 多问卷支持已上线

---

## 1. 产品概述

### 1.1 产品背景

在情感图像生成领域，需要评估不同模型在"情感表达准确性"和"内容语义一致性"两个维度的表现。本平台用于收集用户对多模型生成图像的主观评价，为模型改进提供数据支持。

### 1.2 产品目标

- **v1.0**: 基础问卷功能
- **v2.0**: FastAPI 重构，解决并发问题
- **v3.0**: 支持多问卷管理，每个问卷独立配置和数据

### 1.3 目标用户

| 角色 | 需求 |
|------|------|
| 研究人员 | 创建多个问卷、上传配置、查看统计数据、导出数据 |
| 实验参与者 | 通过短代码链接访问特定问卷、回答问题、提交评价 |
| 数据分析者 | 导出CSV、生成报告、图表分析 |

---

## 2. 功能需求

### 2.1 核心功能模块

```
┌─────────────────────────────────────────────────────────────┐
│                    User Study Platform v3.0                  │
├─────────────────┬─────────────────┬─────────────────────────┤
│   公共模块       │   管理模块       │    工具模块             │
├─────────────────┼─────────────────┼─────────────────────────┤
│ • 问卷首页       │ • 问卷列表       │ • 图片预处理            │
│ • 答题页面       │ • 创建问卷       │ • 配置生成              │
│ • 答案提交       │ • 数据统计       │ • 数据导出              │
│ • 完成页面       │ • 图表分析       │ • 结果分析              │
│                 │ • 数据导出       │ • 数据迁移              │
│                 │ • 状态管理       │                         │
└─────────────────┴─────────────────┴─────────────────────────┘
```

### 2.2 多问卷系统 (v3.0 新增)

#### 2.2.1 问卷管理

**问卷列表**
- 显示所有问卷及其状态（进行中/暂停/已归档）
- 显示每个问卷的参与人数
- 快速操作：查看、暂停/恢复、导出数据

**创建问卷**
- 输入问卷名称和描述
- 自动生成或自定义短代码（6位字符）
- 上传配置文件（study_config.json）

**短代码系统**
- 6位小写字母+数字组合
- 排除易混淆字符（0, O, 1, I, l）
- 示例：`abc123`, `study7`, `user24`

#### 2.2.2 问卷访问

**URL 结构**
- 问卷首页：`/study/{code}`
- 开始答题：`/study/{code}/start`
- 答题页面：`/study/{code}/question/{idx}`
- 完成页面：`/study/{code}/completed`

**数据隔离**
- 每个问卷的参与者数据独立
- 问卷间数据互不可见
- 通过 `study_id` 外键关联

### 2.3 问卷系统（单问卷功能）

**实验说明页**
- 显示研究标题和说明
- 展示示例图片和理想特征
- 开始实验按钮

**答题页面**
- 进度条显示当前进度
- 问题描述（内容+情感）
- 2x2 网格展示4张图片
- 点击选择+提交

**双维度评估**
- 问题-1: 情感维度（哪张图最能唤起目标情感）
- 问题-2: 内容维度（哪张图最符合内容描述）

**完成页面**
- 感谢参与提示
- 返回问卷首页链接

### 2.4 管理后台

**问卷管理**
- 问卷列表查看
- 创建新问卷
- 问卷状态管理（激活/暂停/归档）
- 问卷详情查看

**配置管理**
- 上传 study_config.json
- 配置预览
- 按问卷隔离配置

**数据统计**
- 按问卷统计参与者数、完成率、平均用时
- 每题统计（各选项选择次数）
- 模型统计（总得票数、情感/内容维度票数）

**图表分析**
- 模型总得票数柱状图
- 情感维度得票数横向柱状图
- 内容维度得票数横向柱状图
- 实时自动刷新（30秒）

**数据导出**
- 异步CSV导出（不阻塞页面）
- 可按问卷导出
- 导出任务状态查询
- 下载导出文件

---

## 3. 技术架构

### 3.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Bootstrap 5 + Jinja2 | 响应式设计 |
| 后端 | FastAPI | 异步高性能框架 |
| 数据库 | SQLite + SQLAlchemy | 轻量级，支持连接池 |
| 图表 | Chart.js | 可视化展示 |
| 进程 | Uvicorn | ASGI服务器，支持多进程 |

### 3.2 架构演进

```
v1.0 (Flask)         v2.0 (FastAPI)           v3.0 (多问卷)
────────────────────────────────────────────────────────────
单文件应用     →     模块化架构       →      多租户架构
单问卷支持     →     单问卷优化       →      多问卷隔离
无API文档      →     Swagger文档      →      多问卷API
同步处理       →     异步+连接池       →      数据隔离+迁移
```

### 3.3 目录结构

```
project/
├── app/                        # 主应用
│   ├── main.py                # FastAPI入口
│   ├── config.py              # 配置管理
│   ├── database.py            # 数据库连接
│   ├── models.py              # 数据模型（含Study）
│   ├── schemas.py             # Pydantic验证
│   ├── routers/               # 路由
│   │   ├── public.py          # 公共路由（多问卷）
│   │   ├── admin.py           # 管理后台（问卷管理）
│   │   └── api.py             # RESTful API
│   ├── services/              # 业务逻辑
│   │   ├── study.py           # 研究服务（含多问卷）
│   │   ├── stats.py           # 统计服务
│   │   └── export.py          # 导出服务
│   ├── templates/             # HTML模板
│   └── utils/                 # 工具函数
│       └── short_code.py      # 短代码生成
├── scripts/                   # 工具脚本
│   ├── prepare_images.py      # 图片预处理
│   ├── generate_config.py     # 配置生成
│   ├── export_data.py         # 数据导出
│   ├── analyze_results.py     # 结果分析
│   └── migrate_to_multi_study.py  # 多问卷迁移
├── uploads/                   # 上传的图片
├── exports/                   # 导出文件
├── tests/                     # 测试文件
└── static/                    # 静态资源
```

---

## 4. 数据模型

### 4.1 问卷 (Study) - v3.0 新增

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(UUID) | 主键 |
| code | String(20) | 短代码，唯一索引 |
| name | String | 问卷名称 |
| description | Text | 问卷描述 |
| config_json | Text | 配置JSON |
| status | String | 状态：active/paused/archived |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

### 4.2 参与者 (Participant)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String(UUID) | 主键 |
| study_id | String(UUID) | 外键 → Study.id |
| started_at | DateTime | 开始时间 |
| ip_address | String | IP地址 |
| user_agent | Text | 浏览器信息 |
| completed_at | DateTime | 完成时间 |

### 4.3 响应 (Response)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| participant_id | String(UUID) | 外键 → Participant.id |
| study_id | String(UUID) | 外键 → Study.id |
| question_id | String | 问题ID (如 q1-1) |
| selected_index | Integer | 选择索引 (0-3) |
| rating | Integer | 评分 (1-5) |
| comment | Text | 评论 |
| time_spent | Float | 用时(秒) |
| created_at | DateTime | 提交时间 |

### 4.4 关系图

```
┌─────────┐       ┌─────────────┐       ┌──────────┐
│  Study  │ 1    *│ Participant │ 1    *│ Response │
├─────────┤───────┼─────────────┤───────┼──────────┤
│ id      │       │ id          │       │ id       │
│ code    │       │ study_id    │       │ study_id │
│ name    │       │ started_at  │       │ ...      │
│ config  │       │ completed   │       │          │
└─────────┘       └─────────────┘       └──────────┘
```

---

## 5. 接口设计

### 5.1 RESTful API

#### 健康检查
```
GET /api/health
```

#### 问卷管理
```
GET    /admin/api/studies              # 获取问卷列表
POST   /admin/api/studies              # 创建问卷
GET    /admin/api/studies/{code}       # 获取问卷详情
PUT    /admin/api/studies/{code}/status # 更新问卷状态
DELETE /admin/api/studies/{code}       # 删除问卷
```

#### 统计数据
```
GET /api/stats/overall?study_code={code}&api_key={key}
GET /api/stats/charts?study_code={code}&api_key={key}
GET /api/stats/consistency?study_code={code}&api_key={key}
```

#### 数据导出
```
POST /api/export?study_code={code}&api_key={key}
GET  /api/export/{task_id}?api_key={key}
```

### 5.2 页面路由

#### 公共路由（多问卷）
| 路径 | 说明 |
|------|------|
| / | 首页（输入短代码） |
| /study/{code} | 问卷首页 |
| /study/{code}/start | 开始答题 |
| /study/{code}/question/{idx} | 答题页面 |
| /study/{code}/completed | 完成页面 |

#### 管理路由
| 路径 | 说明 |
|------|------|
| /admin | 管理后台首页 |
| /admin/studies | 问卷列表 |
| /admin/studies/create | 创建问卷 |
| /admin/study/{code} | 问卷详情 |
| /admin/analysis | 数据分析 |

#### 向后兼容（旧路由重定向）
| 旧路径 | 重定向到 |
|--------|----------|
| /start | /study/default/start |
| /question/{idx} | /study/default/question/{idx} |
| /completed | /study/default/completed |

---

## 6. 短代码系统

### 6.1 设计原则

- **长度**: 6位字符（可配置）
- **字符集**: 小写字母 + 数字，排除易混淆字符
- **排除字符**: 0, O, o, 1, I, l
- **可用字符**: abcdefghijklmnopqrstuvwxyz23456789

### 6.2 生成规则

```python
# 自动生成示例
generate_short_code()  # -> "abc123"
generate_short_code()  # -> "xyz789"

# 自定义代码（需符合规则）
code = "user24"  # ✓ 有效
code = "test-01" # ✗ 包含无效字符
```

### 6.3 使用场景

- **问卷分享**: `https://example.com/study/abc123`
- **二维码生成**: 基于短代码URL
- **数据分析**: 按问卷代码筛选数据

---

## 7. 性能要求

### 7.1 并发性能

- 支持 **50+** 用户同时答题
- 页面加载时间 < **2秒**
- API响应时间 < **200ms**

### 7.2 数据导出

- CSV导出支持 **10万+** 记录
- 异步导出不阻塞页面
- 导出任务状态实时查询

### 7.3 多问卷支持

- 支持 **100+** 问卷同时存在
- 问卷间数据完全隔离
- 切换问卷无延迟

---

## 8. 安全要求

### 8.1 认证授权

- 管理后台密码保护
- API密钥验证
- 问卷状态控制访问（暂停时不可答题）

### 8.2 数据保护

- 参与者ID使用UUID
- 不存储敏感个人信息
- 问卷数据隔离
- 定期备份数据库

### 8.3 短代码安全

- 短代码随机生成，不可预测
- 自定义代码需符合格式规则
- 代码唯一性校验

---

## 9. 部署运维

### 9.1 启动命令

```bash
# 开发模式（热重载）
python run.py --mode dev

# 生产模式（4工作进程）
python run.py --mode prod --workers 4
```

### 9.2 环境变量

```bash
ADMIN_PASSWORD=secure-password
SECRET_KEY=random-secret
DATABASE_URL=sqlite:///./user_study.db
WORKERS=4
```

### 9.3 数据迁移

```bash
# 从v2.0迁移到v3.0（多问卷）
python scripts/migrate_to_multi_study.py

# 检查迁移状态
python scripts/check_db.py
```

---

## 10. 使用流程

### 10.1 首次部署

1. 准备图片数据
2. 运行 `scripts/prepare_images.py`
3. 运行 `scripts/generate_config.py`
4. 配置 `.env` 文件
5. 启动应用 `python run.py --mode prod`

### 10.2 创建新问卷

1. 访问管理后台 `/admin/studies`
2. 点击"创建新问卷"
3. 输入问卷名称和描述
4. 上传配置文件
5. 获取短代码链接并分享

### 10.3 日常运维

1. 监控 `/api/health` 状态
2. 定期导出数据备份
3. 查看 `/admin/studies` 问卷状态
4. 使用 `scripts/analyze_results.py` 生成报告

---

## 11. 附录

### 11.1 情感类别

- amusement (愉悦)
- anger (生气)
- awe (敬畏)
- contentment (满足)
- disgust (厌恶)
- excitement (激动)
- fear (恐惧)
- sadness (悲伤)

### 11.2 对比模型

- sdxl: Stable Diffusion XL
- ti: Textual Inversion
- emogen: EmoGen
- ours: 研究团队模型

### 11.3 配置文件示例

```json
{
  "title": "User Study",
  "instructions": "实验说明...",
  "randomize": true,
  "examples": [...],
  "questions": [
    {
      "id": "q1-1",
      "prompt": "选择最能唤起情感的一张",
      "images": ["/uploads/..."],
      "models": ["sdxl", "ti", "emogen", "ours"],
      "type": "choose_one"
    }
  ]
}
```

---

## 12. 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0 | - | Flask单文件版本 |
| v2.0 | 2024-03 | FastAPI重构，解决并发问题，添加API文档 |
| v3.0 | 2024-03 | 多问卷支持，短代码系统，数据隔离 |

---

**文档结束**