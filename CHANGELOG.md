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

---

## V3.3.3 — 工程加固 + 文档对齐 (2026-09-12)

### 迭代目标
在交付答辩前的架构评审基础上，补齐仓库首个自动化回归测试套件，修复评审确认的 3 项 P0 缺陷，并将全部文档与代码对齐。

> 依据：[架构评审报告](docs/review/architecture-review-2026-09-12.md)（共识别 P0×3 / P1×4 / P2×4，本轮处理 P0 三项）。

### 1. 自动化测试套件（仓库首个）✅
- ➕ `backend/tests/`：pytest + FastAPI TestClient，**45 用例全绿**
  - `test_auth.py`(8) / `test_items.py`(14) / `test_admin.py`(7) / `test_stats.py`(4)
  - `test_adversarial_auth.py`(5) / `test_adversarial_stats.py`(4) / `test_adversarial_meta.py`(2) / `test_adversarial_admin_toggle.py`(1)
- ➕ `backend/pytest.ini`、`backend/requirements-dev.txt`（pytest / httpx）
- `conftest.py` 隔离方案：临时 DB 文件 + CLIP 假向量桩 + SMTP 阻断 + 上传目录重定向；**不加载 ~600MB 模型、不触网**
- 运行：`venv\Scripts\python.exe -m pytest tests/ -v`

### 2. P0 缺陷修复 ✅
| 编号 | 缺陷 | 修复 |
|------|------|------|
| R1 | 禁用用户已签发 JWT 仍可越权访问全部接口 | `dependencies/auth.py` 增补 `role=='disabled'` → 403 拦截 |
| R2 | 「今日失物/今日拾物」东八区 00:00–08:00 统计错位 | `api/stats.py` 改为北京时间当日的 UTC 半开区间范围比较 |
| R3 | `bcrypt` 未直接声明依赖（`passlib` 实际未使用） | `requirements.txt` 直接将 `passlib[bcrypt]` 替换为 `bcrypt==5.0.0` |

### 3. 文档与代码对齐 ✅
- `PROJECT.md`：§2 目录树 / §3.3 匹配权重与阈值 / §3.4 自动匹配阈值 / §3.6 轮询说明 / §4 补公告与计数表 / §5 补公告端点与端点总数 36 / §8.4 环境变量 / §9 算法公式 / §10 增自动化测试 / §11 版本演进
- `README.md`：移除已删除的 `POST /api/me/avatar`、补 `GET /api/me/history`、补迭代路线 V3.3.1–V3.3.3、新增「运行测试」
- 逐条对照见 [docs/review/doc-sync-2026-09-12.md](docs/review/doc-sync-2026-09-12.md)

### 文档勘误
- 早期 V3.3 条目记载「❌ 移除分类占比和累计活跃」，但**代码实际仍保留分类占比**（`api/stats.py` 仍返回 `categories`，`views/HomeView.vue` 仍用 ECharts 渲染饼图）。历史条目按惯例保留原文，此处注明其与现状不符。

> **当前版本**: V3.3.3 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery + Redis / OSS / PWA

---

## V3.4.0 — 语义与性能加固 (2026-09-12)

### 迭代目标
在架构评审（P0 三项已随 V3.3.3 修复）基础上，落地增量修复设计 [docs/review/design-fix-batch-2026-09-12.md](docs/review/design-fix-batch-2026-09-12.md) 中确认的 **C1 / C2 / R4 / R5 / R6 / R7 / R9 / R10 / O2** 整改项，重点是**账户状态语义拆分**、**颜色特征持久化**、**匹配性能与异步化**、**路由与契约健壮化**，并将回归测试扩充至 **70 用例**。

> 依据：[架构评审报告](docs/review/architecture-review-2026-09-12.md)、[增量修复设计](docs/review/design-fix-batch-2026-09-12.md)。本轮以**后端 schema / 语义 / 契约**为主，前端除路由守卫状态字段外无改动；文档同步见 [变更总结](docs/review/v3.4.0-change-summary-2026-09-12.md)。

