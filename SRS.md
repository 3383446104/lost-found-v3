# 校园失物检索平台 — 软件需求规格说明书 (SRS)

> 版本：v3.6.0 | 日期：2026-10-14 | 基于 v3.3 源码 + v3.4.x 加固 + v3.5.0 中文化模型 / 跨模态检索 + v3.6.0 打分口径重构与社区化融合，逐项与代码对齐

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
- 失物/拾物信息发布与管理（**1-3 张图片**、拖拽排序、首图封面）
- 基于 **Chinese-CLIP ViT-H-14**（默认，中文图文跨模态）多模态模型的图文特征提取与智能匹配（**三检索模式** + 主辅证据加权 + 跨模态尺度映射 + 证据链）；`open_clip ViT-B-32` 为可回滚后端
- 管理员审核机制（通过/驳回 + 双向邮件通知 + 设为首页推荐）
- 站内消息与 QQ 邮箱 HTML 邮件通知（含匹配等级与命中依据）
- **认领闭环**（申请含特征描述 + 证明图 → 发布者审批（互斥自动拒绝）→ 归还确认；联系方式分级可见（申请通过后向申请人展示完整号码）；v3.6.0 起取代旧"通知式认领"）
- **社区互动**（五类举报 + 处理留痕 + 进度查询；楼中楼留言）
- **内容运营**（轮播图 / 分类管理 / 公告草稿）与**相似推荐**（详情页相似物品、首页推荐位）
- 数据统计看板（首页 4 卡片 + 分类占比；管理端找回率 / 发布趋势 / 分类占比）
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

> ⚠️ **v3.4.0（C2）**：守卫判定字段由 `user.role === 'disabled'` 改为 `user.status === 'disabled'`（见 `frontend/src/router/index.js`）。

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
| FR-ITEM-01 | 发布物品 | `POST /api/items/` — FormData: type(lost/found)、title(2-50字符)、description(≤500字)、category、contact、location、image(≤16MB)。自动提取 CLIP 图像+文本特征（维度随后端：`cn_clip` 1024 / `open_clip` 512）。初始状态 review_status=pending, status=pending |
| FR-ITEM-02 | 物品列表（分页+筛选） | `GET /api/items/` — 参数: type/category/keyword/user_id/limit/offset。管理员看全部；普通用户看 (approved+active) OR 自己物品；匿名仅看已审核+活跃物品 |
| FR-ITEM-03 | 分类筛选 | 全部/失物/拾物/仅我的 |
| FR-ITEM-04 | 类别筛选 | 7 类别：电子产品/证件卡片/包袋箱包/书籍文具/服装配饰/钥匙门禁/其他 |
| FR-ITEM-05 | 关键词搜索 | title 或 description LIKE 模糊匹配 |
| FR-ITEM-06 | 物品详情 | `GET /api/items/{id}` — 公开访问，未审核物品仅限发布者/管理员可见。返回全部字段（不含向量） |
| FR-ITEM-07 | 编辑物品 | `PUT /api/items/{id}` — 仅本人/管理员。支持更换图片（自动删旧图+重提取特征）。非管理员编辑后 review_status 重置为 pending |
| FR-ITEM-08 | 删除物品 | `DELETE /api/items/{id}` — 仅本人/管理员。同时删除图片文件 |
| FR-ITEM-09 | 图片访问 | `GET /api/items/uploads/{filename}` — 公开，路径遍历防护 |
| FR-ITEM-10 | 多图上传（v3.6.0） | 1-3 张，首图封面（`images` 有序 JSON）；**仅封面参与向量检索**；编辑用 `keep`（保留文件新顺序）+ 新图，封面变更才重算向量、移除的文件同步删除 |

