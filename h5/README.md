# HR 人力池系统 · H5 自助申请端

面向菲律宾求职者的**免登录**手机申请表单（Vue 3 + Vite + Vant）。

## 功能

| 模块 | 说明 |
|---|---|
| 隐私同意 | 菲律宾《数据隐私法》(RA 10173) 合规声明，必须勾选才能提交；服务端记录 `privacy_agreed_at` |
| 基本信息 | 菲律宾三段式姓名（First / Middle / Last）、性别、出生日期、婚姻状况 |
| 联系方式 | 主手机号（必填）、备用手机号、现居城市、Barangay |
| 社交账号 | Facebook 主页链接、TikTok `@用户名`（**全部选填**） |
| 证件 | 证件1（类型 + 号码，**选填**）、NBI 无犯罪证明 |
| 求职意向 | 意向岗位、期望月薪、可到岗时间 |
| 技能经验 | 学历、最近工作、工作经验 |
| 拍照 | 不锁定摄像头（可选拍照或相册），长边压到 1280 的 JPEG 再上传，解码失败时回退原图（后端限 100MB） |
| 录像 | 自述视频，读取 `loadedmetadata` 校验真实时长 ≤ 40 秒；上传前在设备端用 canvas + MediaRecorder 压到 1080p / 4Mbps（约 20MB），压缩失败或浏览器不支持时回退原片直传 |
| 自由备注 | 长文本，可粘贴整份文字简历 |
| 提交成功页 | 含「Contact Recruiter on Messenger」按钮，跳转 `m.me/<FB主页>` |
| 推广码 | `?ref=XXX` 写入来源（同时存 `sessionStorage`，刷新不丢），服务端记为 `referral` |
| 员工代录 | `/staff/login` 登录后同一张表单提交，服务端记为 `staff` 并绑定员工；token 过期（401）时**就地弹窗重登并自动重提**，表单与已拍媒体不丢 |
| 手机号预检 | 提交前调用 `/api/applicant/check-phone`，重复号码提前拦截 |

> 数据模型里还有邮箱、家乡省份、证件 2/3、工作类型、可接受地点、住家意愿、英语/中文水平等字段，已在后端 schema 与后台详情中支持，**H5 第一期暂未开放**，后续按需加到表单即可。

## 启动

```bash
npm install
npm run dev          # http://localhost:5173/apply
```

**后端必须同时运行在 `http://localhost:8000`** —— `vite.config.js` 已把 `/api` 代理过去。

## 目录

```
h5/
├── index.html
├── vite.config.js            含 /api 代理配置
├── public/favicon.svg
└── src/
    ├── main.js               路由：/apply、/apply/success、/staff/login
    ├── App.vue
    ├── style.css
    ├── auth.js               员工 token 读写（localStorage）
    └── views/
        ├── ApplyForm.vue     申请表单主页面（自助 + 代录共用）
        ├── ApplySuccess.vue  提交成功页
        └── StaffLogin.vue    员工登录页（扫楼代录用）
```

## 两种使用模式

| 模式 | 入口 | 来源记录 |
|---|---|---|
| 求职者自助 | `/apply` | `self`；带 `?ref=推广码` 时记为 `referral` |
| 员工扫楼代录 | 先 `/staff/login` 登录，再在 `/apply` 填表 | `staff`，`source_ref` = 员工账号，`created_by` = 员工 ID |

代录模式下前端自动带上 `Authorization: Bearer <token>`；后端以 token 为准判定来源，客户端传 `source_type` 会被忽略。

## 媒体上传

- **配了 OSS**（`backend/.env` 填 `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` / `OSS_ROLE_ARN` / `OSS_BUCKET` / `OSS_ENDPOINT`）：先 `POST /api/oss/session` 取 15 分钟临时凭证与会话前缀，浏览器用 `ali-oss` 直传 `hr/<会话前缀>/<随机>.<ext>`，照片视频不经过后端。
- **没配 OSS**（`/api/oss/session` 返回 503）：自动退回 `POST /api/oss/upload` 本地上传，仅开发环境使用。
- 上传配额：匿名每 IP 50 次 / 500MB / 天；已登录员工（扫楼代录）不限次数；单文件上限 100MB。
- `ali-oss` 用动态 import，只有真正选择照片/视频时才下载（约 680KB），不传媒体不加载。

生产环境需在 OSS 控制台给 Bucket 配 CORS：来源填 H5 域名，允许方法 `PUT`，允许头 `*`，暴露头 `ETag`。

## 上线前必改

`src/views/ApplySuccess.vue` 中的 `m.me/your.fb.page` —— 替换为你们真实的 Facebook 主页用户名。

> 设计意图：让申请人主动点进 Messenger 会话，这样**主动权反转**，变成她来找你们，成本极低、收益极高。

## 后期打包 Android APK

纯增量方案，**无需重写任何代码**：

```bash
npm install @capacitor/core @capacitor/cli
npx cap init
npx cap add android
```

需本机安装 Android Studio。
