# HR 人力池系统

菲律宾马尼拉招聘场景的申请人管理系统，三端一体。

| 端 | 技术栈 | 目录 | 开发端口 |
|---|---|---|---|
| H5 自助申请端 | Vue 3 + Vite + Vant | `h5/` | 5173 |
| 管理后台 | Vue 3 + Vite + Element Plus | `admin/` | 5174 |
| 后端 API | FastAPI + SQLAlchemy 2.0 + Pydantic v2 | `backend/` | 8000 |

生产部署：Docker Compose + 内部 Nginx 单入口，GitHub Actions 自动构建并 SSH 部署到指定机器。

---

## 📌 给 AI 助手（或新协作者）的阅读指引

1. **先读 [`项目设计说明书.md`](项目设计说明书.md)** —— 业务场景、用户角色、技术选型、数据模型、分期规划全貌都在这里，是理解本项目的最佳入口。
2. **再看本文件** —— 环境要求、启动顺序、必须替换的占位符。
3. **换新电脑时看 [`新机器搭建指南.md`](新机器搭建指南.md)** —— 从零安装软件、初始化 MySQL、Docker 启动、验证清单、常见问题排查，以及可直接粘贴给 TRAE 的启动指令。
4. **代码入口**：[`backend/app/main.py`](backend/app/main.py)（后端路由挂载）、[`backend/app/models.py`](backend/app/models.py)（8 张表映射）、[`h5/src/views/ApplyForm.vue`](h5/src/views/ApplyForm.vue)、[`admin/src/views/ApplicantList.vue`](admin/src/views/ApplicantList.vue)。
5. **⚠️ 请跳过以下目录** —— 它们是**交付报告产物、监理日志或过程草稿，不是源码**，尤其不要打开 `_shared/js/` 下的压缩库，会白白占满上下文：
   - `hr-backend-api-delivery/`（含 `mermaid.min.js` 2.5MB、`echarts.min.js` 1MB）
   - `.trae-html-share-packages/`（含 1.1MB 二进制 zip）
   - `.agent/`、`docs/handoffs/`、`docs/superpowers/`、`docs/agent-supervision/`

---

## 一、环境要求

| 组件 | 版本 | 说明 |
|---|---|---|
| Python | **3.12 或 3.13** | 用 `py -3.13`；**不要用 3.14**（部分三方库预编译包未适配） |
| Node.js | **22 LTS** | 前端构建；CI 固定 22，本地更高版本可用但**不作为基线** |
| MySQL | **5.7.32+（兼容 8.x）** | 字符集 `utf8mb4`；本项目 SQL 未使用 8.0 专属语法 |
| Docker | Engine 24+ / Compose v2.20+ | 生产容器化部署；Compose 需要 `--wait` 支持 |

---

## 二、Docker 一键启动（推荐）

### 2.1 容器架构

```text
浏览器
  │  :80
  ▼
web 容器（Nginx，唯一对外入口）
  ├── /             → H5 静态文件
  ├── /admin/       → 管理后台静态文件（Vite base = /admin/）
  ├── /api/         → backend:8000（FastAPI）
  ├── /uploads/     → 404（不再公开；照片/视频经 /api/media/{token} 签名读取）
  └── /docs         → backend:8000（OpenAPI 文档）
                       │
                       ▼
              宿主机 MySQL 5.7.32
              db=hr_system / user=hr_system
```

- 只有 `web` 映射宿主机端口，`backend` 仅加入 Compose 内部网络，不对外暴露 8000。
- 上传文件保存在命名卷 `uploads`，执行 `docker compose down` 不会删除数据；`down -v` 会删除。
- 两个前端同源托管，不需要跨域配置；`/api` 由 Nginx 反代。

> 如果宿主机 80/443 已被现有 Nginx 站点占用，**不要停宿主机 Nginx**。把 Docker 的 `HTTP_PORT` 设为 `127.0.0.1:8080`，再用 [`deploy/host-nginx.conf.example`](deploy/host-nginx.conf.example) 在宿主机 Nginx 增加一个 `server_name` 反代到 `127.0.0.1:8080`。当前目标机采用的就是这种形态，现有站点不受影响。

### 2.2 首次启动

```bash
cp .env.docker.example .env
# 编辑 .env：至少填写 DB_PASSWORD、JWT_SECRET
openssl rand -hex 32                 # 生成 JWT_SECRET

docker compose up -d --build
docker compose ps
```