### 3.3 智能匹配模块 (FR-MATCH)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-MATCH-01 | 以图搜图 | `POST /api/items/match` — 上传 temp 图片 → CLIP 图像特征 → 计算与目标物品余弦相似度 |
| FR-MATCH-02 | 以文搜图（**真跨模态**） | 输入文字 → CLIP 文本特征 → 与目标**图片**特征计算跨模态相似度（`sim_cross_t2i = q_text · t_img`，而非仅比文本自相似） |
| FR-MATCH-03 | 图文混合匹配 | 同时提供图片+文字；按查询形态的**三种检索模式**（文字 / 图片 / 图文混合）由缺通道动态归一化自动成形，混合模式权重 ≈ 0.43 / 0.43 / 0.14 |
| FR-MATCH-04 | 加权相似度算法（主辅证据 + 五阶段） | 权重「**主证据 + 辅助证据**」：同模态（文-文 / 图-图）0.75、跨模态 0.25（缺通道动态归一化）；**跨模态尺度映射** 0.194→0 / 0.298→1（仅外层加权与展示）；跨模态内 `q_text·t_img` 与 `q_img·t_text` 各 0.5；叠加类别/位置调节（+0.05/-0.08、+0.03/-0.04）、时间衰减（240 天 / 下限 0.6）、分层阈值与**阶段5 跨模态一致性惩罚**（触发条件收窄为「文-文高且图-图不高」）；**颜色通道 2026-09-16 废弃** |
| FR-MATCH-05 | 结果排序 | 按 `match_score`（含时间衰减）降序返回 Top 20，仅匹配 active + approved 物品；判定用 `content_score` ≥ 阈值 |
| FR-MATCH-06 | 分层阈值（**已标定**） | 手动 0.624956 / 自动 0.733952（P=91.7% / R=61.1%）/ 邮件 0.832069（P=100% / R=19.4%）；**内容分尺度**（2026-09-21） |
| FR-MATCH-07 | 临时图片上传 | `POST /api/items/temp-upload` — 上传后返回文件名，匹配后自动删除 |
| FR-MATCH-08 | 匹配来源标注 + 证据链 | 结果项含 `match_source`（∈ `text` / `image` / `mixed`）与 `level`（confirmed / high_suspect / related / reference）、`basis`（命中依据）、`channels`（各通道原始值）；响应顶层含 `legend: {high, mid}`（由阈值派生）；三分数：`content_score`（判定）/ `match_score`（排序）/ `similarity` = `reference_score`（展示） |
| FR-MATCH-09 | 多图检索（v3.6.0） | `image_paths` ≤3：各图向量 L2 归一化 → 均值 → 再归一化（**仅查询侧聚合**）；物品侧仅封面参与 |
| FR-MATCH-10 | 相似推荐（v3.6.0） | `GET /api/items/{id}/similar` — 反类型 + 复用 `compute_match_detail`，内容分 ≥ 手动阈值，按展示分排序 |

### 3.4 管理员审核模块 (FR-ADMIN)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-ADMIN-01 | 待审核列表（分页） | `GET /api/admin/items?review=pending` — 物品管理 Tab 内嵌待审核列表（review_status=pending，分页） |
| FR-ADMIN-02 | 审核通过 | `PUT /api/admin/reviews/{id}` action=approved → status=active, review_status=approved。BackgroundTasks 异步触发自动匹配 |
| FR-ADMIN-03 | 审核驳回 | action=rejected → status=rejected, review_status=rejected。发送站内通知（含驳回理由）+ HTML 邮件（含重新编辑链接） |
| FR-ADMIN-04 | 自动匹配推送 | 审核通过后异步匹配异类物品（失物↔拾物），**维度预检**通过后逐对打分；**判定用内容分 ≥ 0.733952**（`MATCH_THRESHOLD_AUTO`，与标定同尺度；2026-09-21 尺度修正），双向推送通知 + 邮件（含匹配等级与命中依据） |
| FR-ADMIN-05 | 批量审核通过 | `POST /api/admin/items/batch` action=approve — 多选物品 → 一键批量通过（同端点支持 close/delete）。驳回不支持批量（需逐一填写理由+站内通知） |
| FR-ADMIN-06 | 防止重复审核 | SQL `WHERE review_status='pending'` 条件更新 + rowcount 检查（单条+批量均适用） |
| FR-ADMIN-07 | 用户管理 | `GET /api/admin/users` — 用户列表（分页）；支持逻辑删除用户（`status` → `deleted`） |
| FR-ADMIN-08 | 用户角色/状态变更 | `PUT /api/admin/users/{id}` — 设角色（user/admin）/ 切换账号状态（active↔disabled）。**v3.4.0：禁用/启用只改 `status` 并保留 `role`** |
| FR-ADMIN-09 | 审核设推荐（v3.6.0） | 审核操作可传 `is_recommend`，写入 `items.is_recommend`（首页"为你推荐"数据源） |

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