### 1. 数据结构变更（S1）✅
| 变更 | 说明 |
|------|------|
| `users.status` 新增 | 账号状态 `active`/`disabled`/`deleted`；迁移在「加列」分支内完成旧值折算（`role='disabled'` → `status='disabled'` 且 `role='user'`；`role='deleted'` → `status='deleted'` 且 `role='user'`；其余 `active`） |
| `items.color_vector` 新增 | 27 维 RGB 颜色直方图（JSON），用于颜色相似度增强与跨请求复用 |
| 迁移方式 | `database.py:126-143` 幂等迁移（`PRAGMA table_info` 探测后按需 `ALTER TABLE ADD COLUMN`），可重复执行 |

### 2. 账户状态语义拆分（S2 / C2）✅
- `role` 收敛为 `user`/`admin`；禁用/注销迁移到 `status`
- `PUT /api/admin/users/{id}` 的 `toggle_status` **只翻转 `status`、保留 `role`**
- 登录（`api/auth.py`）按 `status` 分流：`disabled` → 403「账号已被禁用，请联系管理员」；`deleted` → 403「账号已注销」
- 前端路由守卫判定字段由 `role==='disabled'` 改为 `status==='disabled'`

### 3. 公开接口账号状态校验（C1）✅
- 新增 `resolve_optional_viewer(request)`：公开接口对携带 token 的禁用/注销用户**降级为匿名**（返回公开内容而非 403）
- 应用于 `GET /api/items/`、`GET /api/items/{id}`

### 4. 匹配性能与异步（S3 / R4 / R5）✅
- **R4** 颜色特征持久化到 `items.color_vector`：发布/换图时计算，匹配时优先读取、缺失时回退现算
- **R5** 邮件与自动匹配通知改为 `BackgroundTasks` 异步投递，避免阻塞请求

### 5. 路由 / 契约 / 健壮化（S4 / R6 / R7 / R9）✅
- **R6** 物品路由改用 Starlette `{item_id:int}` 路径转换器，消除 `/{id}` 与其子路径的匹配顺序问题
- **R7** 去除静默吞异常，关键路径显式记录日志
- **R9** 请求体改用 Pydantic 模型（宽松声明），非法参数保持返回 **400**（而非 422），维持既有契约

### 6. 清理与版本（S5 / R10 / O2）✅
- **R10** 依赖声明与配置清理（移除失效 CORS 配置项）；`APP_VERSION` 提升至 `3.4.0`
- **O2** 管理员不能禁用/删除**自己的**账号（target==current → 400）；允许操作其他管理员账号

### 7. 文档对齐 ✅
- `PROJECT.md` / `README.md` / `SRS.md` 同步改写至 **v3.4.0**
- 7 份根目录产品文档归档至 `docs/product/`（英文 slug、加历史横幅）；评审类归位 `docs/review/`、图件归位 `docs/diagrams/`
- 新建 `docs/README.md` 文档总索引、`docs/review/v3.4.0-change-summary-2026-09-12.md` 变更总结
- ⚠️ **路径迁移说明**：本版将原 `docs/*.md` 迁入 `docs/review/`（图件迁入 `docs/diagrams/`）；更早条目中出现的 `docs/architecture-review-2026-09-12.md`、`docs/doc-sync-2026-09-12.md` 等旧路径，即对应 `docs/review/` 下同名文件（上述链接已同步修正为现行路径）。

### 自动化测试
| 测试文件 | 用例数 |
|----------|:--:|
| `test_auth.py` | 8 |
| `test_items.py` | 14 |
| `test_admin.py` | 7 |
| `test_stats.py` | 4 |
| `test_adversarial_auth.py` | 6 |
| `test_adversarial_stats.py` | 4 |
| `test_adversarial_meta.py` | 2 |
| `test_adversarial_admin_toggle.py` | 1 |
| `test_adversarial_batch_fixes.py` | 24 |
| **总计** | **70**（70 passed / 0 failed ✅）|

### 数据库备份
- 升级前备份：`backend/lost_found.db.bak-20260912`

---