> 首次构建需要从 Docker Hub 拉取 `python:3.12-slim`、`node:22-alpine`、`nginx:1.27-alpine`。如果国内网络拉取超时，请先为 Docker Desktop / Engine 配置镜像加速器，或在可访问 Docker Hub 的机器上构建。

访问地址：

| 服务 | 地址 |
|---|---|
| H5 自助申请 | `http://<服务器IP或域名>/` |
| 管理后台 | `http://<服务器IP或域名>/admin/` |
| 健康检查 | `http://<服务器IP或域名>/healthz`（Nginx）与 `/api/health`（含数据库状态） |
| OpenAPI 文档 | `http://<服务器IP或域名>/docs` |

常用命令：

```bash
docker compose logs -f backend       # 后端日志
docker compose logs -f web           # Nginx 日志
docker compose restart backend       # 只重启后端
docker compose down                  # 停止服务，保留上传文件
```

### 2.3 MySQL 5.7.32 连接准备

容器里的 `backend` 通过 `host.docker.internal` 访问宿主机 MySQL。宿主机需要满足：

1. **Linux 宿主机上 MySQL 监听地址不能只绑定 `127.0.0.1`**，否则 Docker 网段连不进来（Docker Desktop 的 `host.docker.internal` 通常可直接访问本机 localhost）。可在 MySQL 配置中设置：

   ```ini
   [mysqld]
   bind-address = 0.0.0.0
   ```

   > 绑定 `0.0.0.0` 后请用防火墙/安全组限制 3306 只允许受信网段，不要直接暴露公网。

2. **`hr_system` 用户允许 Docker 网段登录**。如果现有用户只允许 `localhost`，容器会报 `Access denied`。用 root 登录 MySQL 执行：

   ```sql
   CREATE USER IF NOT EXISTS 'hr_system'@'%' IDENTIFIED BY '<数据库密码>';
   GRANT ALL PRIVILEGES ON hr_system.* TO 'hr_system'@'%';
   FLUSH PRIVILEGES;
   ```

   > 更严格的做法是把 `%` 换成实际 Docker 网段（如 `172.17.%`）；不确定网段时先用 `%` 验证连通性。

3. **数据库与表已初始化**。全新数据库执行：

   ```bash
   mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS hr_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
   mysql -u root -p < database/schema.sql
   mysql -u root -p < database/seed.sql
   ```

4. **验证容器到数据库的连通性**：

   ```bash
   docker compose exec backend python -c \
     "from sqlalchemy import text; from app.database import engine; print(engine.connect().execute(text('SELECT 1')).scalar())"
   ```

输出 `1` 即连接成功。如果 `host.docker.internal` 不通（部分 Linux / rootless Docker），可把 `.env` 中的 `DB_HOST` 改为 Docker 网关 IP（常见为 `172.17.0.1`）；MySQL 不在宿主机时改为实际可达地址。

### 2.4 关键容器文件

| 文件 | 作用 |
|---|---|
| `backend/Dockerfile` | FastAPI 镜像，非 root 运行，内置数据库健康检查 |
| `deploy/docker/web.Dockerfile` | 多阶段构建 H5 + 管理后台，产物打进 Nginx 镜像 |
| `deploy/nginx.docker.conf` | 单入口 Nginx：静态站点 + `/api` + `/docs` 反代；`/uploads/` 直接 404 |
| `docker-compose.yml` | 本地/单机构建启动 |
| `deploy/docker-compose.prod.yml` | 服务器部署用（只拉镜像，不在服务器构建） |
| `.env.docker.example` | Compose 环境变量模板 |

### 2.5 宿主机已有 Nginx 时

1. `.env` 或 GitHub Variable 中设置 `HTTP_PORT=127.0.0.1:8080`，让容器只绑定回环地址。
2. 复制 [`deploy/host-nginx.conf.example`](deploy/host-nginx.conf.example) 到宿主机 vhost 目录，按实际路径和域名修改 `server_name`。
3. 校验并重载：

   ```bash
   nginx -t && systemctl reload nginx
   ```

容器内 Nginx 已启用 `realip`，只信任回环/私网来源的 `X-Forwarded-For`，因此经过宿主机反代后后端仍能拿到真实客户端 IP。