### 3.6 认领闭环模块 (FR-CLAIM)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-CLAIM-01 | 申请认领/归还 | `POST /api/claims` — lost物品→"我要归还"(我捡到了)，found物品→"我要认领"(我丢失了)。通知 + 邮件中含申请人手机号（从用户账户获取） |
| FR-CLAIM-02 | 防重复申请 | 同物品+同用户已有未读申请通知时拒绝，返回 400 "已发送申请，请等待回复" |
| FR-CLAIM-03 | 发布者自标记 | `PUT /api/items/{id}/mark-claimed` — 发布者对自己的物品点击"已找回"(lost)/"已认领"(found)→ status 变为 claimed。物品从列表消失，转至个人中心历史记录 |
| FR-CLAIM-04 | 总计找回计数 | 每次标记 claimed 后，总计找回数自动 +1（持久化计数器） |
| FR-CLAIM-05 | 已认领物品展示 | claimed 物品在详情页显示"该物品已找回"状态标签，隐藏所有操作按钮 |
| FR-CLAIM-06 | 历史记录查看 | `GET /api/me/history` — 个人中心查看自己发布的所有物品（含已认领/已驳回/已关闭）+ 认领记录 |
| FR-CLAIM-07 | 认领申请（v3.6.0） | `POST /api/claims` — feature_description 必填、proof_image（`proof_` 持久上传）。校验物品 active+approved、非本人、同人同物无进行中申请（status∈0/1） |
| FR-CLAIM-08 | 申请列表与按钮态（v3.6.0） | `GET /api/claims/mine` / `received`（分页）/ `status/{item_id}`（详情页按钮态驱动） |
| FR-CLAIM-09 | 审批与互斥（v3.6.0） | `POST /api/claims/{id}/approve`（发布者）— **同一事务**：0→1 + 同物品其他待审自动置 2（互斥）+ 物品转 `claiming`；通知申请人（通过后可见完整联系方式） |
| FR-CLAIM-10 | 拒绝 / 撤销 / 完成（v3.6.0） | `reject`（`review_remark` 必填，物品保持 active）/ `cancel`（申请人，0→4）/ `complete`（1→3 + 物品 `claimed` + `increment_counter('total_claimed')`） |
| FR-CLAIM-11 | 联系方式分级可见（v3.6.0） | `GET /api/claims/{id}` 三方权限（申请人/发布者/管理员）；status∈(1,3) 时向申请人返回**完整**联系方式，此前为 null；公开接口（items 列表/详情）对非发布者/非管理员脱敏（138\*\*\*\*1234） |

> ⚠️ **v3.3 变更**：删除原有的"确认/拒绝"两步流程（`PUT /api/items/{id}/claim/confirm`），改为发布者自行标记。线下联系通过通知中附带的手机号进行。
>
> **v3.6.0 升级为认领闭环**：新表 `claims` 取代通知式认领（status：0 待审核 / 1 已通过 / 2 已拒绝 / 3 已完成 / 4 已撤销）；`mark-claimed` 允许 active/claiming 两态并联动已完成申请（**计数器不重复计数**）。

### 3.7 社区互动模块 (FR-COMMUNITY) — v3.6.0

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-REPORT-01 | 提交举报 | `POST /api/reports` — report_type ∈ 1 虚假信息 / 2 不良内容 / 3 联系方式异常 / 4 重复发布 / 5 其他；reason 必填；同人同物 pending 去重 |
| FR-REPORT-02 | 我的举报进度 | `GET /api/reports/mine` — 待处理 / 已处理 / 已驳回 |
| FR-REPORT-03 | 管理端列表与详情 | `GET /api/reports/admin`（keyword / type / status 筛选，pending 优先）+ `/{id}`（并排：举报全字段 + 被举报物品快照） |
| FR-REPORT-04 | 处理留痕 | `PUT /api/reports/admin/{id}/handle` — handle_result 必填，写 handler_id / handle_time，通知举报人 |
| FR-COMMENT-01 | 留言列表 | `GET /api/comments/item/{item_id}` — 公开，仅 status=1，扁平结构（含 username / is_mine），前端组树 |
| FR-COMMENT-02 | 发表 / 楼中楼回复 | `POST /api/comments` — content ≤ 500 字；parent 须同物品且可见 |
| FR-COMMENT-03 | 删除 / 隐藏 | `DELETE /api/comments/{id}`（本人 / 管理员；**父留言级联删回复**）+ `PUT /api/comments/admin/{id}/status`（隐藏 / 恢复）+ `GET /api/comments/admin`（管理端列表） |

### 3.8 内容运营模块 (FR-OPS) — v3.6.0

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-OPS-01 | 轮播图 | 公开 `GET /api/banners`（仅启用、sort_no 升序）；管理端上传（`banner_` 前缀）+ CRUD（标题 / 描述 / 跳转链接 / 排序 / 启停） |
| FR-OPS-02 | 分类管理 | `GET/POST/PUT/DELETE /api/categories/admin*` — 表驱动（种子 7 类）；**被物品使用的分类删除返回 400**；`GET /api/items/categories` 空表回退常量（响应结构不变） |
| FR-OPS-03 | 公告草稿 / 发布分离 | announcements 加 `status`（draft / published）；公开列表仅 published；`PUT /{id}/publish` / `unpublish` |

### 3.9 管理端统计模块 (FR-STATS-ADMIN) — v3.6.0

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-STATS-ADMIN-01 | 总览 | `GET /api/stats/admin/overview` — 物品总数 / 待审核 / 已完成 / 用户数 |
| FR-STATS-ADMIN-02 | 找回率 | `GET /api/stats/admin/recovery` — claimed_total = max(计数器, by_type 求和)；rate = claimed/(claimed+active+claiming)，分母 0 → 0 |
| FR-STATS-ADMIN-03 | 发布趋势 | `GET /api/stats/admin/publish-trend?days=30` — lost / found 拆分，**北京时间区间口径**（复用 `_bj_day_utc_range`） |
| FR-STATS-ADMIN-04 | 分类占比 | `GET /api/stats/admin/category-pie` |