> **当前版本**: V3.4.0 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery + Redis / OSS + PWA

---

## V3.4.1 — 契约补齐 (2026-09-12)

### 迭代目标
补齐 v3.4.0 评审遗留的最后一处一致性问题：`POST /api/items/match` 此前在后端**无鉴权依赖**（仅依赖前端路由守卫），本轮将其补齐为需登录端点，使接口契约与页面访问控制一致。

> 历史背景：v3.4.0 文档（`SRS.md` §5.2 / §9.3、`PROJECT.md` §11.1）曾如实标注该端点为「无鉴权」遗留项；本轮即针对该项的收尾修复。

### 1. 补齐 `POST /api/items/match` 鉴权 ✅
- 源码：`backend/app/api/items.py:458` → `async def match_items(req: MatchRequest, current_user: dict = Depends(get_current_user)):`
- 实测契约：
  - 缺 `Authorization` 头 → **403** `{"detail":"Not authenticated"}`（`HTTPBearer` auto_error）
  - token 非法 / 过期 → **401** `{"detail":"无效或过期的 Token"}`
- 前端无改动：`/match` 路由本就有 `requiresAuth` 守卫，axios 拦截器自动附带 token

### 2. 版本与测试 ✅
- `backend/app/config.py:8`：`APP_VERSION` → `"3.4.1"`（OpenAPI `version` 随之）
- 更新 3 条路由顺序用例 + 新增 2 条鉴权契约用例（`backend/tests/test_items.py`：14 → 16）
- **72 passed / 0 failed**（原 70）

---

> **当前版本**: V3.4.1 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery + Redis / OSS + PWA

---

## V3.5.0 — 中文化模型 + 图文跨模态检索 (2026-09-14)

### 迭代目标
把「以文搜图」从**名不副实**变为**真能力**：默认模型由英文预训练的 `open_clip ViT-B-32` 换为中文图文跨模态的 **Chinese-CLIP ViT-H-14**（OFA-Sys `cn_clip`），并**启用 img·text 跨模态通道**（此前系统只比两个自相似度、从不计算图文对齐）；同时把阈值/权重 config 化、可回滚、可标定，并加装维度错配的运行期防线。保留 `open_clip` 作为**可一键回滚**后端。

> 依据：增量 PRD [docs/product/PRD-v3.5.0-incremental.md](docs/product/PRD-v3.5.0-incremental.md)、架构设计 [docs/review/v3.5.0-incremental-design.md](docs/review/v3.5.0-incremental-design.md)、QA 回归 [docs/review/qa-v3.5.0-regression-2026-09-13.md](docs/review/qa-v3.5.0-regression-2026-09-13.md)。

### 1. 模型双后端抽象（D1）✅
- ➕ `backend/app/clip_backend.py`：新增 `ClipBackend` **协议**（`encode_image` / `encode_text` / `embed_dim` / `is_available`）+ `OpenClipBackend`（回滚，行为等价 v3.4.1）+ `ChineseClipBackend`（默认）+ `get_backend()` **工厂**（按 `settings.CLIP_BACKEND` 选择）。
- 默认 `CLIP_BACKEND="cn_clip"` → **ViT-H-14**（`embed_dim=1024`，**联合投影维度**，非视觉宽度 1280、非 512）；回滚 `"open_clip"` → **ViT-B-32**（512 维）。
- **未知 `CLIP_BACKEND` 取值 → 抛 `RuntimeError`，禁止静默降级**（新旧向量空间不兼容，静默降级会拿新查询向量比旧库向量）。
- `cn_clip` 为 **lazy import**（仅在后端 `_ensure_loaded` 内导入），保证未安装该包时 pytest **收集阶段不崩**。
- `CLIPService` 退化为**兼容壳**，公开方法名/签名冻结（`_initialize` / `get_image_feature` / `get_text_feature` / `get_color_histogram` / `compute_color_similarity` / `compute_weighted_similarity`）。
- 安装：`cn_clip` 须 **`pip install cn_clip --no-deps`**（其 `setup.py` 硬钉 `lmdb==1.3.0`，Windows 无 wheel 会编译失败；推理不需要 lmdb）；权重默认走 **ModelScope**（`CLIP_CN_USE_MODELSCOPE=True`），或置 `CLIP_CN_CKPT_PATH` 指向本地 `.pt` 实现**运行期零网络**。