示例（BaoTa 面板）：

```bash
cp deploy/host-nginx.conf.example /www/server/panel/vhost/nginx/hr-contest.conf
nginx -t && systemctl reload nginx
```

---

## 三、本地开发启动

### 第 1 步：数据库

```bash
mysql -u root -p < database/schema.sql   # 初始化表结构（全新库）
mysql -u root -p < database/seed.sql     # 写入初始管理员账号
```

> `schema.sql` 只用于全新库初始化；后续表结构变更以 `backend/app/models.py` 为准，通过 Alembic 迁移执行。

初始管理员：**`admin`**（参赛演示版密码随机生成，由参赛者单独保管，不写入仓库）

### 第 2 步：后端

```powershell
cd backend
py -3.13 -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env                   # 然后按实际环境修改 .env
venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers --forwarded-allow-ips 127.0.0.1
```

也可以直接双击根目录的 `启动后端.bat`。

> **代理头与限流**：启动脚本带 `--proxy-headers --forwarded-allow-ips 127.0.0.1`。
> 只有来自本机 Nginx 的 `X-Forwarded-For` 会被采信，客户端自己伪造无效；限流按真实 IP 生效。
> 若通过 `FORWARDED_ALLOW_IPS`（或 `--forwarded-allow-ips`）配置可信代理网段，生产容器环境建议收紧为 Docker 内网/反代网段，避免无条件使用 `*` 放开所有来源；同时请让后端只监听 `127.0.0.1`（或防火墙封禁 8000），避免绕过 Nginx 直连伪造该头。

- 接口文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health （应返回 `{"status":"ok","database":"connected"}`）

**`.env` 关键项**（模板见 [`backend/.env.example`](backend/.env.example)）：

| 变量 | 说明 |
|---|---|
| `APP_ENV` | 运行环境标识（默认 `development`；设为 `production` 时强制校验 `JWT_SECRET` 强度并默认关闭 API 文档） |
| `ENABLE_API_DOCS` | 是否开放 `/docs`、`/redoc`、`/openapi.json`（留空时由 `APP_ENV` 自动决定，生产默认 `false`） |
| `CORS_ORIGINS` | 逗号分隔的允许跨域来源（开发默认 `*`，生产同源托管可留空或设为线上域名） |
| `FORWARDED_ALLOW_IPS` | Uvicorn 可信反代 IP/网段（配合 `--proxy-headers` 解析真实客户端 IP，生产建议限定为反代网段） |
| `DATABASE_URL` | 完整 MySQL 连接串；留空时使用下面的 `DB_*` 分段配置 |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | MySQL 分段配置，密码含特殊字符时会自动转义 |
| `JWT_SECRET` | 生产环境请换成随机长字符串（`APP_ENV=production` 时至少 32 位且禁止占位值） |
| `OSS_*` | 阿里云 OSS 配置。**留空即自动降级为本地磁盘存储**（`backend/app/uploads/`），本地开发无需配置 |
| `VITE_FB_PAGE_USERNAME` | H5 构建期环境变量（见 `h5/src/views/ApplySuccess.vue`）：配置 Facebook 主页用户名后，提交成功页展示 Messenger 联系按钮 |

> **上传安全与配额**
> - 匿名上传：每 IP 50 次 / 500MB / 天，外加 10 次/分钟；提交 5 次/分钟、手机号预检 20 次/分钟
> - 已登录员工（扫楼代录）：上传、提交、预检**均不限次数**，账号可追溯、可停用
> - 所有上传仍受单文件 100MB 与磁盘水位保护（剩余 < 5GB 时返回 503）
> - 照片/视频不再公开可读，后台经短时效签名 URL 读取；启用 OSS 时 bucket 必须设为**私有读**
> - 数值可用 `UPLOAD_ANON_DAILY_REQUESTS`、`UPLOAD_ANON_DAILY_BYTES`、`UPLOAD_ANON_PER_MINUTE`、`UPLOAD_MIN_FREE_DISK_BYTES` 覆盖

### 第 3 步：H5 自助申请端

```powershell
cd h5
npm install
npm run dev        # http://localhost:5173/apply
```

### 第 4 步：管理后台

```powershell
cd admin
npm install
npm run dev        # http://localhost:5174/login
```

> 两个前端都通过 `vite.config.js` 把 `/api` 代理到 `http://localhost:8000`，所以**后端必须先跑起来**。