### 3.10 数据统计模块 (FR-STATS)

| 编号 | 功能 | 实现细节 |
|------|------|---------|
| FR-STATS-01 | 首页看板 | `GET /api/stats/dashboard` — 展示中物品总数/今日失物/今日拾物/总计找回数量 + 分类占比 `categories` |
| FR-STATS-02 | 统计卡片 + 饼图 | 首页 4 卡片（展示中/今日失物/今日拾物/总计找回）+ 分类占比饼图，彩色数字，响应式 2×2 网格 |
| FR-STATS-03 | 总计找回计数 | 由 `stats_counters` 持久化计数器累计（不受物品删除影响）；接口读取该计数（缺失时回退 `COUNT(*) WHERE status='claimed'`） |

> ⚠️ **v3.3 变更**：第4卡片从"今日找回"改为"总计找回"（累计值），移除累计活跃功能。**分类占比（`categories`）仍保留并由首页 ECharts 饼图渲染**——早期"移除分类占比"的表述与代码不符。

### 3.11 UI 设计系统 (FR-UI)

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
| NFR-PERF-05 | 颜色通道（已移除） | 颜色通道 **2026-10-16 整体移除**（2026-09-16 起已不参与打分）：不再计算/存储/读取任何颜色特征 |
| NFR-PERF-06 | 多图上传限制（v3.6.0） | 每物品 1-3 张，单张 ≤ 16MB；**仅封面编码向量**（录入成本不随图数增长） |

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
| GET | `/api/items/categories` | ❌ 公开 | 类别列表（v3.6.0 表驱动，空表回退常量） |
| GET | `/api/items/uploads/{filename}` | ❌ 公开 | 访问物品图片（路径遍历防护） |
| GET | `/api/items/recommend` | ❌ 公开 | 首页推荐位（is_recommend=1 + active + approved） |
| GET | `/api/items/{id}/similar` | ❌ 公开 | 详情页相似物品（反类型 + 复用匹配口径） |
| POST | `/api/items/match` | ✅ | 智能匹配（需登录；支持 `image_paths` 多图 ≤3） |
| POST | `/api/items/temp-upload` | ✅ | 临时上传匹配图片 |
| PUT | `/api/items/{id}` | ✅ | 编辑物品（本人/管理员；多图 `keep` + 新图） |
| DELETE | `/api/items/{id}` | ✅ | 删除物品（本人/管理员；清理全部图片） |
| PUT | `/api/items/{id}/mark-claimed` | ✅ | 发布者标记物品已找回/已认领（允许 active/claiming，联动已完成申请） |

> ⚠️ **v3.3 变更**：删除 `PUT /api/items/{id}/claim/confirm`（确认/拒绝认领）。新增 `PUT /api/items/{id}/mark-claimed`（发布者自标记）。
>
> ⚠️ **v3.4.0（C1）**：`GET /api/items/`、`GET /api/items/{id}` 为公开接口，对携带 token 的禁用/注销用户，经 `resolve_optional_viewer` 解析后**降级为匿名**（返回公开可见内容而非 403）。
>
> **v3.4.1**：`POST /api/items/match` 已补齐鉴权（`Depends(get_current_user)`）——缺 `Authorization` 头 → 403 `{"detail":"Not authenticated"}`；token 非法 / 过期 → 401 `{"detail":"无效或过期的 Token"}`。前端 `/match` 路由本就以 `requiresAuth` 守卫，拦截器自动附带 token。
>
> **v3.5.0**：`POST /api/items/match` 结果项新增 `match_source`（∈ `text` / `image` / `mixed`），响应顶层新增 `legend: {high, mid}`（派生自三档阈值，可由 `MATCH_LEGEND_HIGH` / `_MID` 覆盖）；打分前做**向量维度预检**，库中向量维度 ≠ 当前模型维度 → **HTTP 500**（提示先运行 `reembed_all_vectors.py`），不再静默返回空集。**403/401 契约不变，未新增端点**。
>
> **v3.6.0**：新增 `GET /items/recommend` 与 `GET /items/{id}/similar`；多图（1-3 张）**仅封面参与向量检索**；`/match` 请求新增 `image_paths`（≤3，仅查询侧聚合）、结果项新增 `similarity`（展示分）/ `content_score` / `match_score` / `level` / `basis` / `channels`（打分口径重构，判定改用 `content_score`）。

### 5.3 管理员接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| PUT | `/api/admin/reviews/{id}` | Admin | 审核操作（通过/驳回，可设推荐） |
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
| GET | `/api/stats/admin/overview` | Admin | 管理端总览（物品总数/待审核/已完成/用户数）（v3.6.0） |
| GET | `/api/stats/admin/recovery` | Admin | 找回率（口径见 FR-STATS-ADMIN-02）（v3.6.0） |
| GET | `/api/stats/admin/publish-trend` | Admin | 发布趋势（`?days=30`，北京时间口径）（v3.6.0） |
| GET | `/api/stats/admin/category-pie` | Admin | 分类占比（v3.6.0） |