### 2. 跨模态四通道打分 + 阶段5 重构（D2 / D3）✅
- 打分通道由「图-图 0.50 / 文-文 0.30 / 色 0.20」三自相似，扩为**四通道跨模态**：
  - `sim_img_img`（`q_img·t_img`）权重 **0.35**；
  - `sim_cross`（**0.35**）= 可用方向加权平均，内权重 `W_CROSS_T2I`（`q_text·t_img`）/ `W_CROSS_I2T`（`q_img·t_text`）各 **0.5**；
  - `sim_text_text` 权重 **0.15**；`sim_color` 权重 **0.15**。
  - 缺维度按比例**动态归一化**（权重和恒为 1），全缺 → `0.0`。
- **阶段5 升级为真跨模态一致性惩罚**：`cc = min(可用跨模态方向)`；仅当 `max(sim_ii, sim_tt) ≥ CROSS_PENALTY_SELF_HIGH`（0.55）触发；**只降权、对 cc 单调**，因子 ∈ `[CROSS_PENALTY_FLOOR, 1.0]`（默认下界 **0.50**，即最大对折）；`CROSS_PENALTY_ENABLED` 可一键关闭。旧「两自相似比大小」的假交叉验证**移除**。
- 全部权重/阈值/开关**经 config 驱动**（`app/config.py` 新增 `MATCH_W_*` / `MATCH_W_CROSS_*` / `CROSS_PENALTY_*` 等），代码内不硬编码。

### 3. 匹配接口契约（不新增端点）✅
- `POST /api/items/match` 结果项**新增 `match_source`**（∈ `text` / `image` / `mixed`，按查询实际可用输入判定）；
- 响应顶层**新增 `legend: {high, mid}`**，默认由 `MATCH_THRESHOLD_AUTO` / `MATCH_THRESHOLD_MANUAL` **派生**（可由 `MATCH_LEGEND_HIGH` / `MATCH_LEGEND_MID` 覆盖），**修掉前端硬编码图例**（v3.4.1 前端 0.75/0.5 vs 后端 0.20 的割裂）；
- **403/401 契约冻结不变**：缺 `Authorization` → 403 `{"detail":"Not authenticated"}`；非法 token → 401；
- 手动阈值默认值统一走 `_match_threshold_default()`（**每次访问 settings**，消除导入期快照导致的「配置变更只在图例生效」割裂）。

### 4. 阈值重标定与可回滚 ✅
- 三档阈值重设（**均为初值**）：`MATCH_THRESHOLD_MANUAL` **0.20 → 0.35**、`AUTO` **0.65 → 0.55**、`EMAIL` **0.75 → 0.70**；
- 新增 `AUTO_MATCH_ENABLED` 自动推送总开关（灰度期置 false，重嵌入期间暂停推送）；
- 自动匹配路径新增**维度预检**：库中向量维度 ≠ 当前模型维度 → 记 `ERROR` 并跳过（避免被静默吞成「未找到」）。

### 5. 运维脚本（3 个新增）✅
- ➕ `backend/scripts/reembed_all_vectors.py`：**全量重嵌入** `image_vector` / `text_vector`——库文件**冷备**（`lost_found.db.bak-*`）/ `--dry-run`（只读 + 输出 **ETA**）/ **断点续跑**（`--resume`，含 fingerprint 校验）/ **幂等**；`color_vector`（27 维，与模型无关）不动。
- ➕ `backend/scripts/calibrate_thresholds.py`：**PR 曲线** + `Recall@1/3/5/10` + `--grid` 权重网格（步长 0.05、和 = 1.0）+ `--degenerate-check`（确认 `sim_ii ≡ 1.0` 的接线自检）/ `--stats`（结构自检，不加载模型）。
- ➕ `backend/scripts/backfill_color_vectors.py`：回填历史 `items.color_vector`（27 维）。