### 第 5 步：传统 Nginx 部署（可选，未使用 Docker 时）

如果不用 Docker，生产仍可走 **Nginx 同源托管**：

1. `npm run build` 分别构建 `h5/`、`admin/`，产物在各自 `dist/`。
2. 复制 [`deploy/nginx.conf.example`](deploy/nginx.conf.example) 到 `/etc/nginx/conf.d/hr.conf`，替换 `server_name` 与两个 `root` 路径。
3. 后端启动参数改为 `--host 127.0.0.1`（只让 Nginx 访问）。
4. 确认 `client_max_body_size 110m` —— 小于 105m 会让大视频直接吃 Nginx 的 413，绕过后端校验。

> 管理后台构建时 `base` 自动设为 `/admin/`，静态资源会输出到 `dist/assets` 并以 `/admin/assets/...` 访问；`deploy/nginx.conf.example` 的 `/admin/` 反代/别名配置已按此路径准备。

| 模板中的占位 | 替换为 |
|---|---|
| `hr.example.com` | 线上域名 |
| `/var/www/hr/h5`、`/var/www/hr/admin` | 两个 `dist/` 的实际部署路径 |
| `/var/www/hr/uploads` | 本地兜底上传目录（用 OSS 时可删掉整个 location） |

---

## 四、GitHub Actions 自动构建与部署

工作流文件：[`.github/workflows/docker-deploy.yml`](.github/workflows/docker-deploy.yml)

### 4.1 触发与流程

- 推送到 `main` 分支自动触发；也可以在 Actions 页面手动 `Run workflow`。
- CI 并行构建两个镜像并推送到 GHCR：
  - `ghcr.io/<owner>/hr-contest-backend:latest` 与 `:sha-<commit>`
  - `ghcr.io/<owner>/hr-contest-web:latest` 与 `:sha-<commit>`
- 部署 Job 通过 SSH 登录目标机器，把 `.env`、`docker-compose.prod.yml`、`remote-deploy.sh` 放到部署目录。
- 目标机拉取私有 GHCR 包时使用本次 workflow 的临时 `GITHUB_TOKEN`，无需单独创建 PAT；脚本在拉取完成后自动登出。
- 目标机器执行 `docker compose pull` + `docker compose up -d --remove-orphans --wait`，**自动完成重启**，无需手工停服。

### 4.2 需要在 GitHub 配置的 Variables

位置：仓库 `Settings → Secrets and variables → Actions → Variables`。

| Variable | 是否必填 | 示例 / 默认 | 说明 |
|---|---|---|---|
| `DEPLOY_HOST` | 必填 | `1.2.3.4` 或 `hr.example.com` | 目标机器地址 |
| `DEPLOY_USER` | 必填 | `deploy` | SSH 用户；需有 Docker 权限 |
| `DEPLOY_PORT` | 可选 | `22` | SSH 端口 |
| `DEPLOY_PATH` | 可选 | `/opt/hr-contest` | 目标机部署目录 |
| `DEPLOY_SSH_FINGERPRINT` | 可选 | `SHA256:...` | 目标机 SSH host key 指纹，配置后可防止中间人；取法见 4.5，注意要用 ECDSA 指纹 |
| `HTTP_PORT` | 可选 | `80` 或 `127.0.0.1:8080` | Docker Web 的宿主机绑定；宿主机已有 Nginx 时用 `127.0.0.1:8080` 并配合宿主机反代 |
| `DB_HOST` | 可选 | `host.docker.internal` | 容器视角的 MySQL 地址 |
| `DB_PORT` | 可选 | `3306` | MySQL 端口 |
| `DB_NAME` | 可选 | `hr_system` | 数据库名 |
| `DB_USER` | 可选 | `hr_system` | 数据库用户 |
| `DOCKER_PLATFORM` | 可选 | `linux/amd64` | 目标机架构；ARM 机器填 `linux/arm64` |
| `OSS_REGION` | 可选 | `ap-southeast-6` | 使用 OSS 时填写 |
| `VITE_OSS_DOMAIN` | 可选 | `your-bucket.oss-ap-southeast-6.aliyuncs.com` | 使用 OSS 时，管理后台展示媒体文件的域名（构建期写入前端） |
| `VITE_FB_PAGE_USERNAME` | 可选 | `your.fb.page` | H5 提交成功页（`h5/src/views/ApplySuccess.vue`）跳转 `m.me/<username>` 的 Facebook 主页用户名（构建期写入前端） |
| `CORS_ORIGINS` | 可选 | `https://your-hr-domain.example.com` | 后端允许的跨域来源（逗号分隔） |