> ⚠️ **v3.3 变更**：移除累计活跃数据。`total_claimed` 替代 `today_claimed`，统计 `status='claimed'` 的物品总数（由 `stats_counters` 持久化计数器提供）。
>
> ⚠️ **勘误（v3.4.0 复核）**：接口仍返回 `categories`（分类占比），前端首页以 ECharts 饼图渲染——早期"移除分类占比"的表述与代码不符。

### 5.6 公告接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/announcements` | ✅ | 获取公告列表（公开仅 `published`；管理员 `all=true` 可见全量含草稿） |
| POST | `/api/announcements` | Admin | 新建公告（可存草稿） |
| PUT | `/api/announcements/{id}` | Admin | 编辑公告 |
| PUT | `/api/announcements/{id}/publish` | Admin | 发布（draft → published）（v3.6.0） |
| PUT | `/api/announcements/{id}/unpublish` | Admin | 下架（published → draft）（v3.6.0） |
| DELETE | `/api/announcements/{id}` | Admin | 删除公告 |

### 5.7 认领接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| POST | `/api/claims/proof-upload` | ✅ | 证明图上传（`proof_` 持久前缀，独立于 temp_ 清理） |
| POST | `/api/claims` | ✅ | 提交认领申请（特征描述必填；防冒领 / 防重复校验） |
| GET | `/api/claims/mine` / `received` | ✅ | 我的申请 / 收到的申请（分页） |
| GET | `/api/claims/status/{item_id}` | ✅ | 详情页按钮态 |
| GET | `/api/claims/{id}` | ✅ | 申请详情（三方可见；通过后对申请人返回**完整**联系方式） |
| POST | `/api/claims/{id}/approve` | ✅ | 同意（同事务互斥 + 物品转 claiming） |
| POST | `/api/claims/{id}/reject` | ✅ | 拒绝（`review_remark` 必填） |
| POST | `/api/claims/{id}/complete` | ✅ | 确认完成（物品转 claimed + 计数器 +1） |
| POST | `/api/claims/{id}/cancel` | ✅ | 申请人撤销（仅待审核态） |

### 5.8 举报接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| POST | `/api/reports` | ✅ | 提交举报（type 1-5、reason 必填；pending 去重） |
| GET | `/api/reports/mine` | ✅ | 我的举报（进度） |
| GET | `/api/reports/admin` | Admin | 管理端列表（筛选 + pending 优先） |
| GET | `/api/reports/admin/{id}` | Admin | 并排详情（举报 + 物品快照） |
| PUT | `/api/reports/admin/{id}/handle` | Admin | 处理（结论必填 + 处理人/时间 + 通知举报人） |

### 5.9 留言接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/comments/item/{item_id}` | ❌ | 留言列表（仅正常态，扁平结构） |
| POST | `/api/comments` | ✅ | 发表 / 回复（≤500 字） |
| DELETE | `/api/comments/{id}` | ✅ | 删除（本人/admin；**父留言级联删回复**） |
| PUT | `/api/comments/admin/{id}/status` | Admin | 隐藏 / 恢复 |
| GET | `/api/comments/admin` | Admin | 管理端列表 |

### 5.10 轮播图与分类接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:--:|------|
| GET | `/api/banners` | ❌ | 启用中的轮播图（sort_no 升序） |
| POST | `/api/banners/upload` | Admin | 图片上传（`banner_` 前缀） |
| GET / POST | `/api/banners/admin` | Admin | 列表 / 新建 |
| PUT / DELETE | `/api/banners/admin/{id}` | Admin | 编辑 / 删除 |
| GET / POST | `/api/categories/admin` | Admin | 分类列表（含 item_count）/ 新建 |
| PUT / DELETE | `/api/categories/admin/{id}` | Admin | 编辑 / 删除（**被物品使用 → 400**） |

### 5.11 错误响应格式

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
| image_path | TEXT | | 图片路径（v3.6.0 起与封面同步） |
| cover_image | TEXT | | 封面文件名（= images[0]，**仅封面参与向量检索**）（v3.6.0） |
| images | TEXT | | 有序图片文件名 JSON 数组（1-3 张）（v3.6.0） |
| is_recommend | INTEGER | DEFAULT 0 | 首页推荐位标记（v3.6.0） |
| image_vector | TEXT | | CLIP 图像特征 (JSON)；维度随后端（`cn_clip` 1024 / `open_clip` 512） |
| text_vector | TEXT | | CLIP 文本特征 (JSON)；维度随后端（`cn_clip` 1024 / `open_clip` 512） |
| contact | TEXT | | 联系方式 |
| location | TEXT | | 地点 |
| status | TEXT | CHECK(7 states) | pending/active/**claiming**/claimed/done/rejected/closed（claiming 为 v3.6.0 新增「认领中」，经表重建迁移） |
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

