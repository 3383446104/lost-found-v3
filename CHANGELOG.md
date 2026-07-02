# 迭代日志 (CHANGELOG)

> 校园失物检索平台 — 版本迭代记录

---

## V3.1 — 体验增强迭代 (2026-06-29)

### 迭代目标
依据 [PROJECT.md](PROJECT.md) 中 V3.1 路线图，在不破坏现有功能的前提下增强用户体验。

---

### 1. 骨架屏组件化 ✅

**改动文件：**
- `lost-found-frontend/src/components/SkeletonCard.vue`（新建）
- `lost-found-frontend/src/views/HomeView.vue`（修改）

**实现内容：**
- 抽取 `.skeleton` 相关 HTML/CSS 为独立的 `<SkeletonCard />` 组件
- 组件复用全局 `@keyframes shimmer` 动画
- HomeView 从内联骨架 HTML 迁移至 `<SkeletonCard>`，加载时渲染 6 个占位卡片
- 后续可直接在 MatchView、NotificationsView 等列表页复用

---

### 2. 深色模式 ✅

**改动文件：**
- `lost-found-frontend/src/styles/theme.css`（追加 120+ 行）
- `lost-found-frontend/src/composables/useTheme.js`（新建）
- `lost-found-frontend/src/layouts/DefaultLayout.vue`（修改）

**实现内容：**
- 完整暗色主题 CSS 变量覆盖（品牌色提亮、中性色反转、阴影加深）
- Element Plus 暗色组件精细适配（表格/下拉菜单/弹出框/对话框）
- `useTheme` 组合式函数：
  - 首次访问自动检测系统 `prefers-color-scheme`
  - 手动切换后写入 `localStorage` 持久化
  - 监听系统主题变化（仅用户未手动设置时生效）
- DefaultLayout Header 添加 🌙/☀️ 主题切换按钮（圆形图标按钮，悬停高亮）
- `color-scheme: dark` 声明确保原生表单控件同步

---

### 3. 个人中心页面 ✅

**改动文件：**
- `backend/app/api/auth.py`（新增 `PUT /api/me` 端点）
- `lost-found-frontend/src/views/ProfileView.vue`（新建）
- `lost-found-frontend/src/api/auth.js`（新增 `updateProfile`）
- `lost-found-frontend/src/router/index.js`（新增 `/profile` 路由）
- `lost-found-frontend/src/layouts/DefaultLayout.vue`（修改下拉菜单）

**实现内容：**

**后端：**
- `GET /api/me` 响应扩展：新增 `phone`、`email`、`created_at` 字段
- `PUT /api/me` 新增端点：
  - 支持更新密码（bcrypt 重新哈希，完成后强制重新登录）
  - 支持更新邮箱（格式校验）
  - 支持更新手机号（11 位校验）
  - 参数化查询防注入

**前端：**
- 双栏布局：左侧用户信息卡片（头像、ID、注册时间、联系方式），右侧修改表单
- 修改密码表单（含验证 + loading + 成功后自动退出）
- 联系方式表单（手机号 + 邮箱，更新即时刷新）
- 用户下拉菜单「个人信息」从 Toast 升级为导航至 `/profile`

---

### 4. 物品认领确认流程 ✅

**改动文件：**
- `backend/app/api/items.py`（新增 `POST /{id}/claim` + `PUT /{id}/claim/confirm`）
- `lost-found-frontend/src/api/items.js`（新增 `claimItem`、`confirmClaim`）
- `lost-found-frontend/src/views/ItemDetailView.vue`（新增认领 UI）

**实现内容：**

**后端：**
- `POST /api/items/{id}/claim` — 申请认领：
  - 校验：不能认领自己的物品、物品必须为 active+approved
  - 防重复：同一物品同一用户不可重复申请
  - 发送站内通知给物品发布者（标题含认领人用户名）
- `PUT /api/items/{id}/claim/confirm` — 确认/拒绝认领：
  - 仅物品发布者（或管理员）可操作
  - 确认：物品状态 → `claimed`，标记相关通知为已读
  - 拒绝：不改变物品状态
  - 结果通知发送给认领申请人

