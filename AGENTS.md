# HR 人力池系统 · 项目规则（AI 与协作者必读）

## 项目是什么

菲律宾马尼拉扫楼招聘场景的申请人管理系统，三端一体：H5 自助申请端、管理后台、FastAPI 后端。
业务规模 1,000~2,000 人/月、≤30,000 人/年，**单机单体架构足够**。不要引入微服务、消息队列、分库分表、Redis 集群等超出规模的设计。

## 技术栈（已定型，不得更换）

| 目录 | 技术 | 端口 |
|---|---|---|
| `h5/` | Vue 3 + Vite + Vant，`base=/` | 5173 |
| `admin/` | Vue 3 + Vite + Element Plus，`base=/admin/` | 5174 |
| `backend/` | FastAPI + SQLAlchemy 2.0 + Pydantic v2 + PyJWT + bcrypt | 8000 |
| 数据库 | MySQL（开发机 8.4.9，**生产固定 5.7.32 且不升级**） | 3306 |
| 部署 | Docker Compose + Nginx 单入口 + GitHub Actions → GHCR → SSH | — |
| 文件存储 | 阿里云 OSS；未配置时自动降级到本地 `backend/app/uploads/` | — |
| 前端运行时 | Node **22 LTS**（CI 固定 22；本地更高版本可用，但不作为基线） | — |

## 命令

后端（仓库根目录执行）：

```bash
python -m venv backend/venv
backend/venv/bin/python -m pip install -r backend/requirements.txt   # Windows: backend\venv\Scripts\python
cd backend && python -m uvicorn app.main:app --reload --proxy-headers --forwarded-allow-ips 127.0.0.1
```

前端（Windows PowerShell 下请统一使用 `npm.cmd`，避免 `npm.ps1` 受执行策略拦截）：

```bash
cd h5 && npm.cmd ci && npm.cmd run dev        # http://localhost:5173/apply
cd admin && npm.cmd ci && npm.cmd run dev     # http://localhost:5174/login
```

全栈容器：

```bash
docker compose up -d --build
docker compose ps && docker compose logs -f backend
```

测试：

```bash
cd backend && python -m pytest -q
```

> **Swarm `share` 独立工作区（Git Worktree）执行提示**：`share` 隔离副本不包含被 `.gitignore` 忽略的 `backend/venv/` 与 `node_modules/`。在 Worktree 内执行后端测试或静态检查时，直接调用主工作区解释器即可：`D:\SourceCode\HR\backend\venv\Scripts\python.exe -m pytest -q` 与 `D:\SourceCode\HR\backend\venv\Scripts\python.exe -m ruff check --config ruff.toml .`（`tests/conftest.py` 基于 `Path(__file__)` 动态挂载当前 Worktree 源码，不会串回主工作区）。

- **定义**：`backend/tests/` 下覆盖「提交、导入、导出、权限」四条关键路径的 P0 用例，CI 必须全绿。
- **现状（已建立）**：提交、导入、导出、权限四条路径的 P0 用例已全部入库（`backend/tests/`），并接入 CI：PR 与 push 均执行 `pytest -q`，test 失败则 deploy 不执行。

## 代码质量工具

- 后端 **ruff** 统一以 `backend/ruff.toml` 为准（启用规则集 `E`、`F`、`I`，忽略历史长注释 `E501`，固定 `app` 为 first-party、`alembic` 为 third-party，消除跨目录执行时的 `I001` 排序翻转）；全量 `backend/` 必须保持零告警，命令：`D:\SourceCode\HR\backend\venv\Scripts\python.exe -m ruff check --config backend/ruff.toml backend/app backend/alembic backend/tests`。
- **mypy：本期不启用**。

## 目录约定

- `backend/app/`：`main.py` 挂载路由，`models.py` 表映射，`schemas.py` 请求/响应模型，`routers/` 按资源划分，`utils/` 纯工具。
- `backend/app/models.py` 与 `backend/alembic/versions/` 必须保持**双向结构同步**（列、类型、可空性、索引一致）；因生产固定 MySQL 5.7.32，实际 DDL 以人工审定且幂等的 Alembic 迁移为准。
- `database/schema.sql`：初始建库参考与历史快照，不再作为增量变更的执行入口。
- `deploy/`：所有 Nginx / Compose / 部署脚本模板，禁止在服务器上直接改。
- 以下目录是**交付报告产物、监理日志或过程草稿，不是源码，除非用户明确指定，否则 AI 一律跳过**：`hr-backend-api-delivery/`、`.trae-html-share-packages/`、`.agent/`、`docs/handoffs/`、`docs/superpowers/`、`docs/agent-supervision/`、`docs/learning/`、`docs/reports/`、`docs/talent-pool/`。

## 硬约束（违反即视为不合格）

1. **MySQL 5.7.32 兼容（最高优先级）**
   - 禁止使用：`WITH`/CTE、窗口函数、`utf8mb4_0900_*` 排序规则、`CREATE INDEX ... DESC`、`ALTER TABLE ... RENAME COLUMN`、依赖 `CHECK` 约束生效、`JSON_TABLE`、`VALUES ROW()`。
   - 排序规则统一 `utf8mb4_unicode_ci`，引擎 `InnoDB`。
   - 生产开启 `ONLY_FULL_GROUP_BY`：所有 `GROUP BY` 必须列全字段。
   - 新增或修改 SQL 必须在 **MySQL 5.7.32** 上验证，不能只在 8.4 上跑通就交付。
