# HR 人力池系统 · 手工黑盒冒烟脚本

本目录包含发布前手工黑盒冒烟脚本 [`Invoke-HrSmoke.ps1`](Invoke-HrSmoke.ps1)，用于对已启动的 Docker Compose / Nginx + FastAPI 全栈实例执行 60+ 项端到端 HTTP 断言。

> **定位说明（见 `AGENTS.md`）**：本脚本为**发布前手工回归质量门**，**不整体移植进 CI**（CI 自动化质量门由 `backend/tests/` 下的 `pytest -q` 与前端构建承担）。

---

## 环境要求

- **Windows PowerShell 5.1** 或 **PowerShell 7+**（脚本采用纯 ASCII 与 `.NET` 内置 `HttpClient` / `ZipArchive`，无需安装任何第三方 PowerShell 模块）
- 目标环境已通过 Docker Compose 或 Nginx + FastAPI 启动，且初始管理员账号可用

---

## 使用示例

推荐通过环境变量传入管理员密码，避免密码留在命令行历史中：

```powershell
$env:HR_SMOKE_ADMIN_PASSWORD = "your-admin-password"
.\scripts\manual-smoke\Invoke-HrSmoke.ps1 -BaseUrl "http://localhost"
```

跳过匿名提交限流压测（例如在同一 IP 下短时间内连续重跑冒烟时）：

```powershell
.\scripts\manual-smoke\Invoke-HrSmoke.ps1 `
  -BaseUrl "http://localhost" `
  -AdminUsername "admin" `
  -SkipRateLimit
```

显式传参方式：

```powershell
.\scripts\manual-smoke\Invoke-HrSmoke.ps1 `
  -BaseUrl "http://127.0.0.1:8080" `
  -AdminUsername "admin" `
  -AdminPassword "your-admin-password" `
  -TimeoutSec 30
```

---

## 参数说明

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-BaseUrl` | `"http://localhost"` | 目标站点根地址（Nginx 入口），末尾 `/` 会自动裁剪 |
| `-AdminUsername` | `"admin"` | 管理员登录用户名 |
| `-AdminPassword` | `$env:HR_SMOKE_ADMIN_PASSWORD` | 管理员密码；为空时脚本直接报错退出，**无任何硬编码兜底密码** |
| `-SkipRateLimit` | `$false` | 跳过末尾的匿名 `POST /api/applicant/submit` 429 限流触发测试 |
| `-TimeoutSec` | `30` | 单次 HTTP 请求超时时间（秒） |

---

## 覆盖的断言分组（64+ 项）

1. **健康检查与 Nginx 路由**：`/healthz`、`X-Content-Type-Options: nosniff`、`/api/health`、H5 `/` 与 `/apply`、Admin `/admin/`、HTML 引用的 `/assets/*` 与 `/admin/assets/*` 静态资源。
2. **安全加固 404 路由**：`/docs`、`/redoc`、`/openapi.json`、`/learning`、`/uploads/test.jpg` 均返回 `404`。
3. **认证与员工 RBAC**：错误密码 `401`、管理员登录签发 JWT、短密码 `<8` 位 `422`、创建临时员工、普通员工访问 `/api/staff/list` 与 `/api/export/applicant` 返回 `403`、管理员防自锁（自停用 `400`、最后一名启用管理员自降级 `400`）。
4. **文件上传与签名媒体**：拒绝 `.exe`/`.html`（`415`）、上传 1×1 PNG（`POST /api/oss/upload` 返回 `local/` key）、伪造 `/api/media/bad-token` 返回 `404`。
5. **公开 H5 流程**：`/api/applicant/check-phone`、缺少 `privacy_agreed`（`422`）、`gender="other"`（`422`）、`gender=null` 合规提交（`200`）、重复手机号柔性去重（`409`）、员工 JWT 代录（`source_type="staff"`）。
6. **签名媒体读取**：`/api/applicant/{id}/media-url` 签发短时效 URL 并成功读取 `200 image/png`。
7. **候选人工作流与三轮面试**：`/api/applicant/list` 多条件筛选（含 `gender=unspecified`）、`/api/applicant/stats/today`、详情、全字段 `PATCH` 与显式 `null` 清空、状态流转与 `/history`、`/contacts` 与 `/api/contact/follow-ups`、`POST/GET /api/applicant/{id}/interviews`（非法轮次 `422` + Round 1 `pass` `200`）。
8. **批量 Excel 导入**：`/api/import/template`（`200 .xlsx`）、非 `.xlsx` 拒绝（`400`）、内存构造 `.xlsx`（含 1 条合法空性别行 + 1 条 `gender="other"` 失败行）上传 `/api/import/applicant` 验证 `success_count=1` / `fail_count=1`、`/api/import/batches` 查询批次。
9. **Excel 导出**：`/api/export/applicant` 默认脱敏与 `X-Export-Truncated` / `X-Export-Max-Rows` 响应头、`include_pii=true` 管理员 `200` vs 普通员工 `403`。
10. **停用与软删除清理**：停用临时员工并验证登录被拒（`403`）、`DELETE /api/applicant/{id}` 软删除测试数据并验证删除后 `GET` 返回 `404`。
11. **匿名限流（可选）**：未传 `-SkipRateLimit` 时触发匿名 `POST /api/applicant/submit` 返回 `429`。

> **退出码**：全部通过返回 `0`；任意断言失败返回非零退出码 `1`。
