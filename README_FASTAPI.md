# User Study Platform - FastAPI 多问卷版

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例配置文件并修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件，设置管理员密码：
```
ADMIN_PASSWORD=your-secure-password
```

### 3. 数据迁移（如果是旧版本升级）

```bash
# 从单问卷版本迁移到多问卷版本
python scripts/migrate_to_multi_study.py
```

### 4. 启动应用

**开发模式**（带热重载）：
```bash
python run.py --mode dev
```

**生产模式**（多进程）：
```bash
python run.py --mode prod --workers 4
```

### 5. 访问应用

- **首页**: http://localhost:8888/（输入短代码访问问卷）
- **管理后台**: http://localhost:8888/admin?pw=your-password
- **问卷列表**: http://localhost:8888/admin/studies
- **API 文档**: http://localhost:8888/docs

---

## 📁 项目结构

```
app/
├── __init__.py
├── main.py                  # FastAPI 应用入口
├── config.py                # 配置管理 (Pydantic Settings)
├── database.py              # 数据库连接 (SQLAlchemy)
├── models.py                # 数据库模型（含 Study, Participant, Response）
├── schemas.py               # Pydantic 数据验证
├── routers/
│   ├── public.py            # 公共路由（多问卷：/study/{code}/*）
│   ├── admin.py             # 管理后台（问卷管理、数据分析）
│   └── api.py               # RESTful API
├── services/
│   ├── study.py             # 研究逻辑（含多问卷支持）
│   ├── stats.py             # 统计服务
│   └── export.py            # 导出服务
├── templates/               # Jinja2 模板
│   ├── index.html           # 首页/问卷首页
│   ├── question.html        # 答题页面
│   ├── completed.html       # 完成页面
│   ├── admin.html           # 管理后台首页
│   ├── admin_studies.html   # 问卷列表
│   ├── admin_study_create.html  # 创建问卷
│   ├── admin_study_detail.html  # 问卷详情
│   └── analysis.html        # 数据分析
├── utils/
│   └── short_code.py        # 短代码生成工具
└── templates/               # HTML 模板

scripts/                     # 工具脚本
├── prepare_images.py        # 图片预处理
├── generate_config.py       # 配置生成
├── export_data.py           # 数据导出
├── analyze_results.py       # 结果分析
├── migrate_to_multi_study.py # 多问卷迁移
└── README.md                # 脚本使用说明

tests/                       # 测试文件
├── conftest.py              # 测试配置
├── test_api.py              # API 测试
└── test_services.py         # 服务测试

exports/                     # 导出文件目录
uploads/                     # 上传图片目录
static/                      # 静态资源
```

---

## 🎯 多问卷功能

### 创建问卷

1. 访问管理后台：`/admin/studies`
2. 点击"创建新问卷"
3. 填写问卷名称和描述
4. 可选：自定义短代码（如 `user24`）
5. 上传配置文件 `study_config.json`
6. 创建成功后获得访问链接

### 问卷访问

**方式1：通过短代码**
```
https://your-domain.com/study/{code}
```

**方式2：首页输入**
- 访问首页 `/`
- 输入短代码
- 进入对应问卷

**方式3：直接链接**
- 分享完整链接给参与者

### 问卷状态管理

| 状态 | 说明 | 访问权限 |
|------|------|----------|
| active | 进行中 | 允许新参与者 |
| paused | 暂停 | 禁止新参与者 |
| archived | 已归档 | 只读访问 |

在问卷详情页可以切换状态。

---

## ⚡ 性能优化

### 已实施的优化

1. **异步支持**: FastAPI 原生支持异步，提升并发处理能力
2. **数据库连接池**: SQLAlchemy 连接池，避免频繁创建连接
3. **SQLite WAL 模式**: 提升并发写入性能
4. **静态文件缓存**: 图片等静态资源添加缓存头
5. **GZip 压缩**: 自动压缩响应数据
6. **后台导出**: CSV 导出使用后台线程，不阻塞请求

### 多进程部署

生产环境建议使用多进程：

```bash
# 4 个工作进程
python run.py --mode prod --workers 4

# 或使用 Hypercorn（支持 HTTP/2）
pip install hypercorn
python run.py --mode hypercorn --workers 4
```

---

## 🔌 API 接口

### 健康检查
```bash
GET /api/health
```

### 问卷管理 API

#### 获取问卷列表
```bash
GET /admin/api/studies?pw=your-password
```

#### 创建问卷
```bash
POST /admin/studies/create?pw=your-password
Content-Type: multipart/form-data

name=问卷名称&description=描述&code=自定义代码&configfile=@study_config.json
```

#### 更新问卷状态
```bash
PUT /admin/api/studies/{code}/status?pw=your-password
Content-Type: application/json

{"status": "paused"}  # active | paused | archived
```

### 统计数据 API

#### 总体统计
```bash
GET /api/stats/overall?study_code={code}&api_key=your-password
```

#### 图表数据
```bash
GET /api/stats/charts?study_code={code}&api_key=your-password
```

#### 一致性分析
```bash
GET /api/stats/consistency?study_code={code}&api_key=your-password
```

### 数据导出 API

#### 创建导出任务
```bash
POST /api/export?study_code={code}&api_key=your-password
```

#### 查询任务状态
```bash
GET /api/export/{task_id}?api_key=your-password
```

完整 API 文档访问：`http://localhost:8888/docs`

---

## 🔄 向后兼容

旧版本的路由会自动重定向到新路由：

| 旧路径 | 重定向到 |
|--------|----------|
| `/start` | `/study/default/start` |
| `/question/{idx}` | `/study/default/question/{idx}` |
| `/completed` | `/study/default/completed` |

原有数据会自动迁移到 `default` 问卷。

---

## 🛡️ 安全建议

1. **修改默认密码**: 在生产环境务必修改 `ADMIN_PASSWORD`
2. **使用 HTTPS**: 生产环境配置 SSL 证书
3. **限制访问**: 使用防火墙限制管理后台 IP
4. **定期备份**: 定期备份 `user_study.db` 数据库
5. **短代码保密**: 分享问卷链接时注意不要泄露给其他研究组

---

## 🐛 故障排除

### 端口被占用
```bash
python run.py --port 8889
```

### 数据库锁定
如果提示数据库锁定，检查：
1. 是否有其他进程正在访问数据库
2. 磁盘空间是否充足

### 静态文件 404
确保 `uploads/` 和 `static/` 目录存在：
```bash
mkdir -p uploads static
```

### 短代码无效
- 检查是否使用了易混淆字符（0, O, 1, I, l）
- 确认短代码长度为6位
- 检查是否与其他问卷重复

---

## 📚 相关文档

- [PRD.md](PRD.md) - 产品需求文档
- [AGENTS.md](AGENTS.md) - 项目架构和上下文
- [scripts/README.md](scripts/README.md) - 工具脚本使用说明