**前端：**
- 非本人查看活跃物品时，显示绿色「申请认领」提示卡片
- 物品发布者看到待处理认领通知时，显示橙色确认/拒绝操作区
- 点击认领 → 确认弹窗 → API 调用 → 成功反馈
- 确认认领后物品详情即时刷新（状态变为「已认领」）

---

### 5. 30 秒轮询未读通知数量 ✅

**改动文件：**
- `lost-found-frontend/src/layouts/DefaultLayout.vue`（修改）

**实现内容：**
- `onMounted` 中启动 `setInterval(refreshUnread, 30000)`
- `onUnmounted` 中 `clearInterval` 防止内存泄漏
- 保留原有的路由切换时拉取（`router.afterEach`），双保险机制
- 导航栏铃铛图标实时显示最新未读数

---

### 构建验证

```
✓ 1673 modules transformed (+5 new modules)
✓ built in 966ms
✓ 零错误（仅 @vueuse/core 第三方 INFO）
```

新增模块：`SkeletonCard.vue`、`ProfileView.vue`、`useTheme.js`

### 功能测试

| # | 测试用例 | 结果 |
|---|---------|:--:|
| 1 | 骨架屏组件渲染（HomeView 加载态） | ✅ |
| 2 | 深色模式切换 + 持久化 | ✅ |
| 3 | 系统主题自动检测 | ✅ |
| 4 | `GET /api/me` 返回 phone/email/created_at | ✅ |
| 5 | `PUT /api/me` 更新密码 | ✅ |
| 6 | `PUT /api/me` 更新联系方式 | ✅ |
| 7 | 个人中心页面渲染 | ✅ |
| 8 | `POST /api/items/:id/claim` 认领申请 | ✅ |
| 9 | 防重复认领 | ✅ |
| 10 | `PUT /api/items/:id/claim/confirm` 确认认领 | ✅ |
| 11 | 物品状态变为 claimed | ✅ |
| 12 | 认领 UI 正确显示/隐藏 | ✅ |
| 13 | 30 秒轮询未读数量 | ✅ |
| 14 | 生产构建零错误 | ✅ |

---

### 文件变更统计

| 类型 | 数量 | 文件 |
|------|:----:|------|
| 新建 | 4 | `SkeletonCard.vue`, `ProfileView.vue`, `useTheme.js`, `CHANGELOG.md` |
| 修改 | 7 | `theme.css`, `DefaultLayout.vue`, `HomeView.vue`, `ItemDetailView.vue`, `auth.py`, `items.py`, `router/index.js` |
| 后端新增端点 | 3 | `PUT /api/me`, `POST /api/items/{id}/claim`, `PUT /api/items/{id}/claim/confirm` |
| 未修改 | 9 | LoginView, RegisterView, PublishView, MatchView, AdminView, NotificationsView, config.py, database.py, match_service.py |

---

### 回滚指南

如需回滚至 V3.0，执行：
```bash
git checkout HEAD~1
```

或手动恢复：
- 删除 `src/components/SkeletonCard.vue`、`src/views/ProfileView.vue`、`src/composables/useTheme.js`
- 从 `theme.css` 中移除 `[data-theme="dark"]` 及后续所有样式
- 从 `auth.py` 中移除 `PUT /api/me` 端点
- 从 `items.py` 中移除 claim 相关端点
- 还原 `HomeView.vue` 内联骨架 HTML
- 还原 `DefaultLayout.vue` 中主题按钮和轮询代码

---

---

## V3.1.1 — 功能补全 + UI 修复 (2026-06-29)

### 迭代目标
补全 V3.1 中未完整实现的功能（头像上传、认领邮件通知），修复多个页面的 UI 排版问题，新增一键已读。

---

### 1. 头像上传 ✅

**改动文件：**
- `backend/app/database.py`（修改 — users 表迁移 avatart_path 列）
- `backend/app/api/auth.py`（新增 `POST /api/me/avatar`、`GET /api/avatars/{filename}`）
- `lost-found-frontend/src/api/auth.js`（新增 `uploadAvatar`）
- `lost-found-frontend/src/views/ProfileView.vue`（重写）