### 4.3 需要在 GitHub 配置的 Secrets

位置：仓库 `Settings → Secrets and variables → Actions → Secrets`。

| Secret | 是否必填 | 说明 |
|---|---|---|
| `DEPLOY_SSH_KEY` | 必填 | 目标机 SSH 私钥（建议专用 deploy key，不要用个人主密钥） |
| `DB_PASSWORD` | 必填 | MySQL `hr_system` 用户密码 |
| `JWT_SECRET` | 必填 | 随机长字符串，建议 `openssl rand -hex 32` |
| `GHCR_USERNAME` | 可选 | 仅在手动拉取或临时 token 权限不足时填写；自动部署默认使用 `github.actor` |
| `GHCR_READ_TOKEN` | 可选 | 仅在手动拉取或临时 token 权限不足时填写；自动部署默认使用 workflow 的 `GITHUB_TOKEN` |
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_ROLE_ARN` / `OSS_BUCKET` / `OSS_ENDPOINT` | 可选 | 使用阿里云 OSS 时配置，留空则用本地磁盘 |

### 4.4 目标机器前置条件

```bash
# 1. 已安装 Docker Engine 24+ 与 Docker Compose v2.20+
docker --version
docker compose version

# 2. SSH 用户可执行 docker（加入 docker 组后重新登录）
sudo usermod -aG docker "$USER"

# 3. 防火墙放行 HTTP_PORT（默认 80）
# 4. 本机 MySQL 按 2.3 节允许容器网段访问
```

### 4.5 部署目标机配置与取指纹

目标机的公网 IP、SSH 账号、部署目录等**具体值属于部署机密，不写入本仓库**；请在 GitHub Actions Secrets/Variables 中配置，或参考 4.6 清单对接运维。

SSH 指纹不要直接照搬 `ssh-keyscan` 的全部结果：`appleboy/ssh-action` 使用 Go SSH 客户端，实际协商的是 ECDSA 主机密钥。用下面命令取得与它一致的指纹（`<host>` 换成实际地址）：

```bash
ssh-keyscan -p 22 -t ecdsa <host> 2>/dev/null \
  | ssh-keygen -lf - -E sha256
```

把输出的 `SHA256:...` 填入 GitHub Variable `DEPLOY_SSH_FINGERPRINT`。如果填成 ED25519 指纹，日志会报 `host key fingerprint mismatch`。

### 4.6 新机器接入清单

以后更换机器时，把下面这些信息发给我即可继续配置（密码只放 GitHub Secret，不要贴在代码或 README 里）：

- [ ] 服务器公网 IP 或域名
- [ ] SSH 端口、SSH 用户名
- [ ] SSH 私钥（或你希望使用的 deploy key 公钥）
- [ ] SSH host key 指纹（按 4.5 取 ECDSA 指纹）
- [ ] 部署目录（默认 `/opt/hr-contest`）
- [ ] 该用户是否已安装 Docker / Compose，是否在 `docker` 组
- [ ] 对外 HTTP 端口（默认 80），以及云厂商安全组是否已放行
- [ ] 目标机 CPU 架构（`uname -m`：`x86_64` / `aarch64`）
- [ ] MySQL 是否就在这台机器上；若是，确认 `bind-address` 与 `hr_system` 用户授权
- [ ] 无需准备 PAT：自动部署使用临时 `GITHUB_TOKEN`；只有需要手工 `docker pull` 时才考虑 `read:packages` PAT
- [ ] 可选：域名、HTTPS 终止方式（当前 Nginx 容器只监听 80，HTTPS 可在外层 LB / Caddy 终止）

### 4.7 手工重启与回滚

目标机部署目录已包含 `remote-deploy.sh`，可随时手工执行：

```bash
cd <部署目录>
bash remote-deploy.sh              # 拉取 .env 中 IMAGE_TAG 对应的镜像并重启

