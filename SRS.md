# 校园失物检索平台 — 软件需求规格说明书 (SRS)

> 版本：v3.5.0 | 日期：2026-09-14 | 基于 v3.3 源码 + v3.4.x 加固 + v3.5.0 中文化模型与跨模态检索，逐项与代码对齐

---

## 目录

1. [引言](#1-引言)
2. [用户角色定义](#2-用户角色定义)
3. [功能性需求](#3-功能性需求)
4. [非功能性需求](#4-非功能性需求)
5. [接口需求](#5-接口需求)
6. [数据需求](#6-数据需求)
7. [前端页面需求](#7-前端页面需求)
8. [核心算法说明](#8-核心算法说明)
9. [约束与假设](#9-约束与假设)

---

## 1. 引言

### 1.1 项目概述

本系统是一个面向高校校园的智能化失物招领平台，核心能力包括：

- 用户注册与登录（JWT 鉴权，7 天有效期）
- 失物/拾物信息发布与管理（含图片上传）
- 基于 **Chinese-CLIP ViT-H-14**（默认，中文图文跨模态）多模态模型的图文特征提取与智能匹配；`open_clip ViT-B-32` 为可回滚后端
- 管理员审核机制（通过/驳回 + 双向邮件通知）
- 站内消息与 QQ 邮箱 HTML 邮件通知
- 物品认领/归还自标记流程（发布者标记"已找回/已认领"）
- 数据统计看板（展示中/今日失物/今日拾物/总计找回 + 分类占比）
- 深色/浅色主题切换

### 1.2 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.115+ |
| 前端框架 | Vue 3 (Composition API) | 3.5+ |
| UI 组件库 | Element Plus | 2.14 |
| 状态管理 | Pinia | — |
| 路由 | Vue Router | 5 |
| 构建工具 | Vite (Rolldown) | 8 |
| 数据库 | SQLite | 3 |
| AI 模型 | Chinese-CLIP ViT-H-14（默认）/ OpenCLIP ViT-B-32（回滚，`CLIP_BACKEND` 可切） | OFA-Sys `cn_clip` / `laion2b_s34b_b79k` |
| 认证 | JWT HS256 + bcrypt | — |
| 邮件 | SMTP (QQ 邮箱) | SSL 465 |

### 1.3 术语表

| 术语 | 定义 |
|------|------|
| CLIP | Contrastive Language-Image Pre-Training，图文跨模态预训练模型 |
| 余弦相似度 | 两个 L2 归一化向量的内积，用于衡量图文/颜色匹配程度（`cn_clip` ViT-H-14 为 **1024 维**联合投影 / `open_clip` ViT-B-32 为 **512 维**；颜色为 27 维） |
| JWT | JSON Web Token，HS256 签名，7 天过期 |
| 站内消息 | 系统内用户接收的通知，存储于 notifications 表 |
| 软删除 | 将记录标记为已删除但保留数据；用户注销后关闭物品、改用户名并将 `status` 置为 `deleted` |
| role / status | 账号「角色」（user/admin）与「账号状态」（active/disabled/deleted）两个正交维度 |

---

## 2. 用户角色定义

> ⚠️ **v3.4.0 变更（C2 账户状态语义拆分）**：账号「角色」与「状态」两个维度解耦。`users.role` 收敛为 `user` / `admin` 两种；「禁用」「注销」不再是角色，而是 `users.status` 的取值（`active` / `disabled` / `deleted`）。

### 2.1 角色（role）

| 角色 | 数据库标识 | 权限范围 |
|------|-----------|---------|
| **普通用户** | `role='user'` | 浏览物品列表/详情；发布/编辑/删除自己的物品；使用智能匹配；申请认领/归还；标记自己物品"已找回/已认领"；查看通知；个人中心（含历史记录） |
| **管理员** | `role='admin'` | 审核所有物品（通过/驳回 + 批量通过）；用户管理（设管理员/撤销管理/禁用/启用/逻辑删除）；编辑/删除任何物品；发布公告；拥有普通用户全部权限 |

### 2.2 账号状态（status）

| 状态 | 数据库标识 | 行为 |
|------|-----------|------|
| **正常** | `status='active'` | 可正常登录与访问 |
| **已禁用** | `status='disabled'` | 由管理员封禁；登录时返回 403 "账号已被禁用，请联系管理员"；已签发 JWT 访问受保护接口时返回 403；访问公开接口时降级为匿名 |
| **已注销** | `status='deleted'` | 用户自助注销；登录时返回 403 "账号已注销"；访问公开接口时降级为匿名；JWT 有效期过后完全失效 |

> ⚠️ **v3.3 变更**：去除「访客」角色。所有功能页面均需注册登录后方可访问。未登录用户仅可见登录页和注册页。

### 路由守卫逻辑

```
router.beforeEach:
  status === 'disabled' 用户 → 清除登录态 → /login
  requiresAuth + 未登录 → /login
  requiresGuest + 已登录 → /items (user) 或 /admin (admin)
  requiresAdmin + 非Admin → /items
router.afterEach:
  已登录 + status !== 'disabled' → 刷新未读消息数量
```

> ⚠️ **v3.4.0（C2）**：守卫判定字段由 `user.role === 'disabled'` 改为 `user.status === 'disabled'`（见 `lost-found-frontend/src/router/index.js`）。

---

## 3. 功能性需求

### 3.1 用户认证模块 (FR-AUTH)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-AUTH-01 | 用户注册 | `POST /api/register` — username(2-20字符)、password(6-30字符)、phone(必填,11位)、email(选填)。bcrypt 哈希存储。返回 JWT token + user 对象（含 `status='active'`） |
| FR-AUTH-02 | 用户登录 | `POST /api/login` — username + password。验证 bcrypt 哈希。`status='disabled'` 返回 403 "账号已被禁用，请联系管理员"；`status='deleted'` 返回 403 "账号已注销"。返回 JWT token(7天) + user(id/username/role/status) |
| FR-AUTH-02b | 禁用/注销拦截 | 登录时 `status='disabled'`（或 `deleted`）返回 403；已登录禁用用户在路由守卫中被清除登录态并跳转 /login；受保护接口由 `get_current_user` 统一校验 `status` |
| FR-AUTH-03 | 自动登录 | localStorage 持久化 token + user。`authStore.restore()` 在路由守卫中恢复。请求拦截器自动附加 `Authorization: Bearer` |
| FR-AUTH-04 | 获取用户信息 | `GET /api/me` — 返回 id/username/role/status/phone/email/created_at（v3.3 移除 avatar_path） |
| FR-AUTH-05 | 更新个人资料 | `PUT /api/me` — 支持更新 password(bcrypt重新哈希)/email/phone/username(唯一性校验)。密码变更后强制重新登录。**头像上传已移除** |
| FR-AUTH-06 | 注销账号 | `DELETE /api/me` — 软删除：关闭所有活跃物品，用户名标记 `_deleted_{id}`，`status` 置为 `deleted` |
| FR-AUTH-07 | 退出登录 | 前端清除 token 和 user，跳转 /login |
| FR-AUTH-08 | 登录后自动跳转 | admin → `/admin`，user → `/items` |
| FR-AUTH-09 | 获取历史记录 | `GET /api/me/history` — 返回用户所有物品(不限状态) + 认领记录 |

### 3.2 物品管理模块 (FR-ITEM)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-ITEM-01 | 发布物品 | `POST /api/items/` — FormData: type(lost/found)、title(2-50字符)、description(≤500字)、category、contact、location、image(≤16MB)。自动提取 CLIP 图像+文本特征（维度随后端：`cn_clip` 1024 / `open_clip` 512），并计算 27维颜色直方图（`color_vector`）。初始状态 review_status=pending, status=pending |
| FR-ITEM-02 | 物品列表（分页+筛选） | `GET /api/items/` — 参数: type/category/keyword/user_id/limit/offset。管理员看全部；普通用户看 (approved+active) OR 自己物品；匿名仅看已审核+活跃物品 |
| FR-ITEM-03 | 分类筛选 | 全部/失物/拾物/仅我的 |
| FR-ITEM-04 | 类别筛选 | 7 类别：电子产品/证件卡片/包袋箱包/书籍文具/服装配饰/钥匙门禁/其他 |
| FR-ITEM-05 | 关键词搜索 | title 或 description LIKE 模糊匹配 |
| FR-ITEM-06 | 物品详情 | `GET /api/items/{id}` — 公开访问，未审核物品仅限发布者/管理员可见。返回全部字段（不含向量） |
| FR-ITEM-07 | 编辑物品 | `PUT /api/items/{id}` — 仅本人/管理员。支持更换图片（自动删旧图+重提取特征+重算 `color_vector`）。非管理员编辑后 review_status 重置为 pending |
| FR-ITEM-08 | 删除物品 | `DELETE /api/items/{id}` — 仅本人/管理员。同时删除图片文件 |
| FR-ITEM-09 | 图片访问 | `GET /api/items/uploads/{filename}` — 公开，路径遍历防护 |

### 3.3 智能匹配模块 (FR-MATCH)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-MATCH-01 | 以图搜图 | `POST /api/items/match` — 上传 temp 图片 → CLIP 图像特征 → 计算与目标物品余弦相似度 |
| FR-MATCH-02 | 以文搜图（**真跨模态**） | 输入文字 → CLIP 文本特征 → 与目标**图片**特征计算跨模态相似度（`sim_cross_t2i = q_text · t_img`，而非仅比文本自相似） |
| FR-MATCH-03 | 图文混合匹配 | 同时提供图片+文字，四通道加权融合相似度 |
| FR-MATCH-04 | 加权相似度算法（四通道跨模态 + 五阶段） | 基础四通道：图-图 0.35 + **跨模态 0.35** + 文-文 0.15 + 色 0.15（缺失通道时动态权重归一化）；跨模态内 `q_text·t_img` 与 `q_img·t_text` 各 0.5；叠加类别/位置调节、时间衰减、分层阈值与**阶段5 跨模态一致性惩罚** |
| FR-MATCH-05 | 结果排序 | 按相似度降序返回 Top 20，仅匹配 active + approved 物品 |
| FR-MATCH-06 | 分层阈值 | 手动匹配 0.35 / 自动推送 0.55 / 邮件通知 0.70（**v3.5.0 初值，待标定**） |
| FR-MATCH-07 | 临时图片上传 | `POST /api/items/temp-upload` — 上传后返回文件名，匹配后自动删除 |
| FR-MATCH-08 | 匹配来源标注 | 结果项含 `match_source`（∈ `text` / `image` / `mixed`）；响应顶层含 `legend: {high, mid}`（由 `MATCH_THRESHOLD_AUTO` / `_MANUAL` 派生） |

### 3.4 管理员审核模块 (FR-ADMIN)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-ADMIN-01 | 待审核列表（分页） | `GET /api/admin/reviews?page=&size=` — 返回 review_status=pending 的物品 |
| FR-ADMIN-02 | 审核通过 | `PUT /api/admin/reviews/{id}` action=approved → status=active, review_status=approved。BackgroundTasks 异步触发自动匹配 |
| FR-ADMIN-03 | 审核驳回 | action=rejected → status=rejected, review_status=rejected。发送站内通知（含驳回理由）+ HTML 邮件（含重新编辑链接） |
| FR-ADMIN-04 | 自动匹配推送 | 审核通过后异步匹配异类物品（失物↔拾物），**维度预检**通过后逐对打分，相似度≥0.55（`MATCH_THRESHOLD_AUTO`，初值）双向推送通知+邮件 |
| FR-ADMIN-05 | 批量审核通过 | `POST /api/admin/reviews/batch-approve` — 多选物品 → 一键批量通过（最多 50 条/次）。驳回不支持批量（需逐一填写理由+站内通知） |
| FR-ADMIN-06 | 防止重复审核 | SQL `WHERE review_status='pending'` 条件更新 + rowcount 检查（单条+批量均适用） |
| FR-ADMIN-07 | 用户管理 | `GET /api/admin/users` — 用户列表（分页）；支持逻辑删除用户（`status` → `deleted`） |
| FR-ADMIN-08 | 用户角色/状态变更 | `PUT /api/admin/users/{id}` — 设角色（user/admin）/ 切换账号状态（active↔disabled）。**v3.4.0：禁用/启用只改 `status` 并保留 `role`** |

> ⚠️ **v3.4.0（C2 / O2）**：`toggle_status`（禁用/启用）仅翻转 `status`，不再改动 `role`；管理员**不能禁用/删除自己的账号**（`toggle_status`、`delete_user` 针对 target==current 时返回 400 "不能修改自己的账号状态"/"不能删除自己的账号"）。允许管理员禁用/删除**其他**管理员账号。

### 3.5 消息通知模块 (FR-NOTIFY)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-NOTIFY-01 | 站内消息 | 匹配成功、认领申请、审核结果时自动生成通知 |
| FR-NOTIFY-02 | 未读消息数量 | `GET /api/notifications/unread/count` — 导航栏铃铛红点+数字 |
| FR-NOTIFY-03 | 消息列表 | `GET /api/notifications/unread` — 分页返回未读通知（标题/内容/链接/时间） |
| FR-NOTIFY-04 | 标记单条已读 | `PUT /api/notifications/{id}/read` — 验证所有权（user_id） |
| FR-NOTIFY-05 | 一键全部已读 | `PUT /api/notifications/read-all` — 批量更新 |
| FR-NOTIFY-06 | 邮件通知 | 匹配成功/审核结果/认领申请时发送 HTML 邮件（QQ SMTP），经 `BackgroundTasks` 异步投递 |
| FR-NOTIFY-07 | 轮询更新 | 每次路由切换 + 每 30 秒定时 `fetchUnreadCount()` |

### 3.6 物品认领/归还模块 (FR-CLAIM)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-CLAIM-01 | 申请认领/归还 | `POST /api/items/{id}/claim` — lost物品→"我要归还"(我捡到了)，found物品→"我要认领"(我丢失了)。通知 + 邮件中含申请人手机号（从用户账户获取） |
| FR-CLAIM-02 | 防重复申请 | 同物品+同用户已有未读申请通知时拒绝，返回 400 "已发送申请，请等待回复" |
| FR-CLAIM-03 | 发布者自标记 | `PUT /api/items/{id}/mark-claimed` — 发布者对自己的物品点击"已找回"(lost)/"已认领"(found)→ status 变为 claimed。物品从列表消失，转至个人中心历史记录 |
| FR-CLAIM-04 | 总计找回计数 | 每次标记 claimed 后，总计找回数自动 +1（持久化计数器） |
| FR-CLAIM-05 | 已认领物品展示 | claimed 物品在详情页显示"该物品已找回"状态标签，隐藏所有操作按钮 |
| FR-CLAIM-06 | 历史记录查看 | `GET /api/me/history` — 个人中心查看自己发布的所有物品（含已认领/已驳回/已关闭）+ 认领记录 |

> ⚠️ **v3.3 变更**：删除原有的"确认/拒绝"两步流程（`PUT /api/items/{id}/claim/confirm`），改为发布者自行标记。线下联系通过通知中附带的手机号进行。

### 3.7 数据统计模块 (FR-STATS)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-STATS-01 | 首页看板 | `GET /api/stats/dashboard` — 展示中物品总数/今日失物/今日拾物/总计找回数量 + 分类占比 `categories` |
| FR-STATS-02 | 统计卡片 + 饼图 | 首页 4 卡片（展示中/今日失物/今日拾物/总计找回）+ 分类占比饼图，彩色数字，响应式 2×2 网格 |
| FR-STATS-03 | 总计找回计数 | 由 `stats_counters` 持久化计数器累计（不受物品删除影响）；接口读取该计数（缺失时回退 `COUNT(*) WHERE status='claimed'`） |

> ⚠️ **v3.3 变更**：第4卡片从"今日找回"改为"总计找回"（累计值），移除累计活跃功能。**分类占比（`categories`）仍保留并由首页 ECharts 饼图渲染**——早期"移除分类占比"的表述与代码不符。

### 3.8 UI 设计系统 (FR-UI)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-UI-01 | 品牌色 | `#1B4D3E` 深翠绿，9 阶暖灰中性色板 |
| FR-UI-02 | 深色模式 | `[data-theme="dark"]` CSS 变量全覆盖。localStorage 持久化 + 系统主题跟随。导航栏 sun/moon 切换按钮 |
| FR-UI-03 | 骨架屏 | `<SkeletonCard />` 组件，shimmer 动画，用于列表页加载态 |
| FR-UI-04 | 毛玻璃认证页 | 登录/注册独立页面 — 校园航拍背景 + 半透明卡片(blur 24px) + 无导航栏 |
| FR-UI-05 | 响应式 | 断点 480px / 640px / 768px（移动/平板）+ 1440px / 1920px（桌面宽屏） |
| FR-UI-06 | 页面过渡动画 | pageIn/pageOut CSS keyframes (opacity + translateY) |
| FR-UI-07 | 阴影层级 | 5 级 (xs/sm/md/lg/xl) + focus 光环 |
| FR-UI-08 | 圆角系统 | 6 级 (4px/6px/10px/14px/20px/9999px) |
| FR-UI-09 | 间距系统 | 4px 网格 (4~48px) |
| FR-UI-10 | 字体层级 | 10 级 (11px~32px) |

---

## 4. 非功能性需求

### 4.1 性能需求

| 编号 | 需求 | 指标 |
|------|------|------|
| NFR-PERF-01 | 检索路径响应时间（`POST /api/items/match`） | **P95 < 2s**（CPU、无 GPU） |
| NFR-PERF-01b | 录入路径响应时间（发布 / 审核触发的图像编码） | **P95 < 15s**，标注为**一次性、可后台化** |
| NFR-PERF-01c | GPU 依赖 | **不强制 GPU**（CPU 可运行） |
| NFR-PERF-02 | 列表接口响应时间 | < 500ms |
| NFR-PERF-03 | 图片上传限制 | ≤ 16MB/张（物品图片）；v3.3 已移除头像功能 |
| NFR-PERF-04 | CLIP 模型 | 默认 **Chinese-CLIP ViT-H-14**（权重约 3.83GB），输出 L2 归一化 **1024 维**联合投影向量；回滚 **open_clip ViT-B-32**（约 600MB），输出 **512 维** |
| NFR-PERF-05 | 颜色特征复用 | `color_vector` 持久化于 `items` 表，避免每次匹配重复计算（v3.4.0 / R4） |

> ⚠️ **旧 `NFR-PERF-01`「匹配 < 3s」在 v3.5.0 作废**（口径偏旧、未按路径拆分），以本表的 `NFR-PERF-01 / 01b / 01c` 为准。

### 4.2 安全需求

| 编号 | 需求 | 实现 |
|------|------|------|
| NFR-SEC-01 | 密码加密 | bcrypt 加盐哈希 |
| NFR-SEC-02 | 认证机制 | JWT HS256，7 天过期，HTTP Bearer |
| NFR-SEC-03 | SQL 注入防护 | 全参数化查询（? 占位符） |
| NFR-SEC-04 | 权限校验 | `get_current_user`（验证 token + 用户存在 + `status` 不为 disabled/deleted）；`get_current_admin`（验证 `role='admin'`）；公开接口经 `resolve_optional_viewer` 解析可选身份，禁用/注销降级匿名（v3.4.0 / C1）；业务端点（含 `POST /api/items/match`）统一受 `get_current_user` 保护（v3.4.1） |
| NFR-SEC-05 | 文件安全 | 路径遍历防护（`..` 检测 + `os.path.basename`）；文件类型校验（魔数检测） |
| NFR-SEC-06 | 请求体校验 | 请求体经 Pydantic 模型校验，宽松模型保证非法参数仍返回 **400**（而非 422），维持既有契约（v3.4.0 / R9） |

### 4.3 可用性需求

| 编号 | 需求 | 实现 |
|------|------|------|
| NFR-USR-01 | 响应式设计 | 断点 480px / 640px / 768px（移动/平板）+ 1440px / 1920px（桌面宽屏） |
| NFR-USR-02 | 操作反馈 | ElMessage 成功/失败/警告；按钮 loading 状态 |
| NFR-USR-03 | 空状态引导 | el-empty + CTA 按钮 |
| NFR-USR-04 | 错误处理 | 全局异常处理器 → JSON 500；请求拦截器 → 401/403 处理 |

### 4.4 可扩展性需求

| 编号 | 需求 | 说明 |
|------|------|------|
| NFR-EXT-01 | 向量存储可迁移 | 纯 JSON 文本字段，可平滑迁移至 pgvector/FAISS |
| NFR-EXT-02 | 图片存储可迁移 | 本地文件路径，可切换为 OSS URL |
| NFR-EXT-03 | 异步任务可升级 | 当前 BackgroundTasks，可升级为 Celery + Redis |

---

## 5. 接口需求

### 5.1 认证接口

| 方法 | 路径 | 认证 | 请求体 | 响应 |
|------|------|:--:|------|------|
| POST | `/api/register` | ❌ | `{username, password, phone, email?}` | `{success, token, user}`（user 含 `status='active'`） |
| POST | `/api/login` | ❌ | `{username, password}` | `{success, token, user}`（`status='disabled'/'deleted'` 返回 403） |
| GET | `/api/me` | ✅ | — | `{user: {id, username, role, status, phone, email, created_at}}` |
| PUT | `/api/me` | ✅ | `{username?, password?, email?, phone?}` | `{success, message}` |
| GET | `/api/me/history` | ✅ | — | `{success, data: {my_items, my_claims}}` |
| DELETE | `/api/me` | ✅ | — | `{success, message}` |

> ⚠️ **v3.3 变更**：移除 `POST /api/me/avatar`（头像上传）和 `GET /api/avatars/{filename}`（头像访问）。`GET /api/me` 响应不再含 `avatar_path`。

### 5.2 物品接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| POST | `/api/items/` | ✅ | 发布物品（FormData） |
| GET | `/api/items/` | ❌ 公开 | 物品列表（分页+筛选）；匿名仅见已审核+活跃物品 |
| GET | `/api/items/{id}` | ❌ 公开 | 物品详情；未审核物品仅发布者/管理员可见 |
| GET | `/api/items/categories` | ❌ 公开 | 类别列表 |
| GET | `/api/items/uploads/{filename}` | ❌ 公开 | 访问物品图片（路径遍历防护） |
| POST | `/api/items/match` | ✅ | 智能匹配（需登录） |
| POST | `/api/items/temp-upload` | ✅ | 临时上传匹配图片 |
| PUT | `/api/items/{id}` | ✅ | 编辑物品（本人/管理员） |
| DELETE | `/api/items/{id}` | ✅ | 删除物品（本人/管理员） |
| POST | `/api/items/{id}/claim` | ✅ | 申请认领/归还（通知含申请人手机号） |
| PUT | `/api/items/{id}/mark-claimed` | ✅ | 发布者标记物品已找回/已认领 |

> ⚠️ **v3.3 变更**：删除 `PUT /api/items/{id}/claim/confirm`（确认/拒绝认领）。新增 `PUT /api/items/{id}/mark-claimed`（发布者自标记）。
>
> ⚠️ **v3.4.0（C1）**：`GET /api/items/`、`GET /api/items/{id}` 为公开接口，对携带 token 的禁用/注销用户，经 `resolve_optional_viewer` 解析后**降级为匿名**（返回公开可见内容而非 403）。
>
> **v3.4.1**：`POST /api/items/match` 已补齐鉴权（`Depends(get_current_user)`）——缺 `Authorization` 头 → 403 `{"detail":"Not authenticated"}`；token 非法 / 过期 → 401 `{"detail":"无效或过期的 Token"}`。前端 `/match` 路由本就以 `requiresAuth` 守卫，拦截器自动附带 token。
>
> **v3.5.0**：`POST /api/items/match` 结果项新增 `match_source`（∈ `text` / `image` / `mixed`），响应顶层新增 `legend: {high, mid}`（派生自三档阈值，可由 `MATCH_LEGEND_HIGH` / `_MID` 覆盖）；打分前做**向量维度预检**，库中向量维度 ≠ 当前模型维度 → **HTTP 500**（提示先运行 `reembed_all_vectors.py`），不再静默返回空集。**403/401 契约不变，未新增端点**。

### 5.3 管理员接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/admin/reviews` | Admin | 待审核列表（分页） |
| PUT | `/api/admin/reviews/{id}` | Admin | 审核操作（通过/驳回） |
| POST | `/api/admin/reviews/batch-approve` | Admin | 批量审核通过 |
| GET | `/api/admin/users` | Admin | 用户列表（分页） |
| PUT | `/api/admin/users/{id}` | Admin | 用户管理（设角色 / 切换状态） |
| POST | `/api/admin/users` | Admin | 新增用户 |
| DELETE | `/api/admin/users/{id}` | Admin | 逻辑删除用户（`status` → `deleted`） |

> ⚠️ **v3.4.0（O2）**：`PUT`/`DELETE` 针对**操作者自身**（target==current）时返回 400；针对其他管理员账号允许操作。

### 5.4 通知接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/notifications/unread/count` | ✅ | 未读数量 |
| GET | `/api/notifications/unread` | ✅ | 未读列表 |
| PUT | `/api/notifications/{id}/read` | ✅ | 标记单条已读 |
| PUT | `/api/notifications/read-all` | ✅ | 一键全部已读 |

### 5.5 数据统计接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/stats/dashboard` | ✅ | 展示中/今日失物/今日拾物/总计找回 + 分类占比 `categories` |

> ⚠️ **v3.3 变更**：移除累计活跃数据。`total_claimed` 替代 `today_claimed`，统计 `status='claimed'` 的物品总数（由 `stats_counters` 持久化计数器提供）。
>
> ⚠️ **勘误（v3.4.0 复核）**：接口仍返回 `categories`（分类占比），前端首页以 ECharts 饼图渲染——早期"移除分类占比"的表述与代码不符。

### 5.6 公告接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/announcements` | ✅ | 获取公告列表 |
| POST | `/api/announcements` | Admin | 发布公告 |
| PUT | `/api/announcements/{id}` | Admin | 编辑公告 |
| DELETE | `/api/announcements/{id}` | Admin | 删除公告 |

### 5.7 错误响应格式

```json
{"detail": "错误描述"}
```

HTTP 状态码：`400` 参数错误 / `401` 未认证 / `403` 权限不足 / `404` 不存在 / `409` 冲突 / `422` 校验失败 / `500` 服务器错误

---

## 6. 数据需求

### 6.1 用户表 (users)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 用户 ID |
| username | TEXT | UNIQUE NOT NULL | 用户名 (2-20字符) |
| password_hash | TEXT | NOT NULL | bcrypt 哈希 |
| phone | TEXT | | 手机号 (11位) |
| email | TEXT | | 邮箱（选填） |
| role | TEXT | DEFAULT 'user' | 账号角色：`user` / `admin` |
| status | TEXT | DEFAULT 'active' | 账号状态：`active` / `disabled` / `deleted`（⚠️ v3.4.0 新增；迁移时将旧 `role` 的 disabled/deleted 折算到 `status` 并回写 `role='user'`） |
| avatar_path | TEXT | | ⚠️ v3.3 废弃 — 头像功能已移除，列保留不删 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 注册时间 |

### 6.2 物品表 (items)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK AUTOINCREMENT | 物品 ID |
| type | TEXT | NOT NULL CHECK(lost/found) | 失物/拾物 |
| title | TEXT | NOT NULL | 标题 (2-50字符) |
| description | TEXT | | 描述 |
| category | TEXT | | 类别 |
| image_path | TEXT | | 图片路径 |
| image_vector | TEXT | | CLIP 图像特征 (JSON)；维度随后端（`cn_clip` 1024 / `open_clip` 512） |
| text_vector | TEXT | | CLIP 文本特征 (JSON)；维度随后端（`cn_clip` 1024 / `open_clip` 512） |
| color_vector | TEXT | | 27维 RGB 颜色直方图特征 (JSON)（⚠️ v3.4.0 新增，用于颜色相似度增强） |
| contact | TEXT | | 联系方式 |
| location | TEXT | | 地点 |
| status | TEXT | CHECK(6 states) | pending/active/claimed/done/rejected/closed |
| user_id | INTEGER | FK→users.id | 发布者 |
| review_status | TEXT | CHECK(3 states) | pending/approved/rejected |
| reviewer_id | INTEGER | FK→users.id | 审核人 |
| review_time | TIMESTAMP | | 审核时间 |
| reject_reason | TEXT | | 驳回理由 (≤200字符) |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 发布时间 |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**索引**: user_id, type, status, review_status, created_at

### 6.3 匹配记录表 (matches)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | PK |
| lost_item_id | INTEGER | FK→items.id |
| found_item_id | INTEGER | FK→items.id |
| similarity_score | REAL | 余弦相似度 (0~1) |
| is_confirmed | INTEGER | DEFAULT 0 |
| confirmed_at | TIMESTAMP | |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**索引**: lost_item_id, found_item_id

### 6.4 通知表 (notifications)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | PK |
| user_id | INTEGER | FK→users.id |
| title | TEXT | 通知标题 |
| content | TEXT | 通知内容 |
| link | TEXT | 跳转路径 (/items/{id}) |
| is_read | INTEGER | DEFAULT 0 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

**索引**: (user_id, is_read) 复合索引

### 6.5 公告表 (announcements) 与计数表 (stats_counters)

| 表 | 关键字段 | 说明 |
|----|---------|------|
| announcements | id, title, content, target_role, created_at | 管理员发布，按可见范围展示（v3.3 引入） |
| stats_counters | key, value | 持久化计数器（如 `total_claimed`），不受物品删除影响（v3.3） |

### 6.6 类别常量

```
CATEGORIES = ['电子产品', '证件卡片', '包袋箱包', '书籍文具', '服装配饰', '钥匙门禁', '其他']
```

---

## 7. 前端页面需求

### 7.1 页面清单

| 路由 | 组件 | 布局 | 权限 | 关键功能 |
|------|------|:--:|------|------|
| `/login` | LoginView | 独立(毛玻璃) | 未登录 | 校园航拍背景 + 半透明卡片 + 登录后按角色自动跳转 |
| `/register` | RegisterView | 独立(毛玻璃) | 未登录 | 注册表单(用户名/密码/手机/邮箱) |
| `/items` | HomeView | DefaultLayout | 登录 | 公告栏 + 统计看板(4卡片+饼图) + 筛选栏 + 卡片网格 + 骨架屏 + 分页 |
| `/items/:id` | ItemDetailView | DefaultLayout | 登录 | 双栏布局 + 状态标签 + 「我要认领/归还」或「标记已找回/已认领」按钮 + 编辑/删除 |
| `/publish` | PublishView | DefaultLayout | 登录 | 表单卡片 + 图片上传 + 编辑模式(`?edit=`) |
| `/match` | MatchView | DefaultLayout | 登录 | 匹配面板 + 图片/文字输入 + 相似度进度条 |
| `/admin` | AdminView | DefaultLayout | 管理员 | 三标签(物品审核+批量通过+用户管理+公告管理) |
| `/notifications` | NotificationsView | DefaultLayout | 登录 | 通知卡片 + 标记已读 + 一键全部已读 + 链接跳转 |
| `/profile` | ProfileView | DefaultLayout | 登录 | 信息横幅(首字母头像) + Tab分段(账户设置/联系方式/历史记录) + 危险区域(注销) |

> ⚠️ **v3.3 变更**：所有页面均需登录（去除访客浏览权限）。个人中心重设计：砍掉头像上传、引入 Tab 分段式布局、新增历史记录模块。

### 7.2 布局组件

| 组件 | 功能 |
|------|------|
| DefaultLayout | 玻璃拟态 Header + 导航(药丸形激活态) + 主题切换按钮 + 用户下拉菜单 + Footer |
| App.vue | 条件布局：认证路由独立渲染，其余路由包裹 DefaultLayout |
| SkeletonCard | 骨架屏卡片组件（shimmer 动画） |

### 7.3 状态管理

| Store | 状态 | 持久化 |
|-------|------|:--:|
| authStore | token, user, isAdmin | localStorage |
| notificationStore | unreadCount | 内存 (路由钩子+30s轮询刷新) |

---

## 8. 核心算法说明

### 8.1 CLIP 特征提取

```
图片 → Image Encoder → 1024维 L2归一化向量（cn_clip ViT-H-14，默认）
                     →  512维 L2归一化向量（open_clip ViT-B-32，回滚）
文本 → Text Encoder  → 与图像同维（同一联合投影空间；两代向量空间不兼容）
图片 → RGB 直方图     → 27维颜色特征（余弦相似度，与模型无关）
```

延迟加载：首次调用 `get_image_feature()` 或 `get_text_feature()` 时按 `CLIP_BACKEND` 选择后端并初始化模型。`CLIPService` 为兼容壳，实际编码委托 `app/clip_backend.py`；每个 `encode_*` 在 L2 归一化后经 `_assert_embed_dim` 断言维度。

### 8.2 加权相似度融合（四通道跨模态 + 五阶段）

```
通道（q=查询, t=目标）:
  sim_img_img = q_img·t_img;  sim_text_text = q_text·t_text
  sim_cross_t2i = q_text·t_img;  sim_cross_i2t = q_img·t_text
  sim_cross = 可用跨模态方向加权平均（内权重 0.5/0.5）

阶段1 基础加权: Sim = 0.35×sim_img_img + 0.35×sim_cross + 0.15×sim_text_text + 0.15×sim_color
              （缺失通道时动态权重归一化；全缺 → 0.0）
阶段2 类别/位置调节: 同类 +5% / 异类 -8%；同地点 +3% / 异地 -4%
阶段3 时间衰减: 90 天线性衰减至下限 20%
阶段4 分层阈值: 手动匹配 0.35 / 自动推送 0.55 / 邮件通知 0.70（初值待标定）
阶段5 跨模态一致性惩罚: cc = min(可用跨模态方向)；仅当 max(sim_ii,sim_tt)≥0.55 触发；
              只降权、对 cc 单调，因子 ∈ [0.5, 1.0]；CROSS_PENALTY_ENABLED 可关闭
```

> 颜色通道使用 `items.color_vector`（27 维 RGB 直方图）与查询图的颜色特征做余弦相似度；v3.4.0 起该特征持久化于数据库，避免每次匹配重算。
>
> ⚠️ 四通道权重、跨模态内权重、阶段5 参数与三档阈值均为 **v3.5.0 初值，尚未用真实模型标定**；旧「阶段5 交叉验证（图文矛盾降权 50%~75%）」已被上述真跨模态惩罚取代。

### 8.3 自动匹配流程

```
管理员审核通过
  → 若 AUTO_MATCH_ENABLED=false 短路（灰度期）
  → BackgroundTasks.add_task(auto_match_and_notify)
  → 查询异类活跃物品 (type相反, status=active, review_status=approved)
  → 维度预检：库向量维度 ≠ 当前模型维度 → 记 ERROR 并跳过
  → 逐对计算四通道跨模态 + 五阶段加权相似度
  → 筛选 ≥ MATCH_THRESHOLD_AUTO (0.55，初值) 的匹配
  → 批量 INSERT matches 表
  → 双向发送站内通知 (新物品发布者 + 目标物品拥有者)
  → 相似度 ≥ MATCH_THRESHOLD_EMAIL (0.70，初值) 且有邮箱时发送 HTML 邮件（异步投递）
```

### 8.4 认领/归还语义规则

| 物品类型 | 操作者视角 | 操作 | 系统行为 |
|---------|-----------|---------|---------|
| lost | 非发布者(捡到者) | "我要归还" | 发送 `[归还申请]` 通知给发布者（附申请人手机号） |
| found | 非发布者(失主) | "我要认领" | 发送 `[认领申请]` 通知给发布者（附申请人手机号） |
| 任一 | 发布者 | "标记已找回"/"标记已认领" | 物品 status → claimed，从列表移除并计入历史；总计找回 +1 |

> ⚠️ **v3.3 变更**：删除发布者"确认/拒绝"两步流程（原 `PUT /api/items/{id}/claim/confirm`），改为发布者**自行标记**（`PUT /api/items/{id}/mark-claimed`）。线下联系通过通知中的手机号进行。

---

## 9. 约束与假设

### 9.1 技术约束

| 约束 | 说明 |
|------|------|
| Python ≥ 3.11 | 后端运行环境 |
| Node.js ≥ 20 | 前端构建环境 |
| 磁盘 ≥ 5GB | 默认 Chinese-CLIP ViT-H-14 权重约 3.83GB（回滚 open_clip ViT-B-32 约 600MB）+ 依赖 |
| SQLite | 毕设阶段零配置数据库 |
| CPU 推理 | CLIP 在 CPU 上运行，GPU 可选 |
| 端口 8000 | 后端默认端口 |
| 端口 5173 | 前端开发服务器默认端口 |

### 9.2 业务假设

| 假设 | 说明 |
|------|------|
| 管理员手动创建 | 首个管理员需通过数据库直接插入或 Python 脚本创建 |
| 邮件可选 | 未配置 SMTP 时静默跳过邮件通知 |
| 单张图片 | 每个物品仅支持 1 张图片 |
| 用户自行联系 | 认领确认后用户自行通过联系方式沟通取回 |

### 9.3 已知限制

| 限制 | 影响 | 建议 |
|------|------|------|
| SQLite 写锁 | 并发写入 > 20 时性能下降 | 迁移 PostgreSQL |
| JSON 向量存储 | 全表扫描计算相似度 | 引入 pgvector ANN 索引 |
| 无 WebSocket | 通知非实时 | 引入 WebSocket 推送 |
| 无草稿箱 UI | 驳回物品无独立管理入口 | 在发布页增加草稿列表 |
| ~~真实 Chinese-CLIP 权重未下载验证~~ ✅ 已下载并端到端验证 | 权重 3.83GB 已在**本机**下载（ModelScope 源，`CLIP_CN_CKPT_PATH` 零网络加载）并验证：1024 维 + L2 归一 + 语义合理 + 真实 Recall@K | 已闭环（`scripts/verify_real_clip.py`；`RUN_REAL_CLIP=1` 冒烟 2 用例由 skip 转通过） |
| **分层阈值 AUTO/EMAIL 仍不可用** | 真实模型下标定：`Recall@3=1.0`、`Recall@1=0.7917`，但默认配置下 PR 曲线 Precision 上界仅 **0.6129** → `Precision≥0.90/0.98` **无解**，`AUTO`/`EMAIL` 返回 `None` | 有效样本仍小（n=64）；须扩充真实数据复标；**不得为凑出 0.90 而放宽口径** |
| **权重的「最优值」证据不足** | 权重网格合格组合达 **103** 个、其中 **102** 个并列 `Recall@3=1.0` → 无唯一最优，只能给出**方向性**结论（`W_COLOR≈0`、文本主导） | 扩充评测集后重跑 `--grid`；见 `docs/review/threshold-calibration-v3.5.0.md` §5 |
| ~~两代向量空间不兼容~~ ✅ 本库已完成重嵌入（2026-09-14） | 切模型未重嵌入则新旧向量不可比（已加维度防线 → HTTP 500） | 已执行 `reembed_all_vectors.py` 全量重嵌入（冷备 + 守卫，6 条全部 1024 维）；`/match` 实测恢复 HTTP 200 |
| **评测集规模小** | `eval_set_v3.5.0.json` **70 对**（有效 **24 正 / 40 负**，n=64），置信区间宽 | 随数据增长扩充复标；不得表述为「已可靠标定」 |

---

> **文档维护者**：开发团队 | **最后更新**：2026-09-14 | **基于源码版本**：v3.5.0
>
> **v3.4.0 核心变更摘要**：账户状态语义拆分（C2：`role` 收敛为 user/admin，新增 `status`） | 公开接口账号状态校验（C1：`resolve_optional_viewer`） | 颜色特征持久化（R4：`items.color_vector`） | 邮件异步化（R5）| 路由 `:int` 健壮化（R6）| 去静默异常（R7）| 请求体 Pydantic 化（R9）| 依赖与版本清理（R10）| 自动化测试 70 用例全通过
>
> **v3.4.1 补齐**：`POST /api/items/match` 鉴权（缺 token → 403 / 非法 token → 401）| 自动化测试扩至 **72 用例**全通过
>
> **v3.5.0 中文化模型 + 跨模态检索**：新增 `app/clip_backend.py` 双后端抽象（默认 `cn_clip` Chinese-CLIP ViT-H-14 **1024 维** / 回滚 `open_clip` ViT-B-32 **512 维**，未知值抛 `RuntimeError`）| 启用 img·text **跨模态四通道**打分（图-图 0.35 / 跨模态 0.35 / 文-文 0.15 / 色 0.15）| 阶段5 升级为**真跨模态一致性惩罚**（`cc=min(可用跨模态方向)`，≥0.55 触发，只降权 ≤×0.5，可开关）| 阈值重设（手动 0.35 / 自动 0.55 / 邮件 0.70，初值）| `/match` 新增 `match_source` + `legend`（**403/401 契约冻结不变，不新增端点**）| 新增三脚本（`reembed_all_vectors.py` / `calibrate_thresholds.py` / `backfill_color_vectors.py`）| 评测集 **70 对**（30 正 / 40 负）| 维度错配运行期防线（编码断言 + 打分前预检 → HTTP 500）| 自动化测试扩至 **209 用例（207 通过 / 2 门控跳过）**。⚠️ **真实权重已下载并端到端验证（真实 `Recall@3 = 1.0` / `Recall@1 = 0.7917`）；且已补 10 对同类硬负样本，但分层阈值仍不可用** —— 默认配置下 Precision 上界仅 0.6129，`AUTO`/`EMAIL` 仍无解（详见 `docs/review/threshold-calibration-v3.5.0.md` §5）。✅ **生产库已完成全量重嵌入（2026-09-14，冷备 + `_exit_code` 守卫，6 条全部 1024 维）**，`/match` 实测恢复 HTTP 200；`AUTO_MATCH_ENABLED=false` 灰度保持