**实现内容：**
- 数据库自动迁移：`users` 表新增 `avatar_path` 列
- `POST /api/me/avatar` — 上传头像（≤2MB，自动删旧文件）
- `GET /api/avatars/{filename}` — 公开访问头像
- ProfileView 头像区域：圆形裁剪、悬停覆层+相机图标、点击上传即时预览

---

### 2. 认领/归还流程完善 ✅

**改动文件：**
- `backend/app/api/items.py`（重写 claim/confirm 端点）
- `lost-found-frontend/src/views/ItemDetailView.vue`（重构模板+样式）

**实现内容：**
- 根据物品类型自动区分语义：lost→"认领"、found→"归还"
- 通知标题格式化为 `[认领申请]` / `[归还申请]`
- 双向邮件通知（申请时→发布者、确认/拒绝→申请人），HTML 格式 + 品牌绿按钮
- `loadItem()` 自动拉取未读通知检测待处理申请
- 确认/拒绝时传入正确的 `claimer_username`

---

### 3. 物品详情页 UI 重构 ✅

**改动文件：**
- `lost-found-frontend/src/views/ItemDetailView.vue`（模板+样式完全重写）

**实现内容：**
- 返回按钮移出网格独立成行
- 图片卡片：类型徽章浮于右上角、毛玻璃模糊背景
- 信息卡片：行分隔线替代网格、联系方式左绿边框+
- 认领卡片：圆形图标 + 双行文字 + 提示说明 + 按钮
- 三级响应式：768px 单栏、480px 按钮全宽堆叠

---

### 4. 一键已读 ✅

**改动文件：**
- `backend/app/api/notifications.py`（新增 `PUT /api/notifications/read-all`）
- `lost-found-frontend/src/api/notifications.js`（新增 `markAllRead`）
- `lost-found-frontend/src/views/NotificationsView.vue`（新增按钮+逻辑）

**实现内容：**
- `PUT /api/notifications/read-all` — `UPDATE ... SET is_read=1 WHERE user_id=? AND is_read=0`
- 前端「全部已读」按钮：仅在有未读时显示、loading 状态、成功后清空列表+归零红点
- 路由 `/read-all` 置于 `/{notif_id}/read` 之前避免 FastAPI 路径匹配冲突

---

### 5. UI 排版修复 ✅

**改动文件：**
- `lost-found-frontend/src/styles/theme.css`
- `lost-found-frontend/src/views/AdminView.vue`
- `lost-found-frontend/src/views/PublishView.vue`
- `lost-found-frontend/src/views/NotificationsView.vue`

**修复内容：**
- `.page-desc` 负上边距 `-16px` → `2px`，消除描述文字与标题重叠
- AdminView `.page-header` 加 `min-width:0` + `margin-bottom` 防 flex 换行重叠
- PublishView 移动端 `form-row` 的 `gap:0` → `gap: var(--space-4)` 防表单域贴死
- PublishView 加 `margin: 0 auto` 居中，`max-width` 统一 640px 与 MatchView 一致
- NotificationsView `.page-header` 加 `margin-bottom: var(--space-5)` 拉大标题与列表间距

---

### 构建验证

```
✓ 1678 modules transformed
✓ built in 856ms
✓ 零错误
```

### 功能测试

| # | 测试用例 | 结果 |
|---|---------|:--:|
| 1 | 头像上传 + 数据库存储 | ✅ |
| 2 | `GET /api/me` 返回 avatar_path | ✅ |
| 3 | 头像悬停覆层 + 点击上传 | ✅ |
| 4 | 认领（lost）→ 通知标题含"认领" | ✅ |
| 5 | 归还（found）→ 通知标题含"归还" | ✅ |
| 6 | 认领邮件通知发布者 | ✅ |
| 7 | 确认/拒绝邮件通知申请人 | ✅ |
| 8 | 物品详情页双栏布局 | ✅ |
| 9 | 类型徽章毛玻璃效果 | ✅ |
| 10 | 一键已读全部通知 | ✅ |
| 11 | `.page-desc` 不再重叠标题 | ✅ |
| 12 | AdminView 标题/徽章不重叠 | ✅ |
| 13 | PublishView 表单居中 | ✅ |