### 6.6 类别（v3.6.0 表驱动）

```
categories 表（种子 7 类：电子产品 / 证件卡片 / 包袋箱包 / 书籍文具 / 服装配饰 / 钥匙门禁 / 其他）
空表时 GET /api/items/categories 回退常量 CATEGORIES（同 7 项），响应结构不变
```

### 6.7 新增表组（v3.6.0）

| 表 | 关键字段 | 说明 |
|----|---------|------|
| claims | id, item_id, claimer_id, claim_reason, feature_description, proof_image, contact_phone, status(0待审核/1已通过/2已拒绝/3已完成/4已撤销), review_remark, reviewed_at, completed_at | 认领申请；索引 `(item_id,status)`、`(claimer_id,status)` |
| reports | id, item_id, reporter_id, report_type(1-5), report_reason, report_image, handle_status(0待处理/1已处理/2已驳回), handle_result, handler_id, handle_time | 举报 + 处理留痕；索引 `(handle_status,created_at)`、`(item_id)` |
| comments | id, item_id, user_id, parent_id(楼中楼), content, status(1正常/0隐藏) | 留言；索引 `(item_id,status,created_at)` |
| banners | id, title, image_path, description, link_url, sort_no, status(1启用/0停用) | 轮播图（sort_no 升序） |
| categories | id, name UNIQUE, sort_no | 分类表（使用中拒绝删除） |
| announcements（改） | + status(draft/published) | v3.6.0 加列 |
| items（改） | + cover_image / images(JSON) / is_recommend；status 枚举 + claiming | v3.6.0 加列 + 表重建 |

---

## 7. 前端页面需求

### 7.1 页面清单

| 路由 | 组件 | 布局 | 权限 | 关键功能 |
|------|------|:--:|------|------|
| `/login` | LoginView | 独立(毛玻璃) | 未登录 | 校园航拍背景 + 半透明卡片 + 登录后按角色自动跳转 |
| `/register` | RegisterView | 独立(毛玻璃) | 未登录 | 注册表单(用户名/密码/手机/邮箱) |
| `/items` | HomeView | DefaultLayout | 登录 | 轮播图 + 公告栏 + 统计看板(4卡片+饼图) + 筛选栏 + 卡片网格 + 「为你推荐」+ 骨架屏 + 分页 |
| `/items/:id` | ItemDetailView | DefaultLayout | 登录 | 多图画廊 + 留言区(楼中楼) + 相似推荐 + 认领闭环操作区(申请/审批/完整联系方式) + 举报入口 + 编辑/删除 |
| `/publish` | PublishView | DefaultLayout | 登录 | 表单卡片 + 多图上传(1-3 张, 拖拽排序, 首图封面) + 编辑模式(`?edit=`) |
| `/match` | MatchView | DefaultLayout | 登录 | 匹配面板 + 多图上传 + 证据徽章/依据 + 相似度进度条 |
| `/claims` | ClaimsView | DefaultLayout | 登录 | 双 tab（我的申请/收到的申请）+ 同意(互斥提示)/拒绝(必填理由)/确认完成/撤销 |
| `/reports/mine` | MyReportsView | DefaultLayout | 登录 | 举报进度卡片 |
| `/admin` | AdminView | DefaultLayout | 管理员 | 物品审核(批量+设推荐) + 用户管理 + 公告(草稿/发布) + 举报/留言/轮播图/分类管理 |
| `/admin/stats` | AdminStatsView | DefaultLayout | 管理员 | 指标卡 + 找回率仪表盘 + 发布趋势 + 分类占比（含表格视图） |
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

### 8.2 加权相似度融合（三检索模式 + 主辅证据 + 五阶段）

```
按查询形态三种检索模式（缺通道动态归一化自动成形，零分支代码）：
  ① 文字检索 → 文-文 0.75（主） + 跨模态 0.25（辅）
  ② 图片检索 → 图-图 0.75（主） + 跨模态 0.25（辅）
  ③ 图文混合 → 图-图 0.43 + 文-文 0.43 + 跨模态(双向) 0.14

通道（q=查询, t=目标）:
  sim_img_img = q_img·t_img;  sim_text_text = q_text·t_text
  sim_cross_t2i = q_text·t_img;  sim_cross_i2t = q_img·t_text
  sim_cross = 可用跨模态方向加权平均（内权重 0.5/0.5）
  sim_cross_mapped = clip((sim_cross−0.194)/(0.298−0.194), 0, 1)   ← 跨模态尺度映射

阶段1 基础加权: Sim = Σ(wᵢ·simᵢ)/Σ(wᵢ)（主证据 0.75 / 辅助证据 0.25；缺失通道动态归一化；全缺 → 0.0）
阶段2 类别/位置调节: 同类 +5% / 异类 -8%；同地点 +3% / 异地 -4%
阶段3 时间衰减: 240 天线性衰减至下限 60%（2026-09-21 调温和，原 90天/20%）
阶段4 分层阈值: 手动 0.624956 / 自动 0.733952 / 邮件 0.832069（2026-09-21 标定，内容分尺度）
阶段5 跨模态一致性惩罚: 仅当「文-文 ≥ 0.55 且图-图不高」触发（真·文本撞车）；
              cc = min(可用跨模态方向)；只降权、对 cc 单调，因子 ∈ [0.5, 1.0]；CROSS_PENALTY_ENABLED 可关闭

三分数分离: content_score（阈值判定，与标定同尺度）/ match_score（排序，含衰减）/ reference_score（展示，最强证据通道）
证据链: level（confirmed/high_suspect/related/reference）+ basis（命中依据）+ channels（各通道原始值）；
  basis 每条依据须通过各自阈值（图-图/文-文 0.606、跨模态映射后 0.513；2026-10-15 起，图-图通道「存在但低」不再进依据）
```

