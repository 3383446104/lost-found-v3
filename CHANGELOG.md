# 迭代日志 (CHANGELOG)

> 校园失物智能寻回系统 — 版本迭代记录

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

> **下一迭代目标**: V3.2 — 功能增强（多图上传 / WebSocket 推送 / 搜索高亮 / 数据统计仪表盘）