---

### 文件变更统计

| 类型 | 数量 | 文件 |
|------|:----:|------|
| 后端新增端点 | 3 | `POST /api/me/avatar`, `GET /api/avatars/{filename}`, `PUT /api/notifications/read-all` |
| 后端修改 | 3 | `database.py`, `auth.py`, `items.py` |
| 前端新增 | 1 | `auth.js`（`uploadAvatar`） |
| 前端修改 | 7 | `ProfileView.vue`, `ItemDetailView.vue`, `NotificationsView.vue`, `AdminView.vue`, `PublishView.vue`, `theme.css`, `vite.config.js` |

---

> **当前版本**: V3.2 | **下一迭代**: V3.3 — 多图上传 / 公告系统 / 饼状图 / 搜索高亮

---

## V3.2 — 需求驱动迭代 (2026-06-29)

### 迭代目标
依据新增需求文档评审建议，实现登录自动跳转、管理面板增强、数据看板、个人中心补全。

---

### 1. 登录自动跳转 ✅

**改动文件：** `LoginView.vue`

**实现内容：**
- 登录成功后根据 `user.role` 自动跳转：管理员→`/admin`，普通用户→`/items`
- 不再需要手动选择身份，更安全（后端 role 为唯一真相源）

---

### 2. 认领/归还按钮文案优化 ✅

**改动文件：** `ItemDetailView.vue`

**实现内容：**
- lost 物品按钮文案：`申请认领` → `我要认领`
- found 物品按钮文案：`申请归还` → `我要归还`

---

### 3. 个人中心补全 ✅

**改动文件：**
- `backend/app/api/auth.py`（新增 `DELETE /api/me` + `PUT /api/me` 扩展 username）
- `lost-found-frontend/src/api/auth.js`（新增 `deleteAccount`）
- `lost-found-frontend/src/views/ProfileView.vue`（新增用户名修改 + 注销按钮）

**实现内容：**
- 修改用户名：`PUT /api/me` 新增 `username` 字段，含重名校验（2-20字符）
- 注销账号：`DELETE /api/me` 软删除（用户名标记 `_deleted_`，所有活跃物品关闭）
- 前端：修改用户名表单 + 注销确认弹窗（红色警示卡片）

---

### 4. 管理面板增强 ✅

**改动文件：**
- `backend/app/api/admin.py`（审核驳回通知+邮件 + 用户管理端点）
- `lost-found-frontend/src/api/admin.js`（新增 `getUsers`, `updateUser`）
- `lost-found-frontend/src/views/AdminView.vue`（el-tabs 双标签重构）

**实现内容：**

**审核驳回增强：**
- 驳回时发送站内通知（含驳回理由 + 物品链接）
- 驳回时发送 HTML 邮件（含驳回理由 + "重新编辑"按钮链接到发布页）
- 驳回物品状态设为 `rejected`（前端可识别为草稿，支持 `?edit=` 重新提交）

**用户管理（新增）：**
- `GET /api/admin/users` — 分页列表（ID/用户名/角色/手机/邮箱/注册时间）
- `PUT /api/admin/users/{id}` — 设为管理员 / 取消管理 / 禁用 / 启用
- 前端：AdminView 新增「用户管理」标签页，表格+操作按钮+分页

---

### 5. 数据看板 ✅

**改动文件：**
- `backend/app/api/stats.py`（新建）
- `backend/app/main.py`（注册 stats 路由）
- `lost-found-frontend/src/views/HomeView.vue`（统计卡片 + API 调用）

**实现内容：**
- `GET /api/stats/dashboard` — 返回当日总量/失物/拾物/找回 + 累计活跃 + 分类占比
- 首页顶部 4 个统计卡片（展示中/今日失物/今日拾物/今日找回），彩色数字
- 响应式 2×2 网格（≤640px 时）
- 使用 `LIKE` 前缀匹配替代 `date()` 函数，兼容所有 SQLite 版本