### 6. 评测集 ✅
- ➕ `backend/eval/eval_set_v3.5.0.json`：**70 对 = 30 正 / 40 负**（50 对纯文查询 + 20 对图片查询）；其中 **6 对「同图自比」退化对**（`sim_ii ≡ 1.0`）已在标定计算中**剔除** → **有效样本 24 正 / 40 负（n=64）**。负样本含 **10 对同类硬负样本（N31–N40）**，见 §9。
- 小样本免责继续有效：`n` 小、置信区间宽，阈值须随真实数据增长**持续复标**。

### 7. 维度错配的运行期防线（R4 / R2）✅
- **编码后断言**：`app/clip_backend.py::_assert_embed_dim`——每个 `encode_*` 在 L2 归一化后、返回前断言输出维度 == 声明的 `embed_dim`，不符抛 `RuntimeError`（拦下「声明 512、实际 1024」类契约漂移）；
- **打分前预检**：`/match` 在逐条打分前调用 `_assert_vector_dims_match`，库中向量维度 ≠ 当前模型维度 → **HTTP 500**（提示先运行 `reembed_all_vectors.py`）；自动匹配路径同样预检 → 记 `ERROR`。
- 动机：原先 `np.dot` 维度不符被 `except: continue` **静默吞成空结果**，与「真的没找到」外观一致 → 全站匹配静默失效。

### 8. 文档与测试 ✅
- 文档同步至 v3.5.0：`PROJECT.md` / `SRS.md` / `README.md` / `docs/README.md` / 增量 PRD（含 ViT-H-14 维度 512 → **1024 联合投影**修正）。
- 自动化测试扩至 **209 用例（207 通过 / 2 门控跳过）**〔数值随套件演进，以 `--junitxml` 为准〕；新增 `test_match_contract_v350.py` / `test_cross_modal_scoring.py` / `test_cross_consistency_penalty.py` / `test_embed_dim_runtime_contract.py` / `test_config_rollback.py` / `test_reembed_script.py` / `test_qa_v350_*` / `test_calibrate_*` / `test_reembed_encoder_wiring.py`（见 §9）等；2 个 skip 为 `test_real_clip_smoke.py` 的**真实权重门控**用例（设 `RUN_REAL_CLIP=1` 时转通过）。
- 重嵌入脚本补强：`reembed_all_vectors.py` 修复「假绿迁移」缺陷——`main()` 曾恒返回 0，会让真实写库失败时仍以成功退出；现新增 `_ServiceEncoderAdapter`（对齐冻结的 `clip_service` 接口）与 `_exit_code` 守卫（`failed_encode>0` → 2、`ok==0 且 total>0` → 3、`--dry-run` 仍 0），并补 `test_reembed_encoder_wiring.py` 8 例锁定回归。

### 9. 真实权重验证轮（v3.5.0 收尾，2026-09-14）✅
解决了本版长期悬置的「**本机从未加载真实权重**」问题，并把标定从「打桩验证」推进到「**已用真实模型验证**」。

