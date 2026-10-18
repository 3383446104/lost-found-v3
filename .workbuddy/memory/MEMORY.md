# 项目长期记忆 — lost-found-v3

## 前端样式约定

- 设计令牌全部在 `frontend/src/styles/theme.css`：`--text-sm:12px`、`--text-md:15px`、`--text-xl:18px`、`--radius-lg:14px`、`--space-4:16px`、`--neutral-100:#F5F4F1`（= 页面底色）。
- **全局同名类覆盖坑（已踩两次）**：`theme.css` 里有全局 `.img-placeholder`（`height:100%`）和 `.type-badge`（`right:12px`）。在组件 scoped 样式里复用同名类做局部改造时，**必须显式重置全局设置的对向属性**（left↔right、width↔height、height↔aspect-ratio），否则会出现"占位图吞满整卡""徽章拉满整条"这类问题。
- 首页「为你推荐」：`.recommend-grid` 是 flex（5 卡 `flex:1 1 0` + `max-width:22%`），引导文案在 `.recommend-head` 右侧。
- 详情页：`.detail-layout` 本身是白色面板（图 460px 上限 + 右侧信息），信息区 `.info-card` 无边框，认领区在左栏图片下方。

## 验证方式（首页/详情页都需登录）

无法直接截图时：从 Vite 取真实样式渲染离线页 ——
1. `GET /src/views/X.vue` 拿到 `?vue&type=style&scoped=xxx&lang.css` 的 URL；
2. 该 URL **必须加 `&direct`** 才是原始 CSS（否则是 JS 包装模块）；
3. `theme.css?direct` 同理；把 scoped 的 `[data-v-xxx]` 去掉即可在纯 HTML 复现。

## 隐私口径

- 联系方式脱敏统一走 `backend/app/utils/privacy.py::mask_phone`（138****1234）。
- 公开接口（`items` 列表/详情）：发布者本人 / 管理员看完整，其余（含匿名）脱敏。
- 认领接口（`claims.get_claim`）：status∈(1,3) 时向**申请人**返回 `owner_contact`（完整号码，供线下交接）；未通过为 null；发布者/管理员侧为 null。
- 前端拿 `item.contact_masked` 判断是否显示「已脱敏」提示。