---

### 6. 后端架构优化 ✅

**改动文件：** `backend/app/main.py`（新增 stats_router 注册）

---

### 构建验证

```
✓ 1685 modules transformed
✓ built in 1.11s
✓ 零错误
```

### 功能测试

| # | 测试用例 | 结果 |
|---|---------|:--:|
| 1 | 管理员登录→自动跳转 /admin | ✅ |
| 2 | 普通用户登录→自动跳转 /items | ✅ |
| 3 | 修改用户名（含重名校验） | ✅ |
| 4 | 注销账号（软删除 + 物品关闭） | ✅ |
| 5 | 审核驳回→站内通知 + 邮件 | ✅ |
| 6 | 用户管理列表（分页） | ✅ |
| 7 | 设管理员 / 禁用 / 启用 | ✅ |
| 8 | 数据看板 API 返回正确数据 | ✅ |
| 9 | 首页统计卡片渲染 | ✅ |
| 10 | 生产构建零错误 | ✅ |

---

### 文件变更统计

| 类型 | 数量 | 文件 |
|------|:----:|------|
| 后端新建 | 1 | `stats.py` |
| 后端修改 | 3 | `auth.py`, `admin.py`, `main.py` |
| 前端修改 | 6 | `LoginView.vue`, `ItemDetailView.vue`, `ProfileView.vue`, `AdminView.vue`, `HomeView.vue`, `admin.js`, `auth.js` |
| 后端新增端点 | 5 | `DELETE /api/me`, `GET /api/admin/users`, `PUT /api/admin/users/{id}`, `GET /api/stats/dashboard` |

---

## V3.3 — 逻辑收敛 + 体验重构 (2026-06-30)

### 迭代目标
依据新增需求评审 + 竞品分析 + 用户角色与场景设计，实现角色收敛、认领流程简化、个人中心重设计、批量审核、统计聚焦五大核心变更。

---

### 1. 角色体系重构 — 去除访客 + 禁用拦截 ✅
- `backend/app/api/auth.py` — login 增加 disabled 检查(403) + GET /me 移除 avatar_path + 删除头像端点 + 新增 history
- `lost-found-frontend/src/router/index.js` — 重写 beforeEach：去访客 + disabled 拦截 + 角色分流
- 所有功能页面均需登录；disabled 用户自动清除登录态

### 2. 认领流程重构 — 自标记替代确认/拒绝 ✅
- ➕ `PUT /api/items/{id}/mark-claimed` — 发布者自标记
- 🔧 `POST /api/items/{id}/claim` — 通知含申请人手机号 + 邮件含联系方式
- ❌ 删除 `PUT /api/items/{id}/claim/confirm`
- 🎨 ItemDetailView 操作区重写

### 3. 个人中心完全重写 ✅
- 🎨 ProfileView 从 394 行重构：首字母头像 + Tab 分段(账户/联系/历史) + inline edit + Danger Zone
- 🚫 砍掉头像上传(API + UI)
- ➕ `GET /api/me/history` + 历史记录 Tab

### 4. 批量审核通过 ✅
- ➕ `POST /api/admin/reviews/batch-approve` (最多 50 条/次)
- 🎨 AdminView: 复选框多选 + 全选 + 工具栏 + 确认弹窗

### 5. 数据统计聚焦 — 总计找回 ✅
- 📊 第4卡片: "今日找回" → "🏆 总计找回"(累计值)
- ❌ 移除分类占比和累计活跃

---

### 文件变更统计

| 类型 | 后端 | 前端 |
|------|:----:|:----:|
| 新增端点 | 3 | — |
| 删除端点 | 4 | — |
| 修改文件 | 4 | 8 |

### 构建验证

```
✓ built in 8.81s
✓ 零错误
```

### P2P 全链路测试