2. **表结构 `backend/app/models.py` 与 Alembic 迁移（`backend/alembic/versions/`）双向同步**。
   - **生产环境固定 `AUTO_MIGRATE=false`**，迁移作为部署脚本独立前置步骤执行（数据库备份 → 一次性容器执行 `alembic upgrade head` → 启动服务），防止镜像回滚时因旧镜像不认识新 revision 而启动死锁。
   - `AUTO_MIGRATE=true` 仅限本地开发按需开启，由 `GET_LOCK` 防并发，迁移失败必须中止启动。
   - 自动迁移仅限加表、加列、加索引等兼容性变更；删列、改类型、改数据必须人工确认。
   - 迁移优先使用独立的 `MIGRATE_DATABASE_URL`（生产 `hr_migrate` 账号仅授 DDL 权限，未配置时回退主连接串并记录告警）；应用运行账号保持最小权限。
   - 禁止未经人工复核直接执行 autogenerate；历史编号 SQL（`database/migrations/001-007`）保留为基线，不再手工执行。
3. 密码哈希只用 `bcrypt`，**禁止 `passlib`**（Python 3.13 已移除 `crypt` 模块）。
4. 手机号**不做数据库 UNIQUE 约束**，由应用层柔性去重并返回 409。
5. 员工管理必须保留防自锁：不能停用自己，不能把最后一个启用状态的管理员降级或停用。
6. 上传上限前后端统一 100MB；两套 Nginx 的 `client_max_body_size` 必须 ≥ `110m`。
7. admin 构建 `base=/admin/`，静态资源必须能在 `/admin/assets/` 下访问。
8. 不新增第三方依赖，除非 PR 描述写明理由、体积与替代方案；`alembic`（数据库迁移）与 `oss2`（OSS 私有桶预签名 URL）已批准。
9. **导出隐私与截断治理**：`/api/export/applicant` 已实现默认对敏感 PII（手机号、证件号等）做掩码脱敏（仅限显式传入 `include_pii=true` 时导出明文），记录导出审计日志（操作人、筛选条件、行数），并在达到 `EXPORT_MAX_ROWS` 上限时通过 `X-Export-Truncated` 响应头与 Excel 末行提示显式告知“结果已截断”，禁止静默截断。
10. **`gender` 允许为空是刻意设计**，不是数据缺陷：不设 "Other" 或任何非二元选项，既避免引发争议，也允许不愿表态的申请人留空。
    - **禁止**把 `gender` 改为必填；**禁止**新增 Other / 非二元选项；批量导入路径同样允许为空。
    - 报表与统计中，`gender IS NULL` 显示为"未填写"，单列统计，不并入性别比例的分母。

## 质量门（每个 PR 必须全绿）

- 后端 `pytest -q` 全绿（覆盖提交/导入/导出/权限路径）。
- 后端 `ruff check --config backend/ruff.toml backend/app backend/alembic backend/tests` 零告警。
- 前端 `h5` 与 `admin` 执行 `npm.cmd run build` 零报错。
- 涉及表结构或 SQL 变更时，必须提供幂等 Alembic 迁移，并在隔离的 MySQL 5.7.32 容器上通过空库 `alembic upgrade head` 与关键 SQL 冒烟。
- Swarm 模式下必须经独立只读 `verifier` 对照本文件硬约束审查 diff 通过后方可合并；涉及前端交互变动优先配合 `browser` 子代理或自动化冒烟实测。
- 手工回归：58+ 项 PowerShell 手工断言脚本归入 `scripts/manual-smoke/`，作为发布前手工冒烟，**不整体移植进 CI**；`docs/reports/测试报告-2026-10-24-Docker.md` 中受影响部分的断言必须复验。

## 交付约定（AI Swarm 高效模式）

- **单 Worker 限高与严格文件隔离**：单个 Swarm Worker 子任务改动建议控制在 200~500 行内；每个写代码的 Worker 必须在 Brief 中明确划定「负责文件清单」与「禁止触碰范围」，严禁两个 Worker 同时编辑同一文件。
- **按功能/波次合并 + 强门禁放行**：取消“单 PR 死卡 300 行”与人工逐行读代码前提，允许按完整业务功能或同一治理波次合并为一个 PR（建议 ≤ 800~1000 行，确保故障时可独立 `git revert`），放行唯一标准是「自动化质量门全绿 + 独立只读 `verifier` 验收通过」。
- **分支命名**：`feat/<slug>`、`fix/<slug>`、`chore/<slug>`（关联 Issue 时可用 `feat/<issue号>-<slug>`，禁止编造虚构 Issue 号）。
- **PR / 合并说明**：必须包含改了什么、为什么、执行的验证命令及输出摘要、涉及的表与接口。
- **安全红线**：**禁止直接操作生产机或生产数据库**（部署只走 GitHub Actions）；禁止把 `.env`、`config.json`、Cookie、AK/SK 或真实申请人 PII 写入代码、Docker 镜像、日志或 PR 描述；**严禁将 `docs/`（含 `docs/learning/`）下任何内部学习笔记、架构复盘或过程文档打包进 Docker 镜像、挂载 Nginx 路由或同步至生产服务器**。

## 云端运行环境

- 语言版本：Node 22 LTS、Python 3.12。
- 安装脚本：`pip install -r backend/requirements.txt && (cd h5 && npm ci) && (cd admin && npm ci)`。
- **常规单元测试（`pytest`）**：强制使用 **SQLite 内存库 + 每用例事务回滚**（`backend/tests/conftest.py` 保留 `_assert_not_production` 守门，严禁 `pytest` 连接任何 MySQL 或读取任何 `.env`）。
- **MySQL 5.7 方言与迁移冒烟**：在 CI 独立 Job（`mysql:5.7.32` service container）或独立冒烟脚本中运行，仅允许通过环境变量连接临时隔离的空测试库验证 `alembic upgrade head` 与方言兼容性，**严禁连接生产库或共享开发库**。
