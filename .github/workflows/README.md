# CI/CD 配置说明

本目录包含 GitHub Actions 的持续集成/持续部署 (CI/CD) 配置。

## 📋 工作流说明

### 1. CI (ci.yml) - 持续集成

**触发条件：**
- 推送到 `main` 或 `develop` 分支
- 提交 Pull Request

**执行步骤：**

| 任务 | 说明 |
|------|------|
| `test` | 运行 Python 测试套件，生成覆盖率报告 |
| `lint` | 代码格式检查（black, isort, flake8） |
| `build-docker` | 构建 Docker 镜像验证 |

### 2. CD (cd.yml) - 持续部署

**触发条件：**
- 推送到 `main` 分支
- 发布新版本 (Release)

**执行步骤：**

| 任务 | 说明 |
|------|------|
| `build-and-push` | 构建并推送 Docker 镜像到 GitHub Container Registry |
| `deploy` | 通过 SSH 自动部署到生产服务器 |

## 🔧 配置方法

### 1. 启用 GitHub Actions

无需额外操作，推送代码后自动启用。

### 2. 配置部署密钥

如果要启用自动部署到服务器，需要在 GitHub 仓库设置中添加以下 Secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `SERVER_HOST` | 服务器 IP 地址或域名 |
| `SERVER_USER` | SSH 用户名（如 `root`） |
| `SSH_PRIVATE_KEY` | SSH 私钥（用于免密登录） |

**添加步骤：**

1. 生成 SSH 密钥对：
```bash
ssh-keygen -t ed25519 -C "github-actions"
```

2. 将公钥添加到服务器：
```bash
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
```

3. 在 GitHub 仓库页面 → Settings → Secrets and variables → Actions → New repository secret

4. 添加以下 secrets：
   - `SERVER_HOST`: 你的服务器 IP
   - `SERVER_USER`: root（或其他用户名）
   - `SSH_PRIVATE_KEY`: 私钥内容（`cat ~/.ssh/id_ed25519`）

## 📊 查看执行结果

在 GitHub 仓库页面：
- **Actions** 标签页查看所有工作流运行记录
- **Packages** 标签页查看构建的 Docker 镜像

## 🚀 部署流程

```
1. 开发者推送代码到 main 分支
         ↓
2. GitHub Actions 自动运行测试
         ↓
3. 测试通过后构建 Docker 镜像
         ↓
4. 镜像推送到 GitHub Container Registry
         ↓
5. 自动部署到生产服务器
         ↓
6. 服务更新完成！
```

## 📝 手动触发部署

如果需要手动触发部署，可以使用以下命令：

```bash
# 在 GitHub 网页上
# Actions → CD → Run workflow

# 或者在本地强制推送触发
git commit --allow-empty -m "Trigger deployment"
git push origin main
```

## 🔍 故障排查

如果部署失败：

1. 查看 **Actions** 页面的错误日志
2. 检查服务器 Secrets 配置是否正确
3. 确认服务器上 Docker 是否正常运行
4. 检查服务器磁盘空间是否充足

## 📚 相关文档

- [GitHub Actions 文档](https://docs.github.com/cn/actions)
- [Docker Buildx](https://docs.docker.com/buildx/working-with-buildx/)
- [GitHub Container Registry](https://docs.github.com/cn/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