# 只重启当前容器，不拉新镜像
docker compose --env-file .env -f docker-compose.prod.yml restart
```

回滚到某个历史提交：

```bash
cd <部署目录>
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=sha-<完整commit SHA>/' .env
bash remote-deploy.sh
```

> 每次部署工作流都会用 GitHub Variables/Secrets 重新生成目标机 `.env`，因此**不要直接在服务器上改 `.env`**，否则下次部署会被覆盖；需要持久化的配置改 GitHub Variables/Secrets。

### 4.8 参赛演示环境部署（栈内自带数据库）

演示环境**自带 MySQL 5.7.32 容器**，与宿主机数据库完全隔离：`web + backend + mysql` 三个容器组成独立网络，数据保存在命名卷 `mysql_data`。宿主机只需提供目录、端口和域名，**不需要建库、不需要授权宿主机 MySQL**。

工作流文件：`.github/workflows/deploy-contest.yml`，仅手动触发；Compose 文件：`deploy/docker-compose.contest.yml`。

**服务器侧前置条件（一次性）**

1. 新建部署目录（如 `/opt/hr-contest`），确认该 SSH 用户可执行 `docker`。
2. 选一个未被占用的回环端口（默认 `127.0.0.1:8081`），在宿主机 Nginx 增加一个 `server_name` 反代到该端口（模板见 `deploy/host-nginx.conf.example`）。
3. 确认可访问 Docker Hub（首次需拉取 `mysql:5.7.32`）。

> ⚠️ 数据在命名卷里，**不要执行 `docker compose down -v`**，否则演示数据会被一并删除（可重新初始化）。

**GitHub 侧配置（本仓库 Settings → Secrets and variables → Actions）**

| 类型 | 名称 | 说明 |
|---|---|---|
| Variable | `DEPLOY_HOST` / `DEPLOY_USER` | 目标机地址与 SSH 用户 |
| Variable | `DEPLOY_PATH` | 默认 `/opt/hr-contest` |
| Variable | `HTTP_PORT` | 默认 `127.0.0.1:8081` |
| Variable | `DB_NAME` / `DB_USER` | 默认 `hr_contest`（栈内 MySQL 初始化时使用） |
| Variable | `CORS_ORIGINS` | 演示域名，如 `https://demo.example.com` |
| Variable | `ENABLE_API_DOCS` | 演示环境默认 `true`，方便评委查看接口文档 |
| Secret | `DEPLOY_SSH_KEY` | 目标机 SSH 私钥 |
| Secret | `DB_PASSWORD` | 栈内 MySQL 业务账号密码 |
| Secret | `DB_ROOT_PASSWORD` | 可选，栈内 MySQL root 密码；不配时回退为 `DB_PASSWORD` |
| Secret | `JWT_SECRET` | 随机长密钥（≥32 位） |

**部署步骤**

1. `Actions → Deploy contest demo → Run workflow`，`image_tag` 填 `latest`（或 `sha-<完整提交SHA>` 回滚）。
2. 工作流会拉取镜像 → 启动栈内 MySQL → 执行 `alembic upgrade head` → 启动服务。
3. 首次部署后，在目标机执行一次初始化（自动创建 admin 账号 + 500 条演示数据）：

   ```bash
   cd /opt/hr-contest
   docker compose --env-file .env -f docker-compose.contest.yml \
     exec -T backend python seed_demo.py --total 500 --days 28 \
     --admin-password '<自定义管理员密码>' --yes
   ```

4. 之后需要一键重建演示数据时，再次运行工作流并勾选 `seed_demo`（admin 账号会保留），或手工执行去掉 `--admin-password` 的同一条命令。

> 演示数据全部为脚本随机生成的虚构信息，不对应任何真实申请人；页面演示时应说明「预置演示数据」。

---

## 五、上线前必须替换的占位符

| 位置 | 占位内容 | 替换为 |
|---|---|---|
| `h5/src/views/ApplySuccess.vue` | `VITE_FB_PAGE_USERNAME`（未配置或为 `your.fb.page` 时隐藏按钮） | 在构建期环境变量 / GitHub Variables 中填入真实的 Facebook 主页用户名 |
| `backend/.env`（本地开发） | `YOUR_DB_PASSWORD`、`your-jwt-secret-here-change-in-production` | 真实数据库密码、随机长密钥 |
| `.env`（Docker 本地） | `REPLACE_WITH_REAL_PASSWORD`、`REPLACE_WITH_RANDOM_LONG_SECRET` | 真实数据库密码、`openssl rand -hex 32` |
| GitHub Secrets | `DB_PASSWORD`、`JWT_SECRET` 未配置时部署 Job 会直接失败 | 在仓库 Actions Secrets 中填写 |
| `database/seed.sql` | admin 初始密码 | 参赛演示版已随机化；自定义密码（需重新生成 bcrypt 哈希） |
| `deploy/nginx.conf.example` | `hr.example.com`、`/var/www/hr/*` | 线上域名与部署路径 |

