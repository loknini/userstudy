# User Study 项目使用说明

## 🚀 快速启动（3步搞定）

### 前提条件
- ✅ Python 3.9+ 已安装
- ✅ Git（可选，如果需要版本管理）

---

### 步骤1：安装依赖

```bash
cd D:\project\userstudy
pip install -r requirements.txt
```

**预计时间：** 2-5分钟（取决于网络速度）

---

### 步骤2：配置环境变量（可选）

```bash
# 复制示例配置文件
copy .env.example .env

# 编辑 .env 文件（设置管理员密码）
notepad .env
```

**最小配置（.env文件）：**
```
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=your-admin-password
HOST=0.0.0.0
PORT=8888
```

**如果不配置：** 使用默认设置（密码：`admin123`，端口：`8888`）

---

### 步骤3：启动项目

#### 方式A：开发模式（推荐，支持热重载）

```bash
python run.py --mode dev
```

**特点：**
- ✅ 修改代码后自动重启
- ✅ 适合开发调试
- ✅ 日志详细

#### 方式B：生产模式（高性能）

```bash
python run.py --mode prod --workers 4
```

**特点：**
- ✅ 多进程，性能更好
- ✅ 适合实际部署
- ⚠️ 修改代码后需手动重启

---

### 步骤4：访问项目

启动成功后，浏览器打开：

| 页面 | 地址 | 说明 |
|------|------|------|
| **首页** | http://localhost:8888/ | 输入问卷代码 |
| **管理后台** | http://localhost:8888/admin?pw=你的密码 | 管理问卷和查看数据 |
| **API文档** | http://localhost:8888/docs | 自动生成的API文档 |

---

## 📝 创建第一个问卷

### 方法1：使用配置文件（推荐）

#### 1. 准备图片
将图片放到 `uploads/` 目录下，按情感分类：
```
uploads/
├── amusement/
│   ├── A house in a garden/
│   │   ├── sdxl-A house in a garden.-amusement_sdxl.jpg
│   │   ├── emo-A house in a garden.-amusement_ti.jpg
│   │   ├── emo-A house in a garden.-amusement_emogen.jpg
│   │   └── 55-A house in a garden.-amusement_ours.jpg
│   └── ...
├── anger/
└── ...
```

#### 2. 创建配置文件 `study_config.json`

参考 `study_config.json.example`，创建你的配置：

```json
{
  "title": "我的用户研究",
  "instructions": "欢迎参与实验...",
  "randomize": true,
  "questions": [
    {
      "id": "q1",
      "prompt": "请从以下图片中选择最符合描述的",
      "images": [
        "/uploads/amusement/A house in a garden/sdxl-A house in a garden.-amusement_sdxl.jpg",
        "/uploads/amusement/A house in a garden/emo-A house in a garden.-amusement_ti.jpg",
        "/uploads/amusement/A house in a garden/emo-A house in a garden.-amusement_emogen.jpg",
        "/uploads/amusement/A house in a garden/55-A house in a garden.-amusement_ours.jpg"
      ],
      "models": ["sdxl", "ti", "emogen", "ours"],
      "type": "choose_one"
    }
  ]
}
```

**⚠️ 关键：** `images` 数组的长度就是每道题的图片数量，现在**已经支持自定义数量了**！

#### 3. 通过管理后台上传配置

1. 访问 http://localhost:8888/admin?pw=你的密码
2. 点击 "创建新问卷"
3. 填写问卷名称、描述
4. 上传 `study_config.json` 文件
5. 系统会生成一个 **6位短代码**（如：`abc123`）
6. 分享链接给参与者：`http://localhost:8888/study/abc123`

---

### 方法2：使用脚本生成配置（高级）

```bash
# 处理图片（调整尺寸、生成缩略图）
python scripts/process_images.py --source-dir "path/to/raw/images" --target-dir uploads

# 生成配置文件模板
python scripts/generate_config.py --output study_config.json

# 手动编辑生成的配置文件，然后上传
```

---

## 📊 查看结果

### 实时统计

访问管理后台：http://localhost:8888/admin?pw=你的密码

**功能：**
- 📈 查看参与人数、完成率
- 📊 查看每个问题的回答分布
- 📥 导出数据到CSV

### 导出数据