> ⚠️ **颜色通道已于 2026-10-16 整体移除**（2026-09-16 起已不参与打分）：无颜色向量列、无颜色计算代码。
>
> ✅ **三档阈值已标定成功**（2026-09-21 打分口径重构后，扭转此前「AUTO/EMAIL 结构性无解」）；样本量仍小，建议灰度观察（`EMAIL` 召回 19.4%）。旧「阶段5 交叉验证（图文矛盾降权 50%~75%）」已被真跨模态惩罚取代。

### 8.3 自动匹配流程

```
管理员审核通过
  → 若 AUTO_MATCH_ENABLED=false 短路
  → BackgroundTasks.add_task(auto_match_and_notify)
  → 查询异类活跃物品 (type相反, status=active, review_status=approved)
  → 维度预检：库向量维度 ≠ 当前模型维度 → 记 ERROR 并跳过
  → 逐对调用 compute_match_detail（三检索模式 + 五阶段）
  → 判定用 content_score ≥ 0.733952（MATCH_THRESHOLD_AUTO，与标定同尺度）
  → 按 match_score 降序，Top-3 落库
  → 双向站内通知（含匹配等级 + 命中依据）
  → content_score ≥ 0.832069（MATCH_THRESHOLD_EMAIL）且有邮箱 → HTML 邮件（含等级与依据）
```

### 8.4 认领/归还语义规则

| 物品类型 | 操作者视角 | 操作 | 系统行为 |
|---------|-----------|---------|---------|
| lost | 非发布者(捡到者) | "我要归还" | 创建 claims 记录（特征描述 + 证明图），通知发布者审批 |
| found | 非发布者(失主) | "我要认领" | 同上 |
| 任一 | 发布者 | 同意 | claim → 1，同物品其他待审**自动拒绝**（互斥），物品 → `claiming`；申请人可见**完整**联系方式 |
| 任一 | 发布者 | 拒绝（理由必填）/ 申请人撤销 | claim → 2 / 4；物品保持 active |
| 任一 | 发布者 | 确认完成 | claim → 3，物品 → `claimed`，总计找回 +1 |
| 任一 | 发布者 | "标记已找回/已认领"（快捷） | 物品 → claimed；若存在已通过申请则联动置 3（**不重复计数**） |

> ⚠️ **v3.3 变更**：删除发布者"确认/拒绝"两步流程（原 `PUT /api/items/{id}/claim/confirm`），改为发布者**自行标记**（`PUT /api/items/{id}/mark-claimed`）。
>
> **v3.6.0**：认领升级为**审批制闭环**（claims 表 + 互斥 + 联系方式分级可见 + 撤销）；`mark-claimed` 保留为快捷入口（联动已通过申请，计数器不重复计数）。

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
| 多图（v3.6.0） | 每个物品支持 1-3 张图片，**仅封面参与向量检索** |
| 用户自行联系 | 认领通过后申请人经完整联系方式线下沟通取回；发布者确认完成 |

### 9.3 已知限制