---

## 六、目录结构
```
HR/
├── backend/                      FastAPI 后端
│   ├── app/
│   │   ├── main.py               入口：CORS + 路由挂载 + 静态文件
│   │   ├── config.py             环境变量（pydantic-settings）
│   │   ├── database.py           engine / SessionLocal / get_db
│   │   ├── models.py             8 张表 SQLAlchemy 2.0 映射
│   │   ├── schemas.py            Pydantic v2 请求/响应模型
│   │   ├── routers/              applicant / auth / contact / export / health / import_applicant / media / oss / staff
│   │   └── utils/                auth_deps / media_token / oss / phone / ratelimit / security / tz / upload_session
│   ├── alembic/                  Alembic 数据库迁移脚本（versions/）
│   ├── tests/                    pytest 单元测试（SQLite 内存库）
│   ├── ruff.toml                 Ruff 静态检查配置
│   ├── requirements.txt          依赖清单（已锁定精确版本）
│   ├── Dockerfile                后端镜像（非 root + 健康检查）
│   └── .env.example              环境变量模板（复制为 .env）
├── database/
│   ├── schema.sql                初始建库参考（增量变更由 backend/alembic 管理）
│   └── seed.sql                  初始管理员账号
├── deploy/
│   ├── nginx.conf.example        传统（非 Docker）Nginx 模板
│   ├── nginx.docker.conf         容器内 Nginx 单入口配置
│   ├── docker-compose.prod.yml   服务器部署 Compose（只拉镜像）
│   ├── remote-deploy.sh          拉镜像 + 重启 + 等待健康
│   ├── host-nginx.conf.example   宿主机已有 Nginx 时的反代模板
│   └── docker/web.Dockerfile     多阶段构建 H5 + 管理后台 + Nginx
├── .github/workflows/docker-deploy.yml  GitHub Actions 构建与 SSH 部署
├── docker-compose.yml            本地构建启动
├── .env.docker.example           Docker Compose 环境变量模板
├── h5/                           H5 自助申请端
├── admin/                        管理后台
├── 项目设计说明书.md              ★ 架构与需求全貌
├── 启动MySQL.bat
├── 启动后端.bat
├── hr-backend-api-delivery/      交付报告产物（非源码，AI 可跳过）
└── .trae-html-share-packages/    交付报告归档（非源码，AI 可跳过）
```

---

## 七、数据库表

| 表 | 用途 |
|---|---|
| `applicant` | 申请人主表（含软删除字段 `deleted_at`） |
| `staff` | 员工 / 管理员账号（bcrypt 密码） |
| `status_history` | 状态流转历史（谁在何时改成了什么状态） |
| `interview_record` | 面试记录（1/2/3 面） |
| `import_batch` | 批量导入批次统计 |
| `schema_version` | 初始建库基线版本记录 |
| `contact_log` | 申请人联系与跟进记录 |
| `candidate_source` | 候选人来源渠道记录 |
| `resume_document` | 简历附件元数据（关联申请人与存储路径） |

详细字段说明见 `database/schema.sql` 内的 `COMMENT`。

---

## 八、API 一览