```bash
# 导出所有回答
python scripts/export_data.py --output responses.csv

# 导出参与者信息
python scripts/export_participants.py --output participants.csv
```

---

## 🔧 常用命令

### 启动/停止

```bash
# 开发模式启动
python run.py --mode dev

# 生产模式启动（4个工作进程）
python run.py --mode prod --workers 4

# 停止：按 Ctrl+C
```

### 数据库备份

```bash
# 备份数据库
copy user_study.db user_study.db.backup.%date:~0,4%%date:~5,2%%date:~8,2%

# 恢复数据库
copy user_study.db.backup.20260531 user_study.db
```

### 清空数据库（慎用！）

```bash
# 删除数据库文件
del user_study.db

# 重新启动，会自动创建新的空数据库
python run.py --mode dev
```

---

## 🐳 使用Docker（可选）

### 快速启动

```bash
# 使用 docker-compose（推荐）
cd D:\project\userstudy
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 手动构建

```bash
# 构建镜像
docker build -t userstudy:latest .

# 运行容器
docker run -d --name userstudy -p 8888:8888 userstudy:latest
```

---

## 🔍 故障排查

### 问题1：端口被占用

**错误信息：** `OSError: [WinError 10048] 通常每个套接字地址...`

**解决方案：**

```bash
# 查找占用端口的进程
netstat -ano | findstr :8888

# 结束进程（替换 PID）
taskkill /PID <PID> /F

# 或者修改端口
python run.py --mode dev --port 8889
```

---

### 问题2：依赖安装失败

**错误信息：** `pip install` 报错

**解决方案：**

```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 问题3：数据库被锁定

**错误信息：** `sqlite3.OperationalError: database is locked`

**解决方案：**

```bash
# 检查是否有多个进程在访问数据库
# 停止所有Python进程，然后重新启动
```

---

### 问题4：图片不显示

**可能原因：**
1. 图片路径错误（检查 `study_config.json` 中的路径）
2. 图片未放到 `uploads/` 目录
3. 文件路径包含中文或特殊字符

**解决方案：**

```bash
# 检查图片是否可以访问
# 在浏览器中打开：http://localhost:8888/uploads/your-image.jpg
```

---

## 📁 项目结构速查

```
userstudy/
├── app/
│   ├── main.py           # FastAPI应用入口
│   ├── routers/          # 路由（公共页面、管理后台、API）
│   ├── services/         # 业务逻辑（答题、统计）
│   ├── templates/        # HTML模板（Jinja2）
│   └── utils/           # 工具函数（短代码生成等）
├── scripts/              # 工具脚本（处理图片、导出数据等）
├── tests/               # 测试文件
├── uploads/             # 上传的图片（需要你自己放）
├── exports/             # 导出的数据（CSV等）
├── user_study.db        # SQLite数据库（自动创建）
├── study_config.json     # 研究配置文件
├── run.py               # 启动脚本
├── requirements.txt      # Python依赖
└── README.md           # 项目说明
```

---

## 💡 开发建议

### 修改代码后

**开发模式（--mode dev）：** 自动重启，无需手动操作

**生产模式（--mode prod）：** 需要手动重启

```bash
# 停止：Ctrl+C
# 重新启动：
python run.py --mode prod --workers 4
```

### 查看API文档

访问：http://localhost:8888/docs

**功能：**
- 📖 查看所有API接口
- 🧪 在线测试API
- 📝 查看请求/响应格式

---

## 🆘 需要帮助？

**遇到问题了？**

1. 查看终端日志（启动时的输出）
2. 查看 `logs/` 目录下的日志文件（如果有配置）
3. 告诉我具体的错误信息和操作步骤，我来帮你解决！

---

## ✅ 验证安装成功

**启动后，你应该看到：**

```
🔄 启动开发服务器（热重载已启用）...
INFO:     Uvicorn running on http://0.0.0.0:8888 (Press CTRL+C to quit)
INFO:     Started reloader process [12345] using WatchFiles
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**然后浏览器访问：** http://localhost:8888/

**应该看到：** 一个输入框，提示输入问卷代码

---

## 🎉 开始使用吧！

现在你已经成功启动项目了！

**下一步：**
1. 准备图片数据
2. 创建 `study_config.json` 配置文件
3. 通过管理后台上传配置
4. 分享短代码给参与者

**有问题随时问我！** 😊