- ➕ `backend/scripts/download_cn_clip_weights.py`：**断点续传**下载器（urllib + HTTP Range；服务器忽略 Range 返回 200 时**从零重下**，杜绝半截坏文件）。经 ModelScope 源 `AI-ModelScope/chinese-clip-vit-huge-patch14` 取得 `clip_cn_vit-h-14.pt`（**3,830,716,726 字节**，字节级校验通过），**无需 `pip install modelscope`**（纯 urllib）；配合 `CLIP_CN_CKPT_PATH` 实现**零网络加载**（16.2s）。
- ➕ `backend/scripts/verify_real_clip.py`：端到端真机验证 —— 结构契约比对（对 `_MODEL_INFO`）、真实加载、编码 **1024 维 + L2 归一**、语义合理性（`cos(查询,正例) > cos(查询,跨类别负例)`）。**全部 PASS**；`test_real_clip_smoke.py` 2 例由 **skip 转通过**。
- **真实标定结果**：`Recall@3 = 1.0` / `Recall@1 = 0.7917` / `Recall@5 = Recall@10 = 1.0`；**跨类别检索已解**，5 个 rank-2 误排**全是同类近重复**（item64↔68 白色蓝牙耳机、item77↔67 卡片）。
- 🐞 **修复 3 处「桩路径掩盖真实路径」的缺陷**（真实权重下才暴露，均已补守卫测试）：
  1. **编码器接口漂移**：`calibrate_thresholds.py` 内部调用 `encode_text/encode_image`，而真实 `clip_service` 只暴露 `get_*_feature` —— 假编码器定义了接口、真实编码器从未接上。修法：加 `_ServiceEncoderAdapter` 适配（**改脚本去迁就冻结的服务接口**，不改服务）。
  2. **候选集重复计数**：候选按 `item_ref or text` 去重，导致**同一条物品被拆成两个候选**（实测 10 个候选 = 6 物品 + 4 幻影），真目标被自己的幻影挤出 Top-3 → `Recall@1/@3` 被算成 **0.0**（真实 0.7917/1.0），并触发一次**错误的**「阻塞性发现」。修法：按 `item_id` 去重 + 字段合并。
  3. **标定未接颜色通道**：`score_pair` 不传 `color1/color2`，而线上两个调用点（`match_service.py:104` / `items.py:614`）都传 → `has_col` 恒为 False → **`W_COLOR` 数学上完全惰性**（实测 `color_weight` 取 0.0/0.15/0.5/0.9 得分完全相同），网格里那列 `W_COLOR 0.7~0.9` 是**假象**。修法：与线上一致传入颜色直方图。
- ➕ 3 个守卫测试：`test_calibrate_candidates.py`（7）/ `test_calibrate_color_channel.py`（5）/ `test_calibrate_grid_summary.py`（4）。
- **网格「并列退化」方法论修正**：`grid_search` 现同时输出**合格集合分布**（`summarize_grid`）——实测合格组合 **103** 个、其中 **102** 个并列 `Recall@3=1.0`，故 Top-N 顺序**无意义**；有信息量的是集合结构（`W_COLOR` 取值直方图单调递减 ⇒ `W_COLOR≈0`、文本主导）。
- **评测集补充 10 对同类硬负样本（N31–N40）**：复用既有正样本查询文本、只换目标，构造「高相似但不同物」的假阳性场景（原负样本全为易分跨类别错配）。结果：`Recall@K` **完全不变**（印证跨类别已解、同类近重复才是残差），而 Precision 上界进一步下降 —— 这是**预期且正确**的。
- ⚠️ **`AUTO`/`EMAIL` 仍不可标定**：默认配置下 PR 曲线 Precision 上界仅 **0.6129**（补硬负样本前约 0.77），`Precision≥0.90/0.98` **无解** → 返回 `None`。**不得为凑出 0.90 而放宽口径**。

### 10. 生产库重嵌入执行轮（2026-09-14，用户授权）✅
解决了「代码已切 cn_clip、库中向量仍为 512 维旧数据」的**悬挂态**（此前 `/match` 因维度防线触发 HTTP 500，cn_clip 尚未真正生效）。

