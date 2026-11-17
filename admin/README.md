# HR 人力池系统 · 管理后台

内部 HR / 管理员使用的 PC 端后台（Vue 3 + Vite + Element Plus）。

## 页面与路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/login` | `Login.vue` | 员工账号密码登录，签发 JWT |
| `/` | → 重定向到 `/applicant` | |
| `/applicant` | `ApplicantList.vue` | 申请人列表 + 筛选 + 详情抽屉 + 编辑 + 软删除 + 状态流转 + 导出 Excel |
| `/staff` | `StaffList.vue` | 员工管理（仅 `admin` 角色可操作） |

## 功能

- **今日统计卡片**：今日录入 / 今日新增待处理 / 申请人总数
- **多条件筛选**：状态、来源（自助/代录/推荐/批量导入）、关键词（姓名/手机号）、日期范围
- **分页表格**：ID、姓名、手机号、意向岗位、状态、来源、录入时间
- **状态标签配色**：`new` 蓝 / `contacted` 灰蓝 / `interview1-3` 黄 / `hired` 绿 / `lost` 灰 / `rejected` 红
- **详情抽屉**：全量字段分块展示，含照片与视频播放（本地开发走 `/uploads`，生产走 OSS）、隐私同意时间、状态流转时间轴（倒序，含操作人与备注）
- **编辑弹窗**：改姓名、手机号、城市、Barangay、意向岗位、申请人备注、内部备注（`PATCH` 只提交改动字段）
- **软删除**：仅 `admin` 可见的红色「删除申请人」，二次确认后写 `deleted_at`，数据库记录保留
- **状态流转弹窗**：选择目标状态 + 备注；选 `hired` 时自动展开薪资 / 雇主 / 入职日期字段；自动写入 `status_history`
- **导出 Excel**：按当前筛选条件导出 38 列数据
- **员工管理**：创建、编辑、重置密码、启用/停用（不能停用当前登录账号，不能动最后一个 admin）
- **路由守卫**：未登录跳登录页；已登录访问登录页自动跳列表

## 启动

```bash
npm install
npm run dev          # http://localhost:5174/login
```

初始账号：**`admin`**（演示版密码随机生成，由参赛者单独保管）

**后端必须同时运行在 `http://localhost:8000`** —— `vite.config.js` 已把 `/api` 代理过去。

## 目录

```
admin/
├── index.html
├── vite.config.js            含 /api 代理配置
├── public/favicon.svg
└── src/
    ├── main.js               路由定义 + 路由守卫
    ├── App.vue
    ├── style.css
    ├── api/http.js           axios 实例 + 拦截器
    └── views/
        ├── Login.vue         登录页
        ├── ApplicantList.vue 申请人列表（详情抽屉 / 编辑 / 软删除 / 状态流转）
        └── StaffList.vue     员工管理
```

## 技术说明

- 登录态存 `localStorage`（`token` + `staff` 信息）
- `api/http.js` 的 axios 拦截器自动附带 `Authorization: Bearer <token>`，收到 401 自动清登录态并跳登录页
- 员工角色分为 `admin`（可管理员工）和 `staff`（仅业务操作），后端按角色校验

## 上线前必改

初始账号 `admin` 必须在登录后立即修改密码。