| 端点 | 方法 | 鉴权 | 说明 |
|---|---|---|---|
| `/api/health` | GET | 否 | 健康检查 + 数据库连通性（数据库异常时返回 503） |
| `/api/auth/login` | POST | 否 | 员工登录，返回 JWT |
| `/api/applicant/submit` | POST | 否 | 免登录提交申请（含 IP 限流 + 手机号柔性去重 + 隐私同意义务校验） |
| `/api/applicant/check-phone` | POST | 否 | 提交前手机号预检，只返回是否存在（带 token 时顺带校验登录态，过期即 401） |
| `/api/applicant/list` | GET | 是 | 分页列表 + 多条件筛选 |
| `/api/applicant/{id}` | GET | 是 | 申请人详情 |
| `/api/applicant/{id}` | PATCH | 是 | 编辑资料（含内部备注，只更新传入字段） |
| `/api/applicant/{id}` | DELETE | admin | 软删除（写 `deleted_at`，不物理删除） |
| `/api/applicant/{id}/status` | PATCH | 是 | 状态流转（自动写 `status_history`） |
| `/api/applicant/{id}/history` | GET | 是 | 状态流转时间轴（倒序，含操作人姓名） |
| `/api/applicant/{id}/contacts` | POST | 是 | 新增申请人联系跟进记录 |
| `/api/applicant/{id}/contacts` | GET | 是 | 查询申请人联系跟进记录 |
| `/api/applicant/{id}/interviews` | POST | 是 | 新增面试记录（1~3 轮，`pass` / `fail` / `pending`） |
| `/api/applicant/{id}/interviews` | GET | 是 | 查询申请人面试记录（按轮次与时间倒序） |
| `/api/contact/follow-ups` | GET | 是 | 待跟进 / 回访列表 |
| `/api/applicant/stats/today` | GET | 是 | 今日新增 / 待处理统计（按 `Asia/Manila` 时区） |
| `/api/import/template` | GET | 是 | 下载批量导入 Excel 模板（`.xlsx`） |
| `/api/import/applicant` | POST | 是 | 批量上传 `.xlsx` 导入申请人（单文件 ≤ 10MB、≤ 2,000 行） |
| `/api/import/batches` | GET | 是 | 分页查询批量导入批次与失败明细 |
| `/api/staff/list` | GET | admin | 员工列表（普通员工不可见账号名册） |
| `/api/staff/{staff_id}` | GET | admin | 查询单个员工信息 |
| `/api/staff` | POST | admin | 创建员工 |
| `/api/staff/{id}` | PATCH | admin | 修改姓名 / 角色（含防自锁校验） |
| `/api/staff/{id}/password` | PATCH | admin | 重置密码 |
| `/api/staff/{id}/status` | PATCH | admin | 启用 / 停用（含防自锁校验） |
| `/api/oss/upload` | POST | 否 | 文件上传（本地磁盘兜底；匿名 50 次/500MB 每日，员工不限） |
| `/api/oss/session` | POST | 否 | OSS 直传会话：15 分钟 STS + 会话前缀 + 单对象 100MB（未配置 OSS 时 503） |
| `/api/media/{token}` | GET | 签名 | 短时效签名读取照片/视频（/uploads 已不再公开） |
| `/api/applicant/{id}/media-url` | GET | 是 | 为申请人照片/视频签发短时效读取地址 |
| `/api/applicant/{id}/resume` | GET | 是 | 简历下载（私有目录 + 路径校验） |
| `/api/export/applicant` | GET | admin | 导出 Excel（38 列；默认对手机号等 PII 掩码脱敏，支持 `include_pii=true` 导出明文；达上限时返回 `X-Export-Truncated` 头并在末行提示） |

完整参数与在线调试：本地 `http://localhost:8000/docs`；Docker 部署后 `http://<服务器>/docs`

---

## 九、开发约定

- 密码哈希**直接用 `bcrypt` 库，禁止 `passlib`**（Python 3.13 移除了 `crypt` 模块，passlib 会崩）
- 手机号**不做数据库 UNIQUE 约束**，由应用层柔性拦截并返回 409 提示合并
- 申请人手机号字段是去重键，但**允许重复录入后人工合并**
- `backend/app/models.py` 与 **Alembic** 迁移（`backend/alembic/versions/`）保持双向同步（因生产固定 MySQL 5.7.32，实际 DDL 以审定后的幂等 Alembic 迁移为准）；`database/schema.sql` 仅作初始建库参考
- 生产环境固定 `AUTO_MIGRATE=false`，由部署脚本在备份后通过独立一次性容器执行 `alembic upgrade head`（本地开发可按需设为 `AUTO_MIGRATE=true`）；删列/改类型/改数据必须人工确认
- 员工管理有**防自锁**保护：不能停用自己的账号，也不能把最后一个启用状态的管理员降级或停用
- 生产优先使用 Docker：`docker compose up -d --build` 或 GitHub Actions 自动部署；两套 Nginx 配置的 `client_max_body_size` 都必须 ≥ 110m（后端单文件上限 100MB）
