#!/bin/bash
# 部署脚本

set -e

echo "🚀 开始部署 User Study Platform..."

# 配置
APP_NAME="userstudy"
DOMAIN="${DOMAIN:-your-domain.com}"
EMAIL="${EMAIL:-your-email@example.com}"

# 更新系统
echo "📦 更新系统..."
sudo apt-get update
sudo apt-get upgrade -y

# 安装必要软件
echo "📦 安装必要软件..."
sudo apt-get install -y python3.12 python3.12-venv python3-pip nginx certbot python3-certbot-nginx git

# 克隆代码
echo "📂 克隆代码..."
if [ ! -d "/opt/$APP_NAME" ]; then
    sudo git clone https://github.com/your-username/userstudy.git /opt/$APP_NAME
fi
cd /opt/$APP_NAME
sudo git pull

# 创建虚拟环境
echo "🐍 创建虚拟环境..."
if [ ! -d "venv" ]; then
    sudo python3.12 -m venv venv
fi
source venv/bin/activate

# 安装依赖
echo "📦 安装依赖..."
pip install -r requirements.txt
pip install gunicorn

# 创建环境变量文件
echo "🔑 配置环境变量..."
if [ ! -f ".env" ]; then
    sudo bash -c 'cat > .env << EOF
ADMIN_PASSWORD=change-this-password
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=sqlite:///./user_study.db
EOF'
fi

# 创建数据目录
sudo mkdir -p uploads uploads_backup exports

# 配置 Nginx
echo "🌐 配置 Nginx..."
sudo cp nginx.conf /etc/nginx/sites-available/$APP_NAME
sudo sed -i "s/your-domain.com/$DOMAIN/g" /etc/nginx/sites-available/$APP_NAME
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# 配置 SSL
echo "🔒 配置 SSL..."
if [ "$DOMAIN" != "your-domain.com" ]; then
    sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL
fi

# 创建 systemd 服务
echo "⚙️ 创建系统服务..."
sudo bash -c "cat > /etc/systemd/system/$APP_NAME.service << EOF
[Unit]
Description=User Study Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/$APP_NAME
Environment=PATH=/opt/$APP_NAME/venv/bin
ExecStart=/opt/$APP_NAME/venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 127.0.0.1:8888
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"

# 启动服务
echo "🚀 启动服务..."
sudo systemctl daemon-reload
sudo systemctl enable $APP_NAME
sudo systemctl restart $APP_NAME

# 检查状态
echo "✅ 检查服务状态..."
sudo systemctl status $APP_NAME --no-pager

echo ""
echo "🎉 部署完成！"
echo "访问地址: https://$DOMAIN"
echo "管理后台: https://$DOMAIN/admin"
echo ""
echo "查看日志: sudo journalctl -u $APP_NAME -f"