- **执行前预检（只读）**：确认权重在位（3.83GB）、`AUTO_MATCH_ENABLED=false` 已在 `.env` 生效（防止重嵌入后自动推送按未标定初值 0.55 开启）、DB MD5 留档。
- **冷备**：`lost_found.db.bak-20260914121815`（与原库字节一致，回滚可用）。
- **全量重嵌入**：`scripts/reembed_all_vectors.py` 正式跑 —— 模型加载 16s + 编码写库 28.9s，统计 `total=6 / processed=6 / ok=6 / failed_encode=0`，`_exit_code` 守卫 → **EXIT=0**。
- **写库后验证**：6 条 `image_vector`/`text_vector` 全部 **1024 维 + L2 归一**（JSON 长度翻倍）；`color_vector`（27 维）**逐字节未动**。
- **端到端验证**：`POST /api/items/match {"text":"蓝牙耳机","target_type":"lost"}` → **HTTP 200**（此前 500）——4 条 lost 候选全部完成跨模态打分，item68「蓝牙耳机」score=0.3872 过手动阈值 0.35 排第一（`source=text`），found 类被正确排除，`legend={high:0.55, mid:0.35}` 派生正确。
- **灰度保持**：`AUTO_MATCH_ENABLED=false` 不变；门禁步骤 8（回填 `MATCH_THRESHOLD_AUTO/EMAIL`）**仍禁止**——须扩充真实评测集复标（默认配置 Precision 上界 0.6129 ＜ 0.90）。
- 配套：`.gitignore` 补 `backend/scripts/.reembed_state.json`（断点状态文件，含本机模型指纹，不入库）。

### 11. 评测集扩充轮 + V4 截断实验（2026-09-14）✅
按文档顺序执行的三项收尾优化（灰度验证 → 评测集扩充复标 → V4 实验）。

- **灰度验证（门禁步骤 10 冒烟补齐）**：`/match` 纯图搜 3 组 + 图文混合 2 组端到端全部 HTTP 200 —— 同类图搜正确命中（item68 耳机 0.62~0.70 排第一）、混合模式自匹配满分排第一（0.70/0.66）、`match_source` 三态（text/image/mixed）与 `legend` 派生全部正确；跨类别查询低分符合预期。
- **评测集扩充**：`eval_set_v3.5.0.json` 70 → **84 对**（+12 条查询变体正样本 P41–P52，每物品 +2、不含 title 原词、与既有查询查重；+2 对 img→img 同类不同物硬负样本 N53–N54）→ 有效标定集 **36 正 / 42 负（n=78）**。
- **复标结论（真实模型）**：`Recall@3=1.0` / `Recall@1=0.75`；Precision 上界 0.6129 → **0.6889**（threshold≈0.343 处），仍 ＜ 0.90 → **`AUTO`/`EMAIL` 结构性无解**，返回 `None`。瓶颈不在正样本数量（+50% 仅 +7.6pp，边际收益显著递减），而在**负样本结构**——同类近重复（3/6 物品为电子产品）与正样本在分数上不可分。**门禁步骤 8 继续禁止**；解除路径 = 真实物品类别多样性增长，而非继续堆查询变体。**未放宽口径**。
- **V4 截断实验闭环（真实模型）**：① 截断一致性：64 字完整串 vs 人工前 50 字向量 `cos=1.000000`（证实截断点 = 50 字、静默无异常）；② 关键信息完全落在 50 字窗口外时，`cos 0.6736 → 0.5220`（**相对损失 ~22.5%**）；③ 长文本本身稀释相似度（74 字长查询 0.67 vs 短查询 0.84）。工程结论：**物品特征前置**可显著保住检索力；前端 `maxlength=300` 与真实 50 字窗口的矛盾应加用户提示。至此 QA 报告 V1–V5 全部「已用真实模型验证」。
- 配套：QA 报告 V4 项与发版门禁待办、标定报告（脚本重生成）、PROJECT/SRS/README/docs 索引、`eval/README.md` 现行描述已同步至 84 对口径；历史轮次记录保留原数字。

### 12. 打分通道收敛为「三通道等权」+ 颜色通道废弃（2026-09-16）✅
起因：用户实测「纯文搜分数偏低」（输入「白色蓝牙耳机」匹配到同名的正确物品，却只有 45%）。逐阶段拆解发现**匹配没找错**，是**分数标度**被低分通道压住：纯文搜索时跨模态通道占 70% 权重，而跨模态余弦天然只有 0.2~0.3 量级。

**用户决策**：通道收敛为三个 —— ①文-文 ②图文跨模态（双向合并）③图-图；**各自独立、等权**（权重均为 1，缺通道动态归一化 ⇒ 等价于可用通道算术平均）；**颜色通道彻底废弃**。

