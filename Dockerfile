# 使用 Python 3.12 作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY static/ ./static/
COPY study_config.json .
COPY run.py .

# 创建上传目录
RUN mkdir -p uploads uploads_backup exports

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8888

# 启动命令
CMD ["python", "run.py", "--mode", "prod", "--host", "0.0.0.0", "--port", "8888"]