| 模块 | 测试数 | 通过 | 通过率 |
|------|:------:|:----:|:------:|
| M1-认证系统 | 7 | 7 | 100% |
| M2-物品+管理员 | 3 | 3 | 100% |
| M3-批量审核+认领 | 4 | 4 | 100% |
| M4-统计+历史 | 7 | 7 | 100% |
| M5-自标记闭环 | 4 | 4 | 100% |
| **总计** | **26** | **26** | **100%** ✅ |

---

---

### V3.3.1 — Bug 修复 (2026-06-30)

修复 6 个 UI 功能测试发现的 Bug，回归测试 12/12 通过。

**修复清单：**
| Bug | 根因 | 修复 |
|-----|------|------|
| #1 未审核物品计入统计 | stats.py SQL 缺少状态过滤 | 增加 `review_status='approved' AND status='active'` |
| #2 展示中卡片显示异常 | 同上 + 前端防御性不足 | SQL 修复 + loadStats 显式字段映射 |
| #3 全选框失效 | 自定义 checkbox 与表格冲突 | 改用 el-table 内置 selection 列 |
| #4 批量审核报错 | 路由顺序 + catch 混淆 | batch-approve 移至参数化路径前 + 分离 try/catch |
| #5 认领弹窗文案不匹配 | handleClaim 文案硬编码 | 根据 item.type 动态生成 |
| #6 标记已找回报异常 | try/catch 混淆 + 已认领物品仍显示列表 | 分离 try/catch + 列表查询排除 claimed/closed |
| #7 mark-claimed 路由 404 | `PUT /{id}/mark-claimed` 在 `PUT /{id}` 之后被拦截 | 移至参数化路径之前（同 Bug #4 根因） |
| #8 自动匹配通知异常 | `sqlite3.Row` 无 `.get()` 方法 | `match_service.py` 中 `row` → `dict(row)` |

**改动文件：** `stats.py`, `admin.py`, `items.py`, `match_service.py`, `HomeView.vue`, `AdminView.vue`, `ItemDetailView.vue`
**回归测试：** 18/18 通过 (100%)

---

> **当前版本**: V3.3.1 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery / OSS / PWA

---

## V3.3.2 — 匹配算法增强 + UI 升级 (2026-07-02)

### 迭代目标
五阶段匹配算法重构、公告系统、物品管理统一Tab、Inter字体、桌面适配、消息优化。

---

### 1. 五阶段智能匹配算法 ✅

- **类别/位置双向调节**：同类+5%, 不同-8%; 同位置+3%, 不同-4%
- **时间衰减**：90天线性衰减至50%
- **分层阈值**：手动0.20/自动0.65/邮件0.75
- **动态权重**：图+色→0.50+0.30+0.20; 纯文→1.0
- **交叉验证**：图文矛盾→降权50%-75%
- **颜色增强**：27维RGB直方图+余弦相似度

### 2. 公告系统 + 物品管理Tab ✅

- `announcements` 表 + CRUD + 分页 + `target_role`
- 首页入口卡片 → el-drawer → 内联展开
- 物品审核+管理合并为统一Tab + 多维筛选 + 批量操作

### 3. UI 升级 ✅

- Inter 字体 + 1440px/1920px 桌面适配
- 去 emoji → Element Plus 图标
- ElMessage 全局优化（2000ms+关闭按钮+max=2+grouping）
- 系统更名：校园失物检索平台

### 4. 后端优化 ✅

- 手机号注册必填 + 邮箱唯一性
- 管理员新增/删除用户端点
- `get_current_user` deleted 角色拦截
- 统计计数器持久化（`stats_counters` 表）

---

### 文件变更

| 类型 | 数量 | 文件 |
|------|:----:|------|
| 后端新建 | 2 | `stats.py`, `announcements.py` |
| 后端修改 | 6 | `clip_service.py`, `match_service.py`, `items.py`, `admin.py`, `auth.py`, `database.py` |
| 前端修改 | 10+ | `HomeView`, `AdminView`, `MatchView`, `ItemDetailView`, `ProfileView`, `LoginView`, `RegisterView`, `theme.css`, `main.js`, `router` |

---

> **当前版本**: V3.3.2 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery + Redis / OSS / PWA