| 限制 | 影响 | 建议 |
|------|------|------|
| SQLite 写锁 | 并发写入 > 20 时性能下降 | 迁移 PostgreSQL |
| JSON 向量存储 | 全表扫描计算相似度 | 引入 pgvector ANN 索引 |
| 无 WebSocket | 通知非实时 | 引入 WebSocket 推送 |
| 无草稿箱 UI | 驳回物品无独立管理入口 | 在发布页增加草稿列表 |
| ~~真实 Chinese-CLIP 权重未下载验证~~ ✅ 已下载并端到端验证 | 权重 3.83GB 已在**本机**下载（ModelScope 源，`CLIP_CN_CKPT_PATH` 零网络加载）并验证：1024 维 + L2 归一 + 语义合理 + 真实 Recall@K | 已闭环（`scripts/verify_real_clip.py`；`RUN_REAL_CLIP=1` 冒烟 2 用例由 skip 转通过） |
| ~~分层阈值 AUTO/EMAIL 不可用~~ ✅ **2026-09-21 首次标定成功** | 打分口径重构（三检索模式 + 尺度映射）后：`AUTO`=0.733952（P=91.7% / R=61.1%）、`EMAIL`=0.832069（P=100% / R=19.4%） | ⚠️ 样本量仍小（EMAIL 处仅 7 个正样本）；建议灰度观察；随数据增长持续复标 |
| **权重的「最优值」证据不足** | 2026-09-21 起「主证据 0.75 / 辅助证据 0.25」含明确语义，不再依赖网格搜索 | `--grid` 保留三维网格供探索 |
| ~~两代向量空间不兼容~~ ✅ 本库已完成重嵌入（2026-09-14） | 切模型未重嵌入则新旧向量不可比（已加维度防线 → HTTP 500） | 已执行 `reembed_all_vectors.py` 全量重嵌入（冷备 + 守卫，6 条全部 1024 维）；`/match` 实测恢复 HTTP 200 |
| **评测集规模小** | `eval_set_v3.5.0.json` **84 对**（有效 **36 正 / 42 负**，n=78），置信区间仍宽 | 随数据增长扩充复标；不得表述为「已可靠标定」 |

---

> **文档维护者**：开发团队 | **最后更新**：2026-10-16 | **基于源码版本**：v3.6.0
>
> **v3.4.0 核心变更摘要**：账户状态语义拆分（C2：`role` 收敛为 user/admin，新增 `status`） | 公开接口账号状态校验（C1：`resolve_optional_viewer`） | 颜色特征持久化（R4：`items.color_vector`） | 邮件异步化（R5）| 路由 `:int` 健壮化（R6）| 去静默异常（R7）| 请求体 Pydantic 化（R9）| 依赖与版本清理（R10）| 自动化测试 70 用例全通过
>
> **v3.4.1 补齐**：`POST /api/items/match` 鉴权（缺 token → 403 / 非法 token → 401）| 自动化测试扩至 **72 用例**全通过
>
> **v3.5.0 中文化模型 + 跨模态检索**：新增 `app/clip_backend.py` 双后端抽象（默认 `cn_clip` Chinese-CLIP ViT-H-14 **1024 维** / 回滚 `open_clip` ViT-B-32 **512 维**，未知值抛 `RuntimeError`）| 启用 img·text **跨模态四通道**打分（图-图 0.35 / 跨模态 0.35 / 文-文 0.15 / 色 0.15）| 阶段5 升级为**真跨模态一致性惩罚**（`cc=min(可用跨模态方向)`，≥0.55 触发，只降权 ≤×0.5，可开关）| 阈值重设（手动 0.35 / 自动 0.55 / 邮件 0.70，初值）| `/match` 新增 `match_source` + `legend`（**403/401 契约冻结不变，不新增端点**）| 新增三脚本（`reembed_all_vectors.py` / `calibrate_thresholds.py` / `backfill_color_vectors.py`）| 评测集 **84 对**（42 正 / 42 负，有效 36 正 / 42 负 n=78）| 维度错配运行期防线（编码断言 + 打分前预检 → HTTP 500）| 自动化测试扩至 **209 用例（207 通过 / 2 门控跳过）**。⚠️ **真实权重已下载并端到端验证（真实 `Recall@3 = 1.0` / `Recall@1 = 0.7917`）；但分层阈值仍不可用** —— 评测集扩充轮（84 对，n=78）复标后 Precision 上界仅 0.6889，`AUTO`/`EMAIL` **结构性无解**（详见 `docs/review/threshold-calibration-v3.5.0.md` §5）。✅ **生产库已完成全量重嵌入（2026-09-14，冷备 + `_exit_code` 守卫，6 条全部 1024 维）**，`/match` 实测恢复 HTTP 200（后续于 v3.6.0 完成阈值标定并开启自动推送，见下）
>
> **v3.6.0 打分口径重构 + 社区化融合**：按查询形态**三种检索模式**（文字/图片/图文混合）| 权重「主证据 0.75 + 辅助证据 0.25」| 跨模态尺度映射（0.194→0.298）| 证据链 + 三分数分离（`content_score` 判定 / `match_score` 排序 / `reference_score` 展示）| 时间衰减失效修复并调温和（240 天 / 0.6）| **三档阈值首次标定成功**（MANUAL 0.624956 / AUTO 0.733952 / EMAIL 0.832069，内容分尺度）| 自动匹配尺度修正（判定改 `content_score`）| 新增 5 表（claims / reports / comments / banners / categories）+ items 3 列（cover_image / images / is_recommend）+ status 枚举新增 `claiming`（表重建迁移）| 认领闭环 / 举报 / 留言 / 多图 / 管理端统计看板 / 相似推荐 / 内容运营 上线 | 自动化测试 **313 用例（311 通过 / 2 门控跳过）**