- **配置（`app/config.py`）**：`MATCH_W_TEXT_TEXT` / `MATCH_W_CROSS` / `MATCH_W_IMG_IMG` = **1.0**；`MATCH_W_COLOR` = **0.0**（键位保留仅兼容旧配置）。
- **打分（`app/clip_service.py`）**：`compute_weighted_similarity` 通道列表收敛为三项；颜色通道不再参与；`color1/color2/color_weight` 形参**保留但一律忽略**（冻结接口兼容），`compute_color_similarity` / `get_color_histogram` 方法保留不参与打分。
- **调用点清理**：`api/items.py` 与 `services/match_service.py` 移除查询/目标的颜色直方图读取与回退计算（**顺带省掉每次匹配的 27 维直方图计算与磁盘 IO**）。
- **标定脚本**：`--grid` 权重网格由四维降为三维（`{text_text, cross, img_img}`）；`summarize_grid` 不再输出颜色直方图；`score_pair` 不传颜色。
- **实测效果（真实模型 + 真实库）**：同一查询「白色蓝牙耳机」→ item64 **45% → 58%**（`source=text`，跨过 `legend.high=0.55` 从「中等」升为「高置信」）；**Recall@K 完全未退化**（@1=0.75 / @3=1.0 / @5=1.0 / @10=1.0，与四通道口径一致）→ 属**分数标度**改进而非排序改变。`AUTO`/`EMAIL` 仍无解（结构性瓶颈未变）。
- **测试**：209 → **213 用例 / 211 passed / 2 门控 skip / 0 failed**。其中 8 例因口径变更按新口径**重算期望值**（`test_cross_modal_scoring` 2 / `test_qa_v350_math` 4 / `test_qa_v350_precheck` 1 / `test_adversarial_batch_fixes` 1），2 个文件重写为「颜色废弃守卫」的反向断言（`test_calibrate_color_channel` / `test_calibrate_grid_summary`）——断言强度不变（仍是精确值比较），仅方向随口径反转。
- **文档**：`PROJECT.md`（§9.2 算法、§3.3/§8.4 配置、版本清单）/ `README.md`（简介、功能表、架构图、设计系统）/ `SRS.md`（FR-MATCH-03/04、§8.2 算法）现行口径同步；标定报告由脚本重新生成。
- ⚠️ **遗留（未修，待决策）**：时间衰减阶段因 `days_old` 解析缺陷**恒不生效**（`datetime.fromisoformat` 返回 naive → 与 aware 相减抛 `TypeError` → 被 `except` 兜底为 0）。修复会让 76 天前物品的分数再乘 0.2（58% → 12%），**必须与阈值下调同步**，故本轮未动。

### ⚠️ 如实声明（重要）
- **`MATCH_THRESHOLD_AUTO` / `EMAIL` 仍不可用**（Precision 上界 0.6129 → 扩充轮后 0.6889，均 ＜ 0.90）：线上**自动匹配 / 邮件通知**的阈值**尚未收敛**，禁止表述为「已可靠标定」；扩充评测集复标已完成（2026-09-14，84 对），结论为**结构性无解**——解除须待真实物品类别多样性增长。
- **权重只能给方向性结论**（`W_COLOR≈0`、文本主导）：合格集合 102 个并列，**不存在唯一最优权重**。
- ✅ **「已用真实模型验证」这一档已非空**：真实权重已在本机下载并端到端验证（真实 `Recall@3=1.0` / `Recall@1=0.7917`）——与上一轮「本机从未加载真实权重」的声明已不同。
- 换模型后**必须重嵌入全库向量**（`image_vector` / `text_vector`）；**两代向量空间不兼容、不可混用**（`color_vector` 27 维不受影响、不重算）。
- 历史 `matches.similarity_score` 存的是**旧口径**分数，展示时不得与新的「相似度 XX%」并列比较。

### 回归基线
- 升级前备份：`backend/lost_found.db.bak-*`（重嵌入脚本自动冷备）。

---

> **当前版本**: V3.5.0 | **下一迭代**: V4.0 — PostgreSQL + pgvector / Celery + Redis / OSS + PWA
