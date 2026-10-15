# 校园失物检索平台 — 项目文档

> 版本：v3.6.0 | 日期：2026-10-14 | 技术栈：FastAPI + Vue 3 + CLIP（Chinese-CLIP / open_clip 双后端）
>
> **v3.3 核心变更**：去除访客 | 自标记认领 | 个人中心重构 | 批量审核 | 总计找回 | 历史记录
> **v3.3.1 修复**：统计过滤 | 批量审核路由 | 认领文案 | 列表过滤 | mark-claimed 路由 | 自动匹配通知
> **v3.3.3 工程加固**：新增自动化测试套件 | P0 修复（禁用用户鉴权 / 今日统计时区 / 依赖声明）| 文档与代码对齐（详见 [CHANGELOG](CHANGELOG.md) 与本轮评审报告）
> **v3.4.0 语义与性能加固**：账户状态拆分（`role` × `status`）| 颜色特征持久化（`items.color_vector`）| 公开接口账号状态校验 | 邮件异步化 | 路由 `:int` 健壮化 | 请求体 Pydantic 化 | 死代码清理 | 自动化测试扩至 **70 用例**
> **v3.4.1 契约补齐**：补齐 `POST /api/items/match` 鉴权（需登录；缺 token → 403 / 非法 token → 401）| 自动化测试扩至 **72 用例**
> **v3.5.0 中文化模型 + 跨模态检索**：默认模型换为 **Chinese-CLIP ViT-H-14**（`cn_clip`，`open_clip ViT-B-32` 可回滚）| 启用 **img·text 跨模态**四通道打分 | 阶段5 升级为**真跨模态一致性惩罚** | 阈值/权重 config 化并重标定 | `/match` 结果新增 `match_source`、响应新增 `legend` | 全量重嵌入 / 标定 / 颜色回填三个脚本 | 自动化测试扩至 **209 用例（207 通过 / 2 门控跳过）**；另修复重嵌入脚本的「假绿迁移」缺陷（`_ServiceEncoderAdapter` 对齐冻结服务接口 + `_exit_code` 守卫）。⚠️ **真实权重已在本机下载并端到端验证（真实 `Recall@3 = 1.0` / `Recall@1 = 0.7917`）；但分层阈值仍不可用** —— 评测集已经扩充轮（2026-09-14：+12 查询变体正样本、+2 同类图负对 → **84 对，有效 36 正 / 42 负 n=78**）复标后，Precision 上界仍仅 **0.6889**，`AUTO`/`EMAIL` **结构性无解**（同类近重复与正样本在分数上不可分，须待真实物品类别多样性增长）。✅ **生产库已完成全量重嵌入（2026-09-14，冷备 + `_exit_code` 守卫，6 条全部 1024 维）**，`/match` 已端到端实测恢复（HTTP 200，纯文/纯图/混合三模式全部通过）；`AUTO_MATCH_ENABLED=false` 灰度保持（⚠️ 该行为 v3.5.0 收尾时点快照，「AUTO/EMAIL 无解」与灰度状态已由 v3.6.0 解决，见下行）
> **v3.6.0 打分口径重构 + 社区化融合**：按查询形态分**三种检索模式**（文字 / 图片 / 图文混合，缺通道动态归一化自动成形）| 权重改「主证据 + 辅助证据」（同模态 0.75 / 跨模态 0.25）| **跨模态尺度映射**（0.194→0、0.298→1；仅外层加权与展示，阶段5 仍用原始余弦）| **证据链** + 三分数分离（`content_score` 判定 / `match_score` 排序 / `reference_score` 展示）| 时间衰减失效修复（`utils/time_utils.days_since_utc`）并调温和（90→240 天、下限 0.2→0.6）| **三档阈值首次标定成功**（MANUAL 0.624956 / AUTO 0.733952 / EMAIL 0.832069，内容分尺度；自动匹配判定改用 `content_score`；自动推送开关已开启）| 融合参考项目八大设计：认领闭环 / 举报 / 留言 / 多图 / 统计看板 / 相似推荐 / 证据链可视化 / 内容运营 | 自动化测试扩至 **304 用例（302 通过 / 2 门控跳过）**

---

## 目录

1. [项目概述](#1-项目概述)
2. [技术架构](#2-技术架构)
3. [需求功能覆盖矩阵](#3-需求功能覆盖矩阵)
4. [数据库设计](#4-数据库设计)
5. [API 接口文档](#5-api-接口文档)
6. [前端页面清单](#6-前端页面清单)
7. [UI 设计系统](#7-ui-设计系统)
8. [部署指南](#8-部署指南)
9. [核心算法说明](#9-核心算法说明)
10. [全链路测试报告](#10-全链路测试报告)
11. [已知限制与后续迭代](#11-已知限制与后续迭代)

---

## 1. 项目概述

### 1.1 项目背景

校园内失物招领信息分散于 QQ 群、表白墙、BBS、服务台等多处，师生查询困难，物品找回成功率低。传统方式依赖关键词匹配和人工浏览，难以利用物品的**图片信息**进行跨模态检索。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **多模态智能匹配** | 基于 **Chinese-CLIP ViT-H-14**（默认，中文跨模态）模型，支持「以图搜图」「以文搜图」「图文混合」三种匹配模式；`open_clip ViT-B-32` 为可回滚后端，config 一键切换 |
| **自动推送通知** | 审核通过后自动匹配异类物品（失物↔拾物），相似度达标时双向推送站内通知 + 邮件 |
| **认领闭环** | 失物→"我要归还"、拾物→"我要认领"；申请含特征描述 + 证明图；发布者审批（同意时**互斥自动拒绝**同物品其他申请，物品转"认领中"）；联系方式**脱敏**仅对申请人可见；确认完成联动"总计找回"计数器（v3.6.0 取代旧"通知式认领"） |
| **管理员审核** | 审核通过/驳回+邮件通知；一键批量通过；用户管理（角色/禁用/逻辑删除）；**设为首页推荐** |
| **社区互动** | 举报（5 类 + 处理留痕 + 进度查询）、留言（楼中楼 / 本人可删 / 管理员隐藏） |
| **多图上传** | 1-3 张图片、拖拽排序、首图封面；**仅封面参与向量检索**（打分口径零改动），多图匹配在查询侧聚合（L2 归一化→均值→再归一化） |
| **相似推荐** | 详情页相似物品推荐（反类型 + 复用匹配口径）；首页"为你推荐"推荐位 |
| **统计看板** | 首页统计卡片（展示中/今日失物/今日拾物/总计找回）；管理端看板（找回率仪表盘 / 近 30 天发布趋势 / 分类占比） |
| **内容运营** | 轮播图（排序/启停/跳转）、分类管理（表驱动 + 使用中删除保护）、公告草稿/发布分离 |
| **个人中心** | Tab 分段式布局：账户设置 + 联系方式 + 历史记录；首字母头像(纯展示)；注销账号 |
| **完整闭环** | 发布 → 审核 → 匹配 → 通知 → 认领申请 → 审批 → 归还确认 → 历史记录 |

### 1.3 用户角色

| 角色 | 权限 |
|------|------|
| **普通用户** | 浏览物品；发布/编辑/删除自己的物品（多图）；使用智能匹配（多图）；申请认领/归还（特征描述 + 证明图）、审批自己物品的认领申请；留言 / 举报；查看通知；个人中心（含历史记录） |
| **管理员** | 审核所有物品（含批量通过）；用户管理（角色/禁用/逻辑删除）；发布公告；编辑/删除任何物品；拥有普通用户全部权限 |

> **v3.4.0 角色模型**：上表的「普通用户/管理员」由 `users.role`（∈ {user, admin}）表达；账号的**启停/注销**由独立的 `users.status`（∈ {active, disabled, deleted}）表达，二者解耦——禁用/启用不再改动 `role`（详见 §4.1）。

---

## 2. 技术架构

```
┌─────────────────────────────────────────────┐
│                  前端 (Vue 3)                │
│  Element Plus 2.14 + Pinia + Vue Router 5   │
│               Vite 8 (Rolldown)              │
│            http://localhost:5173             │
└─────────────────┬───────────────────────────┘
                  │ /api (proxy)
┌─────────────────▼───────────────────────────┐
│               后端 (FastAPI)                 │
│    Python 3.11 + Pydantic 2 + SQLite         │
│    JWT (HS256) + bcrypt + CLIP 2backend     │
│            http://localhost:8000             │
└─────────────────┬───────────────────────────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
  SQLite     CLIP 模型     SMTP 邮件
 (本地)     (cn 3.8GB/      (可选)
             oc 600MB)

项目根目录结构:
lost-found-v3/
├── PROJECT.md              ← 本文档
├── README.md               ← 快速上手
├── SRS.md                  ← 软件需求规格说明
├── CHANGELOG.md            ← 迭代日志
├── docs/                   ← 文档中心（详见 docs/README.md）
│   ├── README.md           ← 文档索引
│   ├── product/            ← 产品阶段文档（v3.3 历史快照 + v3.5.0 增量 PRD）
│   ├── review/             ← 评审与整改（架构评审 / 文档同步 / 增量修复设计 / 整合映射 / 变更总结 / v3.5.0 增量设计 + QA 回归）
│   └── diagrams/           ← sequence-diagram.mermaid / class-diagram.mermaid（含 v3.5.0 三张图）
├── backend/
│   ├── .env                ← 环境变量（密钥/配置）
│   ├── lost_found.db       ← SQLite 数据库
│   ├── uploads/            ← 图片存储
│   ├── logs/               ← 日志文件
│   ├── requirements.txt    ← 运行依赖
│   ├── requirements-dev.txt← 测试依赖（pytest / httpx）
│   ├── pytest.ini          ← pytest 配置
│   ├── scripts/            ← 运维脚本（reembed_all_vectors.py 全量重嵌入 / calibrate_thresholds.py 阈值标定）
│   ├── eval/               ← 评测集（eval_set_v3.5.0.json，84 对构造样本）
│   ├── tests/              ← 自动化测试套件（296 用例）
│   │   ├── conftest.py
│   │   ├── test_auth.py / test_items.py / test_admin.py / test_stats.py
│   │   ├── test_claims.py / test_reports.py / test_comments.py / test_banners.py / test_categories.py
│   │   ├── test_multi_image.py / test_similar_recommend.py / test_stats_admin.py / test_announcement_draft.py
│   │   ├── test_match_contract_v350.py / test_cross_modal_scoring.py / test_cross_consistency_penalty.py
│   │   ├── test_embed_dim_runtime_contract.py / test_config_rollback.py / test_reembed_script.py
│   │   └── test_adversarial_*.py
│   └── app/
│       ├── main.py         ← FastAPI 入口
│       ├── config.py       ← 配置（模型后端/阈值/权重/路径/版本）
│       ├── database.py     ← 数据库连接 + 初始化 + 幂等迁移 + 向量工具
│       ├── clip_backend.py ← CLIP 后端抽象（ClipBackend 协议 + OpenClip/ChineseClip 实现 + 工厂）
│       ├── clip_service.py ← CLIP 特征提取（委托后端）+ 颜色直方图 + 跨模态加权相似度
│       ├── logger.py       ← 日志配置
│       ├── validators.py   ← 输入验证
│       ├── models/         ← Pydantic 数据模型（user / match / admin）
│       ├── api/            ← 路由（auth/items/admin/notifications/stats/announcements/claims/reports/comments/banners/categories）
│       ├── services/       ← 业务逻辑（自动匹配/通知）
│       ├── dependencies/   ← 鉴权依赖（JWT + 可选身份解析）
│       └── utils/          ← 工具（时间/文件/邮件）
└── lost-found-frontend/
    ├── index.html
    ├── vite.config.js      ← Vite 配置 + API 代理
    ├── public/
    │   └── campus-aerial.jpg ← 校园航拍背景图
    └── src/
        ├── main.js          ← 入口（Element Plus + 主题）
        ├── App.vue          ← 根组件（条件布局）
        ├── styles/
        │   └── theme.css    ← 全局设计系统（595行）
        ├── layouts/
        │   └── DefaultLayout.vue ← 主布局
        ├── views/           ← 12 个页面组件 + admin/ 4 个管理子组件（举报/留言/轮播图/分类）
        ├── stores/          ← Pinia 状态（auth/notification）
        ├── api/             ← API 调用封装
        ├── router/          ← 路由 + 导航守卫
        └── utils/           ← 工具函数
```

### 技术选型理由

> **v3.5.0 模型后端**：由 `CLIP_BACKEND` 配置项驱动——默认 **`cn_clip`** → **Chinese-CLIP ViT-H-14**（OFA-Sys，权重首次加载约 **3.83GB**，输出 **1024 维**联合投影；文本塔 RoBERTa-wwm-ext-large-chinese，输入分辨率 224）；可切 **`open_clip`** → **ViT-B-32**（`laion2b_s34b_b79k`，约 600MB，输出 **512 维**）**回滚**。两代向量空间**不兼容、不可混用**，切换后必须重嵌入全库向量（`scripts/reembed_all_vectors.py`）。未知 `CLIP_BACKEND` 取值**抛 `RuntimeError`，禁止静默降级**（`app/clip_backend.py::get_backend`）。

| 技术 | 理由 |
|------|------|
| **SQLite** | 毕设阶段零配置；单文件部署；足以支撑校园级并发 |
| **JSON 向量存储** | 简化架构，避免引入 FAISS/pgvector 等额外依赖 |
| **JWT HS256** | 无状态认证，7天有效期，前端 localStorage 持久化 |
| **bcrypt** | 密码加盐哈希，防彩虹表攻击 |
| **Element Plus** | 成熟 Vue 3 组件库，中文友好，a11y 完备 |
| **Pinia** | Vue 3 官方状态管理，TypeScript 友好 |
| **CSS 变量** | 全局主题统一管理，便于后续深色模式扩展 |

---

## 3. 需求功能覆盖矩阵

### 3.1 用户认证模块 (FR-AUTH)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-AUTH-01 | 用户注册（用户名/密码/手机/邮箱） | ✅ POST /api/register | ✅ RegisterView | ✅ |
| FR-AUTH-02 | 用户登录（用户名+密码→JWT） | ✅ POST /api/login | ✅ LoginView | ✅ |
| FR-AUTH-03 | 自动登录（localStorage Token） | ✅ JWT 验证 | ✅ authStore.restore() | ✅ |
| FR-AUTH-04 | 获取用户信息 | ✅ GET /api/me | ✅ authStore.fetchUser() | ✅ |
| FR-AUTH-05 | 退出登录 | — | ✅ authStore.logout() | ✅ |
| FR-AUTH-06 | 权限控制（user/admin） | ✅ get_current_admin | ✅ 路由守卫 + isAdmin | ✅ |

### 3.2 物品管理模块 (FR-ITEM)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-ITEM-01 | 发布物品（类型/标题/描述/分类/位置/联系/图片） | ✅ POST /api/items/ (FormData) | ✅ PublishView | ✅ |
| FR-ITEM-02 | 物品列表（分页+卡片） | ✅ GET /api/items/ | ✅ HomeView | ✅ |
| FR-ITEM-03 | 分类筛选（全部/失物/拾物/我的） | ✅ type/user_id 参数 | ✅ filter radio + checkbox | ✅ |
| FR-ITEM-04 | 类别筛选 | ✅ category 参数 | ✅ el-select categories | ✅ |
| FR-ITEM-05 | 关键词搜索 | ✅ keyword LIKE 查询 | ✅ el-input search | ✅ |
| FR-ITEM-06 | 物品详情 | ✅ GET /api/items/{id} | ✅ ItemDetailView | ✅ |
| FR-ITEM-07 | 编辑物品（本人/管理员） | ✅ PUT /api/items/{id} | ✅ PublishView?edit= | ✅ |
| FR-ITEM-08 | 删除物品（含图片文件） | ✅ DELETE /api/items/{id} | ✅ ItemDetailView | ✅ |
| FR-ITEM-09 | CLIP 特征提取（图像+文本向量，维度随后端：cn_clip 1024 / open_clip 512） | ✅ create_item/update_item | — | ✅ |
| FR-ITEM-10 | 多图上传（1-3 张，首图封面，拖拽排序；**仅封面参与向量检索**） | ✅ create_item/update_item（images / keep） | ✅ PublishView 网格 + 原生拖拽 | ✅ |

### 3.3 智能匹配模块 (FR-MATCH)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-MATCH-01 | 以图搜图 | ✅ POST /api/items/match | ✅ MatchView | ✅ |
| FR-MATCH-02 | 以文搜图（**真跨模态**：查询文字 × 目标图片） | ✅ POST /api/items/match | ✅ MatchView | ✅ |
| FR-MATCH-03 | 图文混合匹配 | ✅ 三检索模式之一（文字/图片/图文混合，缺通道动态归一化自动成形） | ✅ MatchView | ✅ |
| FR-MATCH-04 | 加权相似度（**主证据 + 辅助证据**：同模态 0.75 / 跨模态 0.25；**跨模态尺度映射** 0.194→0.298；三分数分离） | ✅ compute_match_detail | — | ✅ |
| FR-MATCH-05 | 结果排序（Top 20） | ✅ sorted[:20] | ✅ 卡片列表 | ✅ |
| FR-MATCH-06 | 匹配范围限定（已审核+活跃） | ✅ WHERE status='active' | — | ✅ |
| FR-MATCH-07 | 分层阈值（**已标定**：手动 0.624956 / 自动 0.733952 / 邮件 0.832069，内容分尺度） | ✅ MATCH_THRESHOLD_MANUAL / _AUTO / _EMAIL | — | ✅ |
| FR-MATCH-08 | 匹配来源标注 + 证据链（`match_source` / `level` / `basis` / `channels`） | ✅ 随每条结果下发 | ✅ 来源标签 + 等级徽章 + 依据文案 | ✅ |
| FR-MATCH-09 | 前端图例随阈值派生（响应 `legend: {high, mid}`） | ✅ resolve_legend() | ✅ 结果图例 | ✅ |
| FR-MATCH-10 | 多图检索（`image_paths` ≤3，L2 归一化→均值→再归一化聚合） | ✅ match_items（仅查询侧聚合） | ✅ MatchView 多图上传 | ✅ |

### 3.4 管理员审核模块 (FR-ADMIN)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-ADMIN-01 | 待审核列表（分页，物品管理 Tab 内嵌） | ✅ GET /api/admin/items?review=pending | ✅ AdminView | ✅ |
| FR-ADMIN-02 | 审核通过（→active，触发匹配） | ✅ PUT /api/admin/reviews/{id} | ✅ AdminView | ✅ |
| FR-ADMIN-03 | 审核驳回（→rejected + 理由+通知+邮件） | ✅ 驳回理由必填验证 | ✅ 驳回 Dialog | ✅ |
| FR-ADMIN-04 | 自动匹配推送（内容分 ≥0.733952；通知/邮件含匹配等级与命中依据） | ✅ BackgroundTasks 异步 | — | ✅ |
| FR-ADMIN-05 | 批量审核通过（同端点支持批量关闭/删除） | ✅ POST /api/admin/items/batch | ✅ 多选+工具栏 | ✅ |
| FR-ADMIN-06 | 审核设推荐（`is_recommend`，首页推荐位数据源） | ✅ review_item / admin items | ✅ AdminView 审核对话框开关 | ✅ |

### 3.5 消息通知模块 (FR-NOTIFY)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-NOTIFY-01 | 站内消息（匹配成功自动生成） | ✅ add_notification | — | ✅ |
| FR-NOTIFY-02 | 未读数量（红点+数字） | ✅ GET /notifications/unread/count | ✅ nav-badge | ✅ |
| FR-NOTIFY-03 | 消息列表 | ✅ GET /notifications/unread | ✅ NotificationsView | ✅ |
| FR-NOTIFY-04 | 标记已读 | ✅ PUT /notifications/{id}/read | ✅ NotificationsView | ✅ |
| FR-NOTIFY-05 | 邮件通知（用户有邮箱时） | ✅ send_match_notification (HTML) | — | ✅ |
| FR-NOTIFY-06 | 轮询更新（每30秒） | — | ✅ DefaultLayout `setInterval` + router.afterEach | ✅ |

> ✅ FR-NOTIFY-06: 已采用**双通道刷新**——`DefaultLayout.vue` 在 `onMounted` 启动 `setInterval(refreshUnread, 30000)` 定时轮询（组件卸载时 `clearInterval`），同时保留 `router.afterEach` 在路由切换时拉取，兼顾实时性与即时性。

### 3.6 认领闭环模块 (FR-CLAIM) — v3.6.0

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-CLAIM-01 | 提交认领申请（特征描述必填 + 证明图 + 联系电话；`proof_` 持久证明图独立于 temp_ 清理） | ✅ POST /api/claims（+ proof-upload） | ✅ ItemDetailView 认领对话框 | ✅ |
| FR-CLAIM-02 | 防冒领与防重复（物品须 active+approved、非本人、同人同物无进行中申请） | ✅ claims.py 校验 | — | ✅ |
| FR-CLAIM-03 | 发布者审批（同意时**同事务互斥**自动拒绝其他待审申请，物品转 `claiming`） | ✅ POST /api/claims/{id}/approve | ✅ ClaimsView（含互斥提示） | ✅ |
| FR-CLAIM-04 | 拒绝必填理由 / 申请人可撤销 / 确认完成（物品转 `claimed` + 计数器 +1） | ✅ reject / cancel / complete | ✅ ClaimsView 三操作 | ✅ |
| FR-CLAIM-05 | 隐私：联系方式脱敏（138\*\*\*\*1234），仅申请通过后对申请人可见 | ✅ GET /api/claims/{id} | ✅ 详情页脱敏展示 | ✅ |
| FR-CLAIM-06 | `mark-claimed` 快捷标记联动已完成申请（计数器不重复计数） | ✅ items.py | — | ✅ |

### 3.7 社区互动模块 (FR-COMMUNITY) — v3.6.0

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-REPORT-01 | 五类举报（虚假/不良/联系方式异常/重复发布/其他），理由必填、同人同物 pending 去重 | ✅ POST /api/reports | ✅ 详情页举报对话框 | ✅ |
| FR-REPORT-02 | 举报进度查询（待处理/已处理/已驳回） | ✅ GET /api/reports/mine | ✅ MyReportsView | ✅ |
| FR-REPORT-03 | 管理端并排详情（举报全字段 × 被举报物品快照） | ✅ GET /api/reports/admin/{id} | ✅ ReportManage 对话框 | ✅ |
| FR-REPORT-04 | 处理留痕（结论必填 + 处理人/时间 + 通知举报人） | ✅ PUT /api/reports/admin/{id}/handle | ✅ ReportManage | ✅ |
| FR-COMMENT-01 | 留言列表（公开可见，扁平结构前端组树） | ✅ GET /api/comments/item/{id} | ✅ ItemDetailView 留言区 | ✅ |
| FR-COMMENT-02 | 发表留言 / 楼中楼回复（≤500 字，parent 须同物品且可见） | ✅ POST /api/comments | ✅ 留言输入 + 回复 | ✅ |
| FR-COMMENT-03 | 删除（本人/admin；删父留言**级联删回复**）/ 管理员隐藏与恢复 | ✅ DELETE + PUT admin status | ✅ 本人删除 + CommentManage | ✅ |

### 3.8 内容运营与统计看板 (FR-OPS / FR-STATS-ADMIN) — v3.6.0

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-OPS-01 | 轮播图（排序 / 启停 / 跳转链接 / 图片上传 `banner_` 前缀） | ✅ /api/banners* | ✅ HomeView 轮播 + BannerManage | ✅ |
| FR-OPS-02 | 分类管理（表驱动 + 排序；**被物品使用的分类拒绝删除**；空表回退常量） | ✅ /api/categories/admin* | ✅ CategoryManage | ✅ |
| FR-OPS-03 | 公告草稿/发布分离（draft/published + publish/unpublish） | ✅ announcements.status | ✅ AdminView 发布/下架按钮 | ✅ |
| FR-STATS-04 | 管理端统计：总览 / 找回率 / 发布趋势（北京时间口径）/ 分类占比 | ✅ /api/stats/admin/* | ✅ AdminStatsView | ✅ |
| FR-STATS-05 | 找回率口径：claimed_total = max(计数器, by_type 求和)；rate = claimed/(claimed+active+claiming) | ✅ stats.py | ✅ gauge 展示 | ✅ |

### 3.9 非功能需求覆盖

| 编号 | 需求 | 状态 | 说明 |
|------|------|:----:|------|
| NFR-PERF-01 | 检索路径 `POST /match` **P95 < 2s**（CPU，无 GPU） | ✅ | 口径按路径拆分；**替代旧「匹配 < 3s」**（v3.5.0 作废该旧口径） |
| NFR-PERF-01b | 录入路径（发布/审核触发编码）**P95 < 15s**，可后台化 | ✅ | 一次性开销；不强制 GPU |
| NFR-PERF-02 | 列表 < 500ms | ✅ | SQLite 查询 + 12 条数据 < 50ms |
| NFR-PERF-03 | ≥ 50 并发 | ⚠️ | SQLite 写锁限制；生产环境建议迁移 PostgreSQL |
| NFR-PERF-04 | 图片 ≤ 16MB | ✅ | MAX_CONTENT_LENGTH: 16MB |
| NFR-SEC-01 | bcrypt 密码 | ✅ | bcrypt.hashpw + gensalt |
| NFR-SEC-02 | JWT (7天) | ✅ | HS256 + 7 天过期 |
| NFR-SEC-03 | SQL 注入防护 | ✅ | 全参数化查询（? 占位符） |
| NFR-SEC-04 | 后端权限校验 | ✅ | get_current_user + get_current_admin |
| NFR-USR-01 | 响应式 | ✅ | 三级断点 480px/640px/768px |
| NFR-USR-02 | 操作反馈 | ✅ | ElMessage 成功/失败/警告 |
| NFR-USR-03 | 空状态引导 | ✅ | el-empty + CTA 按钮 |
| NFR-EXT-01 | 向量存储可迁移 | ✅ | 纯 JSON，可平滑迁移至 pgvector |
| NFR-EXT-02 | 图片存储可迁移 | ✅ | 本地文件，可切换 OSS URL |
| NFR-EXT-03 | 异步任务 | ✅ | BackgroundTasks（可升级 Celery） |

### 覆盖率总结

| 模块 | 总需求数 | 已实现 | 覆盖率 |
|------|:------:|:------:|:------:|
| 用户认证 | 6 | 6 | 100% |
| 物品管理 | 10 | 10 | 100% |
| 智能匹配 | 10 | 10 | 100% |
| 管理员审核 | 6 | 6 | 100% |
| 消息通知 | 6 | 6 | 100% |
| 认领闭环（v3.6.0） | 6 | 6 | 100% |
| 社区互动（v3.6.0） | 7 | 7 | 100% |
| 内容运营与统计（v3.6.0） | 5 | 5 | 100% |
| 非功能需求 | 13 | 12 | 92% |
| **总计** | **69** | **68** | **99%** |

---

## 4. 数据库设计

> **v3.4.0 迁移**：`init_db()` 启动时经 `PRAGMA table_info` 守卫执行两段**幂等**迁移——为 `users` 增补 `status`（在「加列」分支内一次性把历史 `role='disabled'/'deleted'` 映射到 `status` 并把 `role` 复位为 `user`），为 `items` 增补 `color_vector`（老数据置 NULL，由 `backend/scripts/backfill_color_vectors.py` 回填）。见源码 `app/database.py:126-143`。
>
> **v3.6.0 迁移**：五张新表（claims / reports / comments / banners / categories，均 `CREATE TABLE IF NOT EXISTS`；categories 空表时种子 7 类）+ `items` 增补三列（`cover_image` / `images` / `is_recommend`，`PRAGMA table_info` 守卫）。**唯一特殊迁移**是 `items.status` 枚举扩展 `'claiming'`——SQLite 的 CHECK 无法 ALTER，故**整表重建**（幂等判据 = `sqlite_master` 建表 SQL 已含 `'claiming'`；**重建 INSERT 必须显式列名对齐**，老表把 reject_reason/color_vector 作为历史 ALTER 追加在末尾，`SELECT *` 会列序错位触发 CHECK；迁移前强制备份）。实测：9 行生产数据完整保留、幂等可重复执行。

### 4.1 users（用户表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 用户ID |
| username | TEXT | UNIQUE, NOT NULL | 用户名 |
| password_hash | TEXT | NOT NULL | bcrypt 哈希 |
| phone | TEXT | | 手机号 |
| email | TEXT | | 邮箱 |
| role | TEXT | DEFAULT 'user' | 授权角色：user / admin（v3.4.0 起不再含 disabled/deleted） |
| status | TEXT | DEFAULT 'active' | 账号状态：active / disabled / deleted（**v3.4.0 新增**） |
| avatar_path | TEXT | | ⚠️ v3.3 废弃，保留列但不再使用 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 注册时间 |

### 4.2 items（物品表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 物品ID |
| type | TEXT | NOT NULL, CHECK(lost/found) | 类型 |
| title | TEXT | NOT NULL | 标题 |
| description | TEXT | | 描述 |
| category | TEXT | | 分类 |
| image_path | TEXT | | 图片路径（v3.6.0 起与封面同步） |
| cover_image | TEXT | | 封面文件名（= images[0]，**仅封面参与向量检索**）（**v3.6.0 新增**） |
| images | TEXT | | 有序图片文件名 JSON 数组（1-3 张）（**v3.6.0 新增**） |
| is_recommend | INTEGER | DEFAULT 0 | 首页推荐位标记（**v3.6.0 新增**） |
| image_vector | TEXT | | CLIP 图像特征 (JSON) |
| text_vector | TEXT | | CLIP 文本特征 (JSON) |
| contact | TEXT | | 联系方式 |
| location | TEXT | | 地点 |
| status | TEXT | CHECK(7 states) | pending/active/**claiming**/claimed/done/rejected/closed（claiming=认领中，**v3.6.0 新增**，经表重建迁移） |
| user_id | INTEGER | FK → users.id | 发布者 |
| review_status | TEXT | CHECK(3 states) | pending/approved/rejected |
| reviewer_id | INTEGER | FK → users.id | 审核人 |
| review_time | TIMESTAMP | | 审核时间 |
| reject_reason | TEXT | | 驳回理由 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 发布时间 |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

### 4.3 matches（匹配记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | PK |
| lost_item_id | INTEGER | FK → items.id |
| found_item_id | INTEGER | FK → items.id |
| similarity_score | REAL | 余弦相似度 |
| is_confirmed | INTEGER | DEFAULT 0 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

### 4.4 notifications（通知表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | PK |
| user_id | INTEGER | FK → users.id |
| title | TEXT | 标题 |
| content | TEXT | 内容 |
| link | TEXT | 跳转路径（如 /items/5） |
| is_read | INTEGER | DEFAULT 0 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP |

### 4.5 announcements（公告表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PK, AUTOINCREMENT | 公告ID |
| title | TEXT | NOT NULL | 标题 |
| content | TEXT | NOT NULL | 内容 |
| is_pinned | INTEGER | DEFAULT 0 | 是否置顶 |
| target_role | TEXT | DEFAULT 'all' | 可见范围：all / user |
| admin_id | INTEGER | FK → users.id | 发布管理员 |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 发布时间 |

### 4.6 stats_counters（统计计数表）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| key | TEXT | PK | 计数器键（如 total_claimed） |
| value | INTEGER | NOT NULL DEFAULT 0 | 累计值，不受物品删除影响 |

> 说明：`total_claimed` 采用持久化计数器而非实时 `COUNT(*)`，避免物品被删除后「总计找回」回落；首次启动时以现存 `status='claimed'` 物品数初始化（取较大值）。

### 4.7 claims（认领申请表）— v3.6.0

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | PK |
| item_id / claimer_id | INTEGER | FK → items.id / users.id |
| claim_reason / feature_description | TEXT | 认领说明 / 物品特征描述（必填，防冒领核验用） |
| proof_image / contact_phone | TEXT | 证明图（`proof_` 前缀持久文件）/ 联系电话（展示时脱敏） |
| status | INTEGER | **0 待审核 / 1 已通过 / 2 已拒绝 / 3 已完成 / 4 已撤销** |
| review_remark / reviewed_at / completed_at | TEXT / TIMESTAMP | 审批备注（拒绝必填）/ 审批时间 / 完成时间 |
| created_at / updated_at | TIMESTAMP | |

**索引**：`idx_claims_item (item_id, status)`、`idx_claims_claimer (claimer_id, status)`

### 4.8 社区与运营表组 — v3.6.0

| 表 | 关键字段 | 说明 |
|----|---------|------|
| reports | id, item_id, reporter_id, report_type(1虚假/2不良/3联系方式异常/4重复发布/5其他), report_reason(必填), report_image, handle_status(0待处理/1已处理/2已驳回), handle_result, handler_id, handle_time, created_at | 举报 + 处理留痕；索引 `idx_reports_status (handle_status, created_at)`、`idx_reports_item (item_id)` |
| comments | id, item_id, user_id, parent_id(楼中楼，NULL=顶层), content(≤500), status(1正常/0隐藏), created_at | 留言；索引 `idx_comments_item (item_id, status, created_at)` |
| banners | id, title, image_path(`banner_` 前缀), description, link_url, sort_no, status(1启用/0停用), created_at, updated_at | 首页轮播图（sort_no 升序） |
| categories | id, name UNIQUE, sort_no, created_at | 分类表（种子 7 类；**被物品使用则拒绝删除**；`items.category` 仍存 TEXT，改名不追溯历史） |

### 索引策略

```
idx_notifications_user_read  → (user_id, is_read)  复合索引
idx_items_user_id            → (user_id)
idx_items_type               → (type)
idx_items_status             → (status)
idx_items_review_status      → (review_status)
idx_items_created_at         → (created_at)
idx_users_username           → (username)
idx_matches_lost_item        → (lost_item_id)
idx_matches_found_item       → (found_item_id)
idx_claims_item              → (item_id, status)             认领（v3.6.0）
idx_claims_claimer           → (claimer_id, status)          认领（v3.6.0）
idx_reports_status           → (handle_status, created_at)   举报（v3.6.0）
idx_reports_item             → (item_id)                     举报（v3.6.0）
idx_comments_item            → (item_id, status, created_at) 留言（v3.6.0）
```

---

## 5. API 接口文档

### 5.1 认证接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| POST | `/api/register` | ❌ | 用户注册 |
| POST | `/api/login` | ❌ | 用户登录 |
| GET | `/api/me` | ✅ | 获取当前用户信息 |
| PUT | `/api/me` | ✅ | 更新个人资料（密码/邮箱/手机） |
| DELETE | `/api/me` | ✅ | 注销账号（软删除） |
| GET | `/api/me/history` | ✅ | 个人历史记录（v3.3 新增） |

> ⚠️ **v3.3**：`POST /api/me/avatar` 和 `GET /api/avatars/{filename}` 已移除。

**注册请求体：**
```json
{
  "username": "string (2-20)",
  "password": "string (6-30)",
  "phone": "string? (11位手机号)",
  "email": "string? (邮箱)"
}
```

**登录/注册响应：**
```json
{
  "success": true,
  "token": "eyJhbGciOi...",
  "user": { "id": 1, "username": "user", "role": "user", "status": "active" }
}
```

### 5.2 物品接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| POST | `/api/items/` | ✅ | 发布物品（FormData；`images` 1-3 张，首图封面，仅封面算向量） |
| GET | `/api/items/` | ❌ | 物品列表（分页+筛选） |
| GET | `/api/items/{id}` | ❌ | 物品详情（公开；内部解析 token，未审核物品仅发布者/管理员可见） |
| PUT | `/api/items/{id}` | ✅ | 编辑物品（本人/管理员；`keep` 保留文件新顺序 + 新图，封面变更才重算向量） |
| DELETE | `/api/items/{id}` | ✅ | 删除物品（本人/管理员；清理 images 全部文件） |
| POST | `/api/items/match` | ✅ | 智能匹配（JSON body，需登录；支持 `image_paths` 多图） |
| GET | `/api/items/recommend` | ❌ | 首页推荐位（`is_recommend=1` + active + approved） |
| GET | `/api/items/{id}/similar` | ❌ | 详情页相似物品（反类型 + 复用匹配口径打分，按展示分排序） |
| POST | `/api/items/temp-upload` | ✅ | 临时上传图片 |
| PUT | `/api/items/{id}/mark-claimed` | ✅ | 发布者标记已找回/已认领（允许 active/claiming，联动已完成申请） |
| GET | `/api/items/categories` | ❌ | 类别列表（公开；v3.6.0 表驱动，空表回退常量） |
| GET | `/api/items/uploads/{filename}` | ❌ | 访问图片（公开） |

> **v3.4.0（C1）**：公开端点 `GET /api/items/` 与 `GET /api/items/{id}` 的身份解析统一走 `resolve_optional_viewer()`——仅当 token 合法且 `status='active'` 时才认作 viewer，`disabled` / `deleted` 一律**降级为匿名**，避免其以「属主」身份看到自己的未审核物品（见 `app/dependencies/auth.py:89-113`）。
>
> **v3.4.1**：`POST /api/items/match` 由**无鉴权裸端点**补齐为需登录——缺 `Authorization` 头 → 403 `{"detail":"Not authenticated"}`（`HTTPBearer` auto_error）；token 非法 / 过期 → 401 `{"detail":"无效或过期的 Token"}`（见 `app/api/items.py` 的 `match_items`）。
>
> **v3.5.0**：`POST /api/items/match` 结果项**新增 `match_source`**（∈ `text` / `image` / `mixed`），响应顶层**新增 `legend: {high, mid}`**——`legend.high` 默认派生自 `MATCH_THRESHOLD_AUTO`、`legend.mid` 默认派生自 `MATCH_THRESHOLD_MANUAL`（可由 `MATCH_LEGEND_HIGH` / `MATCH_LEGEND_MID` 覆盖），彻底消除前端硬编码图例（见 `resolve_legend()`）。**未新增任何端点**。
>
> **v3.6.0**：新增 `GET /items/recommend`（置于 `/{item_id:int}` 之前避免路由吞噬）与 `GET /items/{id}/similar`；`POST /items/` 与 `PUT /items/{id}` 支持多图（1-3 张，**仅封面参与向量检索**，打分口径零改动）；`/match` 请求新增 `image_paths`（≤3，**仅查询侧聚合**）；`mark-claimed` 允许 `active`/`claiming` 两态——**既有响应结构全部冻结不变**。

**列表查询参数：** `type`, `category`, `keyword`, `user_id`, `limit`, `offset`

**匹配请求体：**
```json
{
  "image_path": "temp_xxx.jpg (可选)",
  "image_paths": ["temp_a.jpg", "temp_b.jpg (可选，多图 ≤3)"],
  "text": "描述文字 (可选)",
  "target_type": "lost | found",
  "threshold": 0.624956,
  "category": "类别 (可选，用于类别增强)",
  "location": "地点 (可选，用于位置增强)"
}
```

> `threshold` 省略时默认取 `MATCH_THRESHOLD_MANUAL`（**0.624956**，2026-09-21 标定）；**判定用内容分 `content_score`**（与标定同尺度），排序用含时间衰减的排序分。
>
> **匹配响应（v3.6.0 口径）：**
> ```json
> {
>   "matches": [
>     { "id": 80, "title": "黑色中性笔",
>       "similarity": 0.96,       // 展示分 = reference_score（最强证据通道，映射后）
>       "content_score": 0.88,    // 内容分（阈值判定，与标定同尺度）
>       "match_score": 0.79,      // 排序分（含时间衰减）
>       "level": "high_suspect",  // 证据等级：confirmed/high_suspect/related/reference
>       "basis": ["文字描述高度吻合"],  // 命中依据
>       "channels": { "sim_text_text": 0.96, "sim_cross": 0.28, "sim_cross_mapped": 0.83, "...": "各通道原始值" },
>       "match_source": "mixed", "...": "其余字段略" }
>   ],
>   "legend": { "high": 0.733952, "mid": 0.624956 }
> }
> ```
> `matches` 最多返回 Top-20，按 `match_score` 降序；`match_source` 按**查询实际可用输入**判定：仅文 → `text`、仅图 → `image`、图文 → `mixed`；**证据链**（`level` / `basis` / `channels`）供前端上色与展示命中依据。

### 5.3 管理员接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| PUT | `/api/admin/reviews/{id}` | Admin | 审核操作（通过/驳回+通知+邮件，可设推荐） |
| GET | `/api/admin/users` | Admin | 用户列表（分页） |
| PUT | `/api/admin/users/{id}` | Admin | 用户管理（设角色/启禁用） |
| POST | `/api/admin/users` | Admin | 新增用户 |
| DELETE | `/api/admin/users/{id}` | Admin | 逻辑删除用户 |
| GET | `/api/admin/items` | Admin | 全部物品（多维筛选+分页） |
| PUT | `/api/admin/items/{id}/status` | Admin | 直接修改物品状态（pending→active 走审核） |
| POST | `/api/admin/items/batch` | Admin | 批量操作（approve / close / delete） |

> **v3.4.0**：`PUT /api/admin/users/{id}` 的 `toggle_status` 仅翻转 `status`（active ↔ disabled）并**保留 `role`**（修复「禁用管理员再启用会降级为 user」）；`set_role` 仅改 `role`。O2：不允许禁用/删除自己（`app/api/admin.py:333-334`、`:399-400`）。

### 5.4 通知接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/api/notifications/unread/count` | ✅ | 未读数量 |
| GET | `/api/notifications/unread` | ✅ | 未读列表 |
| PUT | `/api/notifications/{id}/read` | ✅ | 标记单条已读 |
| PUT | `/api/notifications/read-all` | ✅ | 一键全部已读 |

### 5.5 公告接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/api/announcements` | ❌ | 公告列表（公开仅 `published`；`all=true` 且为管理员时可见全量含草稿） |
| POST | `/api/announcements` | Admin | 新建公告（可存草稿） |
| PUT | `/api/announcements/{ann_id}` | Admin | 编辑公告 |
| PUT | `/api/announcements/{ann_id}/publish` | Admin | 发布（draft → published） |
| PUT | `/api/announcements/{ann_id}/unpublish` | Admin | 下架（published → draft） |
| DELETE | `/api/announcements/{ann_id}` | Admin | 删除公告 |

### 5.6 数据统计接口

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/api/stats/dashboard` | 首页看板（展示中/今日失物/今日拾物/总计找回 + 分类占比） | 是 |
| GET | `/api/stats/admin/overview` | 管理端总览（物品总数/待审核/已完成/用户数） | Admin |
| GET | `/api/stats/admin/recovery` | 找回率（claimed_total = max(计数器, by_type 求和)；分母 claimed+active+claiming） | Admin |
| GET | `/api/stats/admin/publish-trend?days=30` | 发布趋势（lost/found 拆分，北京时间口径） | Admin |
| GET | `/api/stats/admin/category-pie` | 分类占比 | Admin |

> 「今日失物/今日拾物」以**北京时间（UTC+8）当日 00:00–24:00** 为口径统计。`items.created_at` 由 SQLite `CURRENT_TIMESTAMP` 写入 UTC 时间，接口内部换算为对应的 UTC 半开区间后再比较。

> **端点总数（v3.6.0）**：认证 6 + 物品 13 + 认领 10 + 举报 5 + 留言 5 + 管理员 10 + 轮播图 6 + 分类 4 + 公告 6 + 通知 4 + 统计 5 = **74**。

### 5.7 认领接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| POST | `/api/claims/proof-upload` | ✅ | 证明图上传（持久 `proof_` 前缀，独立于 temp_ 清理） |
| POST | `/api/claims` | ✅ | 提交认领申请（feature_description 必填；校验物品 active+approved、非本人、无进行中申请） |
| GET | `/api/claims/mine` / `/api/claims/received` | ✅ | 我的申请 / 收到的申请（分页） |
| GET | `/api/claims/status/{item_id}` | ✅ | 详情页按钮态（无申请/待审/通过/拒绝/完成/撤销） |
| GET | `/api/claims/{id}` | ✅ | 申请详情（三方可见；status∈(1,3) 时向申请人返回**脱敏**联系方式） |
| POST | `/api/claims/{id}/approve` | ✅ | 发布者同意（同事务互斥拒绝其他待审 + 物品转 claiming；通知申请人） |
| POST | `/api/claims/{id}/reject` | ✅ | 发布者拒绝（`review_remark` 必填；物品保持 active） |
| POST | `/api/claims/{id}/complete` | ✅ | 确认完成（物品转 claimed + 计数器 +1） |
| POST | `/api/claims/{id}/cancel` | ✅ | 申请人撤销（仅待审核态） |

### 5.8 举报接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| POST | `/api/reports` | ✅ | 提交举报（report_type 1-5、reason 必填；同人同物 pending 去重） |
| GET | `/api/reports/mine` | ✅ | 我的举报（进度） |
| GET | `/api/reports/admin` | Admin | 举报列表（keyword / report_type / handle_status 筛选，pending 优先） |
| GET | `/api/reports/admin/{id}` | Admin | 并排数据包（举报全字段 + 被举报物品快照） |
| PUT | `/api/reports/admin/{id}/handle` | Admin | 处理（handle_result 必填、写处理人/时间、通知举报人） |

### 5.9 留言接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/api/comments/item/{item_id}` | ❌ | 留言列表（仅 status=1，扁平结构含 username/is_mine） |
| POST | `/api/comments` | ✅ | 发表留言/回复（≤500 字；parent 须同物品且可见） |
| DELETE | `/api/comments/{id}` | ✅ | 删除（本人/管理员；**父留言级联删回复**） |
| PUT | `/api/comments/admin/{id}/status` | Admin | 隐藏 / 恢复 |
| GET | `/api/comments/admin` | Admin | 管理端列表（分页筛选） |

### 5.10 轮播图与分类接口（v3.6.0）

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/api/banners` | ❌ | 启用中的轮播图（sort_no 升序） |
| POST | `/api/banners/upload` | Admin | 轮播图上传（`banner_` 前缀） |
| GET / POST | `/api/banners/admin` | Admin | 轮播图列表 / 新建 |
| PUT / DELETE | `/api/banners/admin/{id}` | Admin | 编辑 / 删除 |
| GET / POST | `/api/categories/admin` | Admin | 分类列表（含 item_count）/ 新建 |
| PUT / DELETE | `/api/categories/admin/{id}` | Admin | 编辑 / 删除（**被物品使用 → 400**） |

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

HTTP 状态码：`400` 参数错误 / `401` 认证失败 / `403` 权限不足 / `404` 资源不存在 / `409` 冲突 / `500` 服务器错误

---

## 6. 前端页面清单

| 路由 | 组件 | 布局 | 权限 | 说明 |
|------|------|:----:|------|------|
| `/login` | LoginView | 独立（毛玻璃） | 未登录 | 校园航拍背景 + 半透明卡片；已登录自动跳转 |
| `/register` | RegisterView | 独立（毛玻璃） | 未登录 | 同登录页风格 |
| `/items` | HomeView | DefaultLayout | 登录 | 轮播图 + 公告栏 + 统计卡片 + 筛选栏 + 卡片网格 + 「为你推荐」+ 骨架屏 |
| `/items/:id` | ItemDetailView | DefaultLayout | 登录 | 多图画廊 + 留言区 + 相似推荐 + 认领闭环操作区（申请/审批入口/脱敏联系方式）+ 举报入口 |
| `/publish` | PublishView | DefaultLayout | 登录 | 表单卡片 + 多图上传(1-3 张, 拖拽排序, 首图封面) |
| `/match` | MatchView | DefaultLayout | 登录 | 匹配面板 + 多图上传 + 证据徽章/依据文案 + 结果进度条 |
| `/claims` | ClaimsView | DefaultLayout | 登录 | 双 tab（我的申请/收到的申请）+ 同意(互斥提示)/拒绝(必填理由)/确认完成/撤销 |
| `/reports/mine` | MyReportsView | DefaultLayout | 登录 | 举报进度卡片 |
| `/admin` | AdminView | DefaultLayout | 管理员 | 物品审核(批量+设推荐) + 用户管理 + 公告(草稿/发布) + 举报/留言/轮播图/分类管理 |
| `/admin/stats` | AdminStatsView | DefaultLayout | 管理员 | 指标卡 + 找回率仪表盘 + 发布趋势 + 分类占比（含表格视图） |
| `/notifications` | NotificationsView | DefaultLayout | 登录 | 通知卡片 + 一键已读 |
| `/profile` | ProfileView | DefaultLayout | 登录 | 信息横幅 + Tab(账户/联系/历史) + 危险区域 |

### 路由守卫逻辑

```
router.beforeEach:
  requiresAuth + 未登录  → /login
  requiresGuest + 已登录 → /
  requiresAdmin + 非Admin → /
```

### 状态管理 (Pinia)

| Store | 状态 | 持久化 |
|-------|------|:------:|
| `authStore` | token, user, isAdmin | localStorage |
| `notificationStore` | unreadCount | 内存 + 路由钩子刷新 |

---

## 7. UI 设计系统

### 7.1 色彩系统

| 用途 | 色值 | CSS 变量 |
|------|------|------|
| 品牌主色 | `#1B4D3E` 深翠绿 | `--el-color-primary` |
| 背景 | `#F5F4F1` 暖灰 | `--bg-primary` |
| 卡片 | `#FFFFFF` | `--bg-card` |
| 主文字 | `#2D2B27` | `--text-primary` |
| 次文字 | `#66625A` | `--text-secondary` |
| 辅助文字 | `#8B877E` | `--text-tertiary` |
| 成功 | `#2E7D32` | `--el-color-success` |
| 警告 | `#ED6C02` | `--el-color-warning` |
| 危险 | `#D32F2F` | `--el-color-danger` |
| 失物标签 | `#E57373` (柔红) | 硬编码 |
| 拾物标签 | `#66BB6A` (柔绿) | 硬编码 |

### 7.2 阴影层级

| 层级 | 用途 | 示例 |
|------|------|------|
| `xs` | 默认卡片、按钮 | `0 1px 2px rgba(0,0,0,0.04)` |
| `sm` | 轻微提升 | 输入框悬停 |
| `md` | 卡片悬停 | 通知卡片 |
| `lg` | 对话框、弹窗 | `0 8px 28px rgba(0,0,0,0.08)` |
| `xl` | 模态框 | 确认对话框 |
| `focus` | 焦点光环 | `0 0 0 3px rgba(27,77,62,0.15)` |

### 7.3 圆角系统

`xs(4px)` → `sm(6px)` → `md(10px)` → `lg(14px)` → `xl(20px)` → `full(9999px)`

### 7.4 间距系统 (4px 网格)

`4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48` (对应 `--space-1` ~ `--space-12`)

### 7.5 字体层级

`11 / 12 / 14 / 15 / 16 / 18 / 20 / 24 / 28 / 32` (对应 `--text-xs` ~ `--text-5xl`)

### 7.6 动效规范

| 类型 | 时长 | 缓动函数 |
|------|------|------|
| 快速（hover/active） | 150ms | `cubic-bezier(0.4, 0, 0.2, 1)` |
| 基础（过渡） | 200ms | 同上 |
| 慢速（卡片悬停） | 300ms | 同上 |
| 弹簧（进度条） | 350ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` |

---

## 8. 部署指南

### 8.1 环境要求

- **Python** 3.11+
- **Node.js** 20+
- **磁盘空间** ≥ 5GB（Chinese-CLIP ViT-H-14 权重约 3.83GB；回滚后端 open_clip ViT-B-32 约 600MB）
- **操作系统** Windows / macOS / Linux

### 8.2 后端启动

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt  # 首次需要安装依赖

# 配置 .env 文件（已提供默认值）
# SECRET_KEY=your-secret-key
# MAIL_USERNAME=your-email@qq.com  (可选)
# MAIL_PASSWORD=your-smtp-password  (可选)

# 启动（首次启动会自动下载 Chinese-CLIP 权重 ~3.83GB；可置 CLIP_CN_CKPT_PATH 用本地 .pt 零网络）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 8.3 前端启动

```bash
cd lost-found-frontend
npm install        # 首次需要安装依赖
npm run dev        # 开发模式 → http://localhost:5173
npm run build      # 生产构建 → dist/
```

### 8.4 环境变量说明 (backend/.env)

```
SECRET_KEY                    JWT 签名密钥（生产环境务必修改为强随机字符串）
JWT_EXPIRATION               Token 有效期（天），默认 7
DATABASE                     SQLite 数据库文件名
UPLOAD_FOLDER                图片上传目录
BASE_URL                     前端基础 URL（用于邮件链接）
CLIP_BACKEND                 模型后端，默认 cn_clip（Chinese-CLIP ViT-H-14）；open_clip 为回滚
CLIP_DEVICE                  运行设备 auto/cpu/cuda，默认 auto（有 CUDA 用 cuda 否则 cpu）
CLIP_CN_MODEL_NAME           Chinese-CLIP 模型名，默认 ViT-H-14
CLIP_CN_EMBED_DIM            Chinese-CLIP 联合投影维度，默认 1024
CLIP_CN_USE_MODELSCOPE       权重下载走 ModelScope（默认 True，国内直连）；False 走 HF Hub
CLIP_CN_CKPT_PATH            非空则直接加载本地 .pt（运行期零网络，优先级最高）
MATCH_W_TEXT_TEXT            文-文权重（主证据），默认 0.75（2026-09-21 起）
MATCH_W_IMG_IMG              图-图权重（主证据），默认 0.75
MATCH_W_CROSS                跨模态权重（辅助证据），默认 0.25
MATCH_CROSS_REF_LO / _HI     跨模态尺度映射区间，默认 0.194 / 0.298（实测标定；仅外层加权与展示）
MATCH_DECAY_DAYS / _FLOOR    时间衰减天数 / 下限，默认 240 / 0.6（2026-09-21 调温和）
CROSS_PENALTY_ENABLED        阶段5 跨模态一致性惩罚开关，默认 True
MATCH_THRESHOLD_MANUAL       手动匹配阈值，默认 0.624956（2026-09-21 标定，内容分尺度）
MATCH_THRESHOLD_AUTO         自动匹配阈值，默认 0.733952（实测 P=91.7% / R=61.1%）
MATCH_THRESHOLD_EMAIL        邮件通知阈值，默认 0.832069（实测 P=100% / R=19.4%，样本少建议灰度）
AUTO_MATCH_ENABLED           自动推送总开关，默认 True（当前开启）
MATCH_LEGEND_HIGH            前端图例上界，默认 None → 派生为 MATCH_THRESHOLD_AUTO
MATCH_LEGEND_MID             前端图例下界，默认 None → 派生为 MATCH_THRESHOLD_MANUAL
MAX_AUTO_MATCH_NOTIFICATIONS 自动匹配推送上限，默认 3
MAIL_SERVER                  SMTP 服务器地址
MAIL_PORT                    SMTP 端口
MAIL_USERNAME                SMTP 用户名
MAIL_PASSWORD                SMTP 密码
```

> ⚠️ 三档阈值已于 **2026-09-21 用真实模型标定**（打分口径重构后首次收敛：MANUAL 0.624956 / AUTO 0.733952 / EMAIL 0.832069，内容分尺度）；样本量仍小（36 正样本，`EMAIL` 处仅 7 个正样本 → 召回 19.4%），建议持续灰度观察；复标入口 `scripts/calibrate_thresholds.py`（`--grid` + `Recall@3` 断言）。
>
> CORS 允许来源由 `main.py` 的 `allow_origin_regex`（`^http://localhost:\d+$`）控制，不是 `.env` 项。
>
> **`cn_clip` 安装注意**：须 `pip install cn_clip --no-deps`（其 `setup.py` 硬钉 `lmdb==1.3.0`，Windows 无 wheel 会编译失败；推理不需要 lmdb）。权重下载默认走 ModelScope（`CLIP_CN_USE_MODELSCOPE=True`），或置 `CLIP_CN_CKPT_PATH` 指向本地 `.pt` 使运行期零网络。

### 8.5 管理员账号创建

```bash
cd backend
python -c "
from app.database import get_db_connection
import bcrypt
pw = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
with get_db_connection() as conn:
    conn.execute('INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)', ('admin', pw, 'admin'))
    print('Admin created: admin / admin123')
"
```

---

## 9. 核心算法说明

### 9.1 CLIP 特征提取

```
图片 → Image Encoder → 1024 维 L2 归一化向量（cn_clip ViT-H-14，默认）
                     →  512 维 L2 归一化向量（open_clip ViT-B-32，回滚）
文本 → Text Encoder  → 与图像同维（同一联合投影空间；两代向量空间互不兼容）
图像 → 64×64 resize + RGB 三级量化 → 27 维颜色直方图（L1 归一化，与模型无关）
```

> **v3.4.0（R4）**：颜色直方图在**物品发布 / 换图时**即计算并持久化到 `items.color_vector`；匹配时优先读库，仅当为 NULL（老数据未回填）才回退实时计算，避免匹配热路径重复磁盘 IO。
>
> **v3.5.0（双后端）**：`CLIPService` 为兼容壳，特征提取委托给 `app/clip_backend.py` 的后端（`open_clip` / `cn_clip`）。Chinese-CLIP ViT-H-14 的 `embed_dim=1024` 是**联合投影维度**（`encode_image`/`encode_text` 的真实输出维度），**不是**视觉塔宽度 `vision_width=1280`，亦**不是** 512 维。每个 `encode_*` 在 L2 归一化后、返回前经 `_assert_embed_dim` 断言维度 == 声明值，不符即抛 `RuntimeError`。

### 9.2 加权相似度融合（三检索模式 + 主辅证据 + 五阶段）

**按查询形态分三种检索模式**（2026-09-21 重构），三种模式由「缺通道动态归一化」**自动成形**（零分支代码）：

| 查询形态 | 可用通道 | 归一化后权重 |
|---------|---------|------------|
| ① 文字检索 | 文-文（主）+ 图文跨模态（辅） | 0.75 / 0.25 |
| ② 图片检索 | 图-图（主）+ 图文跨模态（辅） | 0.75 / 0.25 |
| ③ 图文混合 | 图-图 + 文-文 + 跨模态（双向） | 0.43 / 0.43 / 0.14 |

```
通道（q=查询，t=目标；· = 余弦，向量均已 L2 归一化）：
  sim_img_img   = q_img · t_img      图像自相似（主证据，W=0.75）
  sim_text_text = q_text · t_text    文本自相似（主证据，W=0.75）
  sim_cross_t2i = q_text · t_img     查询文字 × 目标图片（描述搜图核心）
  sim_cross_i2t = q_img · t_text     查询图片 × 目标文字
  sim_cross     = 可用跨模态方向的加权平均（内权重 0.5 / 0.5，W=0.25 辅助）
  sim_color     = 【废弃】2026-09-16 起恒不参与打分

跨模态尺度映射（仅外层加权与展示；阶段5 仍用原始余弦）：
  sim_cross_mapped = clip((sim_cross − 0.194) / (0.298 − 0.194), 0, 1)   ← 实测标定区间

基础分 = Σ(wᵢ · simᵢ) / Σ(wᵢ)     （仅在双方该维度均存在时计入 wᵢ；全缺 → 0.0）

阶段1 类别/位置调节：同类 +0.05 / 异类 -0.08；同位 +0.03 / 异位 -0.04
阶段2 时间衰减：     base ×= max(0.6, 1 − 已发布天数 / 240)（2026-09-21 由 90 天·下限 0.2 调温和）
阶段3 分层阈值：     手动 0.624956 / 自动 0.733952 / 邮件 0.832069（2026-09-21 标定值）
阶段4 动态权重：     缺维按比例重分配，见上式
阶段5 跨模态一致性惩罚：仅当「文-文 ≥ 0.55 且 图-图不高」触发（真·文本撞车；原 max 条件会误伤原图自比）；
                     cc = min(可用跨模态方向)（原始余弦）；只降权、对 cc 单调，
                     因子 ∈ [0.5, 1.0]；CROSS_PENALTY_ENABLED 可一键关闭
```

**三分数分离**（2026-09-21，解决「阈值尺度」与「展示口径」两种需求）：

| 分数 | 口径 | 用途 |
|------|------|------|
| `content_score` | 不含类别/位置/时间（含尺度映射） | **阈值判定**（与标定同尺度） |
| `match_score` | 含时间衰减（阶段1-2 后） | 排序（新物品优先） |
| `reference_score` | 最强证据通道（映射后） | 展示（界面 / 通知 / 邮件） |

**证据链**：`level`（confirmed 确定为同一物品 / high_suspect 高度疑似 / related 相关 / reference 参考）+ `basis`（命中依据：图像高度一致 / 文字描述高度吻合 / 图片与描述相互印证）+ `channels`（各通道原始值，透明可解释）。

> 💡 **实测效果（真实模型 + 真实库）**：拿原图搜自己 52% → **100%**（确定为同一物品）；文字描述命中同款 58% → **96%**。`Recall@1` 由 0.75 → **0.7778**（@3/@5/@10 保持 1.0）；**AUTO/EMAIL 阈值首次标定成功**（此前多轮「结构性无解」，Precision 上界仅 0.6889）。
>
> 旧「阶段5 交叉验证」（拿两个自相似度 img>0.7/text<0.15 比大小）在 v3.5.0 已被**真跨模态一致性惩罚**取代；「三通道等权」中间态（2026-09-16）于 2026-09-21 被主辅证据权重取代。

### 9.3 自动匹配流程

```
管理员审核通过
  → 若 AUTO_MATCH_ENABLED=false 直接短路
  → BackgroundTasks 异步启动 auto_match_and_notify()
  → 查询所有异类活跃物品 (type=相反, status=active, review_status=approved)
  → 维度预检：库中向量维度 ≠ 当前模型维度 → 记 ERROR 并跳过（提示先重嵌入）
  → 逐对调用 compute_match_detail（三检索模式 + 五阶段）
  → 判定用 content_score ≥ 0.733952（MATCH_THRESHOLD_AUTO，**与标定同尺度**）
  → 按 match_score 降序，仅保留 Top-3（MAX_AUTO_MATCH_NOTIFICATIONS）
  → 批量插入 matches 表（落库 score 为 match_score）
  → 双向发送站内通知（含匹配等级 + 命中依据）
  → content_score ≥ 0.832069（MATCH_THRESHOLD_EMAIL）且有邮箱时，发送 HTML 邮件（含等级与依据）
```

> ⚠️ 2026-09-21 修复「判定用含衰减的排序分比阈值」的**尺度缺陷**：判定改用 `content_score`。实测「蓝牙耳机↔蓝牙耳机」内容分 0.9377、81 天衰减后排序分仅 0.6278 ＜ AUTO 阈值 —— 旧逻辑**永不推送**（遍历 25 组跨类型物品对通过 0 组），修复后正确进入推送（跨类别全部仍被正确挡掉）。自动推送开关当前已开启。

---

## 10. 测试报告

### 10.1 手工回归记录（历史）

> 以下为人工执行的端到端回归记录，**不可自动复现**，仅作历史留存；自动化测试见 10.2。

**测试环境**
- 日期：2026-06-29
- 后端：http://localhost:8000
- 前端：http://localhost:5173
- 数据库：SQLite (lost_found.db, 9 条物品)

**测试结果**

| # | 测试用例 | 预期 | 实际 | 结果 |
|---|---------|------|------|:--:|
| 1 | 注册新用户 | 返回 token | `success: true, token: eyJ...` | ✅ |
| 2 | 登录 | 返回 token + user | `success: true, role: user` | ✅ |
| 3 | 获取用户信息 | 返回 username | `user: e2etest` | ✅ |
| 4 | 发布物品 | 返回 item ID | `id: 26` | ✅ |
| 5 | 查看未审核物品（本人） | 可见 | `review_status: pending` | ✅ |
| 6 | 管理员审核通过 | `审核成功` | `审核成功，状态变为 approved` | ✅ |
| 7 | 检查通知（双向） | 有通知 | `count: 4` | ✅ |
| 8 | 智能匹配（文字） | 返回匹配列表 | `matches: [...]` | ✅ |
| 9 | 编辑物品 | `success: true` | `success: true` | ✅ |
| 10 | 删除物品 | `success: true` | `success: true` | ✅ |
| 11 | 密码错误登录 | 401 | `401: 密码错误` | ✅ |
| 12 | 前端构建（生产） | 零错误 | `✓ built in 768ms` | ✅ |
| 13 | SPA 路由 /login | index.html | `lang="zh-CN"` | ✅ |
| 14 | API 代理转发 | 正常 | Login OK | ✅ |
| 15 | 物品列表筛选 | 返回 items | `Total:9, Returned:3` | ✅ |

### 10.2 自动化测试（v3.3.3 新增，v3.5.0 / v3.6.0 扩容）

仓库自动化测试套件位于 `backend/tests/`，基于 pytest + FastAPI TestClient。**当前 `--collect-only` 收集 296 用例（294 通过 / 2 门控跳过）**〔数值随套件演进，以 `--junitxml` 为准〕。测试通过 `conftest.py` 夹具实现隔离：monkeypatch 数据库路径到临时文件、以确定性假向量桩替换 CLIP（永不加载真实权重）、阻断真实 SMTP、重定向上传目录。

**A. v3.4.1 基线（72 用例）**

| 文件 | 覆盖重点 | 用例数 |
|------|----------|:------:|
| `tests/test_auth.py` | 注册 / 登录 / 禁用登录 / 当前用户；**禁用用户旧 token 失效** | 8 |
| `tests/test_items.py` | 列表可见性 / get_item 字段裁剪 / 发布初始态 / **路由顺序** / match **鉴权契约（403/401）** / 认领与自标记 | 16 |
| `tests/test_admin.py` | 权限门禁 / 审核通过 / **重复审核 409** / 驳回必填理由 / 批量上限 / 不可删自己 | 7 |
| `tests/test_stats.py` | 需登录 / **北京时间今日口径** / 未审核不计 / 持久化计数器 | 4 |
| `tests/test_adversarial_auth.py` | 对抗性：禁用/注销拦截、公开接口身份降级（C1） | 6 |
| `tests/test_adversarial_stats.py` | 对抗性：时区边界、未审核不计 | 4 |
| `tests/test_adversarial_meta.py` | 对抗性：依赖声明静态守护 | 2 |
| `tests/test_adversarial_admin_toggle.py` | 对抗性：禁用管理员再启用保留 role（C2 回归守护） | 1 |
| `tests/test_adversarial_batch_fixes.py` | 对抗性：C2 / R4–R9 修复的边界固化 | 24 |

**B. v3.5.0 新增/扩展（合计较基线 +137，总收集 209）**

| 文件 | 覆盖重点 |
|------|----------|
| `tests/test_match_contract_v350.py` | `/match` 响应 `match_source` + `legend` 契约；**403/401 契约冻结不变** |
| `tests/test_cross_modal_scoring.py` | 三通道打分与缺维度动态归一化 |
| `tests/test_cross_consistency_penalty.py` | 阶段5 跨模态一致性惩罚（只降权 / ≤×0.5 / 单调 / 可开关） |
| `tests/test_embed_dim_runtime_contract.py` | `_assert_embed_dim` 运行期维度断言 |
| `tests/test_config_rollback.py` | 模型后端 config 驱动 + 回滚切换 |
| `tests/test_reembed_script.py` | 重嵌入脚本：干跑 ETA / 冷备 / 断点续跑 / 幂等 |
| `tests/test_qa_v350_math.py` / `_contract.py` / `_dimension.py` / `_precheck.py` / `_reembed_safety.py` | QA 回归：打分数学 / 接口契约 / 维度错配防线 / 打分前预检 / 重嵌入安全 |
| `tests/test_calibrate_candidates.py` | 标定候选集契约（按 `item_id` 去重 + 字段合并；锁住一次「候选重复 → Recall@K 被低估」的回归） |
| `tests/test_scoring_regression.py` | 打分口径回归（主辅权重 / 跨模态映射 / 惩罚触发 / 证据链 / 标定同口径） |
| `tests/test_calibrate_grid_summary.py` | 权重网格「并列退化」摘要（`summarize_grid` 契约） |
| `tests/test_real_clip_smoke.py` | **真实权重门控**用例（`RUN_REAL_CLIP` 未设时 skip）；本机权重已下载，设 `RUN_REAL_CLIP=1` 时 **2 例通过** |

> ⚠️ **门控跳过说明**：`test_real_clip_smoke.py` 的 2 个用例需真实 `cn_clip` 权重与 `RUN_REAL_CLIP=1`。权重（3.83GB）已在本机下载并端到端验证，故设 `RUN_REAL_CLIP=1` 时这 2 例由 **skip 转通过**；不设时仍 skip（供无权重环境 / CI 使用）。

**C. v3.6.0 新增（合计 +75，总收集 304 = 302 passed / 2 门控 skip）**

| 文件 | 覆盖重点 | 用例数 |
|------|----------|:------:|
| `tests/test_claims.py` | 认领闭环全状态流：申请校验 / 互斥审批 / 拒绝必填 / 完成联动计数器 / 撤销 / 脱敏 | 18 |
| `tests/test_reports.py` | 举报：五类校验 / pending 去重 / 管理端筛选与处理留痕 | 9 |
| `tests/test_comments.py` | 留言：可见性 / 楼中楼 / 级联删除 / 管理员隐藏 | 9 |
| `tests/test_multi_image.py` | 多图：1-3 张 / 仅封面参与检索 / `keep` 语义 / 封面变更重算 | 9 |
| `tests/test_categories.py` | 分类表化：空表回退 / 使用中删除 400 / 排序 | 7 |
| `tests/test_stats_admin.py` | 管理端统计：找回率口径 / 北京时间趋势 | 6 |
| `tests/test_similar_recommend.py` | 相似推荐：反类型 / 阈值 / 推荐位 | 6 |
| `tests/test_announcement_draft.py` | 公告草稿 / 发布 / 下架 | 6 |
| `tests/test_banners.py` | 轮播图：公开仅启用 / CRUD | 5 |

**运行方式**（在 `backend` 目录执行）：

```bash
venv\Scripts\python.exe -m pytest tests/ -v
```

> 首次运行前安装测试依赖：`venv\Scripts\python.exe -m pip install -r requirements-dev.txt`（pytest / httpx）。

---

## 11. 已知限制与后续迭代

### 11.1 已知限制

| 限制 | 影响 | 建议 |
|------|------|------|
| SQLite 写锁 | 并发写入 > 20 时性能下降 | 迁移至 PostgreSQL |
| JSON 向量存储 | 无法高效做向量相似度搜索 | 引入 pgvector/FAISS 做 ANN |
| 同步匹配 | 审核通过时 CLIP 推理阻塞响应 | 升级为 Celery 异步任务队列 |
| 邮件配置可选 | 未配置则静默跳过邮件通知 | 添加管理后台配置页 |
| ~~单张图片~~ ✅ v3.6.0 已支持多图 | 每个物品 1-3 张（首图封面；**仅封面参与向量检索**） | 已闭环（多图匹配在查询侧聚合） |
| CPU 推理 | CLIP 在 CPU 上较慢 | 生产环境建议 GPU 部署 |
| 无微信小程序 | 仅 Web 端覆盖 | 开发微信小程序端 |
| ~~颜色特征未持久化~~ ✅ v3.4.0 已修复 | 匹配时对每个候选重新计算 27 维直方图（重复磁盘 IO） | 已新增 `items.color_vector` 列持久化（评审 R4） |
| ~~同步邮件~~ ✅ v3.4.0 已修复 | 认领/驳回邮件在 async 端点内同步发送，最坏阻塞事件循环约 10s | 已改用 `BackgroundTasks`（评审 R5） |
| ~~公开物品接口不校验账号状态~~ ✅ v3.4.0 已修复 | 被禁用用户携带旧 token 仍能被解析为 viewer，看到自己的未审核物品 | 已新增 `resolve_optional_viewer()` 校验账号状态（C1） |
| ~~匹配接口未鉴权~~ ✅ v3.4.1 已修复 | `POST /api/items/match` 在后端无鉴权依赖，仅靠前端路由守卫 | 已补 `Depends(get_current_user)`（缺 token → 403 / 非法 token → 401） |
| ~~真实 Chinese-CLIP 权重未在本机下载验证~~ ✅ 已下载并端到端验证 | 权重 3.83GB 已在本机下载（ModelScope 源，`CLIP_CN_CKPT_PATH` 零网络加载）并验证：1024 维 + L2 归一 + 语义合理 + 真实 Recall@K | 已闭环（`scripts/verify_real_clip.py`；`RUN_REAL_CLIP=1` 冒烟 2 用例由 skip 转通过） |
| ~~分层阈值 AUTO/EMAIL 不可用~~ ✅ **2026-09-21 首次标定成功** | 打分口径重构（三检索模式 + 尺度映射）后正负样本分布重叠从 0.397 收窄至单通道级；`AUTO`=0.733952（P=91.7% / R=61.1%）、`EMAIL`=0.832069（P=100% / R=19.4%） | ⚠️ 样本量仍小（36 正样本，`EMAIL` 处仅 7 个正样本）；**`EMAIL` 召回低，建议灰度观察后逐步放开**；随真实数据增长持续复标 |
| **权重的「最优值」证据不足** | 2026-09-21 起权重含明确语义（**主证据 0.75 / 辅助证据 0.25**），三模式由缺通道归一化自动成形，不再是自由参数 | `--grid` 保留三维网格供探索；见 `docs/review/threshold-calibration-v3.5.0.md` §5 |
| ~~两代向量空间不兼容~~ ✅ 本库已完成重嵌入（2026-09-14） | 切模型后若未重嵌入，新旧向量比对无物理意义（已加维度防线 → HTTP 500，不再静默空集） | 已执行 `scripts/reembed_all_vectors.py` 全量重嵌入（冷备 `lost_found.db.bak-20260914121815` + `_exit_code` 守卫，6 条全部 1024 维 + L2 归一）；`/match` 端到端实测恢复 HTTP 200 |
| **评测集规模小** | `eval_set_v3.5.0.json` **84 对**（去除 6 对同图自比退化对后**有效 36 正 / 42 负**，n=78），置信区间仍宽 | 随真实物品增长持续扩充复标；不得表述为「已可靠标定」 |
| ~~重嵌入脚本「假绿迁移」缺陷~~ ✅ 已修 | 真实 `--dry-run` 暴露 12 次 `AttributeError`、`ok=0`，但 `main()` 恒返回 0 → 真跑会「成功退出」但库中分毫未动（运维误以为已迁移） | `_ServiceEncoderAdapter` 对齐冻结服务接口 + `_exit_code` 守卫（`failed_encode>0` → 2、`ok==0 且 total>0` → 3、`--dry-run` 仍 0）；守卫 `tests/test_reembed_encoder_wiring.py` 8 例 |

### 11.2 版本演进

#### V3.1 — 体验增强 ✅ 已完成
- [x] 骨架屏组件化
- [x] 深色模式
- [x] 个人中心页面
- [x] 物品认领确认流程
- [x] 头像上传

#### V3.1.1 — 补全 + 修复 ✅ 已完成
- [x] 头像上传（数据库迁移 + API + UI）
- [x] 认领/归还邮件双向通知
- [x] 物品详情页 UI 重构
- [x] 一键已读全部通知
- [x] 多处 UI 细节修复

#### V3.2 — 需求驱动迭代 ✅ 已完成
- [x] 登录后按角色自动跳转
- [x] 认领/归还按钮文案优化
- [x] 个人中心：修改用户名 + 注销账号
- [x] 管理面板：审核驳回通知+邮件
- [x] 管理面板：用户管理
- [x] 数据看板：统计卡片 + 分类占比 API

#### V3.3 — 逻辑收敛 + 体验重构 ✅ 已完成 (2026-06-30)
- [x] 去除访客角色（所有页面需登录）
- [x] 禁用用户登录拦截（403）
- [x] 认领/归还流程重构（自标记替代确认/拒绝）
- [x] 认领通知含申请人手机号
- [x] 个人中心重设计（砍头像 + Tab 分段 + 历史记录）
- [x] 批量审核通过（AdminView 多选 + 一键通过）
- [x] 统计卡片改为"总计找回"
- [x] 公告栏整合到首页
- [x] 用户逻辑删除（管理员操作）

#### V3.3.1 — Bug 修复 ✅ 已完成 (2026-06-30)
- [x] 统计卡片过滤未审核物品（stats.py SQL 加 review_status 条件）
- [x] 展示中卡片数据防御性绑定（HomeView loadStats 显式字段映射）
- [x] 管理员全选框改用表格内置 selection（AdminView 移除自定义 checkbox）
- [x] 批量审核路由移至参数化路径之前（admin.py 路由重排）
- [x] 认领弹窗文案根据物品类型动态生成（ItemDetailView handleClaim）
- [x] 标记按钮异常处理分离（ItemDetailView 分离 ElMessageBox 与 API catch）
- [x] 已认领物品从主列表隐藏（items.py SQL 排除 claimed/closed）
- [x] mark-claimed 路由修正（items.py 移至 PUT /{item_id} 之前）
- [x] 自动匹配通知 Row→dict 修复（match_service.py）

#### V3.3.2 — 匹配算法增强 + UI 升级 ✅ 已完成 (2026-07-02)
- [x] 五阶段智能匹配算法（类别/位置调节 + 时间衰减 + 分层阈值 + 动态权重 + 交叉验证）
- [x] 颜色增强（27 维 RGB 直方图 + 余弦相似度）
- [x] 公告系统 + 物品管理统一 Tab
- [x] Inter 字体 + 1440px / 1920px 桌面适配
- [x] 统计计数器持久化（`stats_counters` 表）

#### V3.3.3 — 工程加固（文档与代码对齐） ✅ 已完成 (2026-09-12)
- [x] 新增自动化测试套件（`backend/tests/`，当时 45 用例全绿；v3.4.0 已扩至 70）
- [x] P0 修复 R1：禁用用户已签发 JWT 立即失效（`dependencies/auth.py` 增补 disabled 拦截）
- [x] P0 修复 R2：「今日失物/今日拾物」改为北京时间口径（`stats.py` 半开区间比较）
- [x] P0 修复 R3：`requirements.txt` 直接声明 bcrypt，移除未使用的 passlib
- [x] 文档对齐：PROJECT / README / CHANGELOG 与代码一致化（详见 `docs/archive/doc-sync-2026-09-12.md`）

#### V3.4.0 — 语义与性能加固 ✅ 已完成 (2026-09-12)
- [x] 数据结构：`users` 新增 `status`（active / disabled / deleted）；`items` 新增 `color_vector`（幂等迁移 `database.py:126-143`）
- [x] **C2** 账户状态语义拆分：`role` 收敛为 user/admin，`toggle_status` 只改 `status`、保留 `role`（修复「禁用管理员再启用降级」）
- [x] **C1** 公开接口账号状态校验：新增 `resolve_optional_viewer()`，禁用/注销一律降级匿名
- [x] **R4** 颜色特征持久化：发布/换图时落库，匹配优先读库、NULL 回退；新增回填脚本 `backend/scripts/backfill_color_vectors.py`
- [x] **R5** 邮件异步化：认领/驳回邮件改 `BackgroundTasks`
- [x] **R6** 路由健壮化：动态路径参数改用类型转换器 `{id:int}`
- [x] **R7** 去静默异常：移除 `asyncio.create_task` + 裸 `except: pass`；`batch_items` 的 `count` 取分支真实 `rowcount`
- [x] **R9** 请求体 Pydantic 化：6 个端点接入宽松模型，错误码仍为 400（不退化 422）
- [x] **R10** 清理与版本：删除零引用模型、未生效 `CORS_ORIGINS`、`LocalhostRegexOrigin`；`APP_VERSION = 3.4.0`
- [x] O2 自锁保护：禁止管理员禁用 / 删除自己
- [x] 自动化测试扩至 **70 用例**（新增对抗性用例固化 C1 / C2 / R4–R9）

#### V3.4.1 — 契约补齐 ✅ 已完成 (2026-09-12)
- [x] `POST /api/items/match` 补齐鉴权：`match_items(req, current_user: dict = Depends(get_current_user))`（`app/api/items.py:458`）
- [x] 契约：缺 `Authorization` 头 → 403；token 非法 / 过期 → 401
- [x] 自动化测试：更新 3 条路由顺序用例 + 新增 2 条鉴权契约用例（`tests/test_items.py` 14 → 16），**合计 72 用例全通过**
- [x] `APP_VERSION` → `3.4.1`

#### V3.5.0 — 中文化模型 + 图文跨模态检索 ✅ 已完成 (2026-09-14)
- [x] **模型双后端抽象**：新增 `app/clip_backend.py`（`ClipBackend` 协议 + `OpenClipBackend` + `ChineseClipBackend` + `get_backend()` 工厂）；默认 `cn_clip` → **Chinese-CLIP ViT-H-14**（**1024 维**联合投影），`open_clip` → **ViT-B-32**（**512 维**）可回滚；未知取值抛 `RuntimeError` 禁止静默降级
- [x] **三通道等权打分**（2026-09-16 修订，取代原四通道）：①文-文 ②图文跨模态（`q_text·t_img` 与 `q_img·t_text` 各 0.5 双向合并）③图-图；三通道权重均为 1.0、缺通道动态归一化（= 可用通道算术平均）；**颜色通道废弃**
- [x] **阶段5 重构**：由「两自相似比大小」升级为**真跨模态一致性惩罚**（`cc = min(可用跨模态方向)`，仅当 `max(sim_ii,sim_tt) ≥ 0.55` 触发，只降权、≤×0.5、可 `CROSS_PENALTY_ENABLED` 关闭）
- [x] **阈值/权重 config 化**：手动 0.35 / 自动 0.55 / 邮件 0.70（**初值待标定**）
- [x] **接口契约（不新增端点）**：`/match` 结果项新增 `match_source`（text/image/mixed），响应新增 `legend: {high, mid}`（由阈值派生）；**403/401 契约冻结不变**
- [x] **三个运维脚本**：`reembed_all_vectors.py`（冷备 / `--dry-run` ETA / 断点续跑 / 幂等）、`calibrate_thresholds.py`（PR 曲线 + Recall@1/3/5/10 + `--grid` 权重网格）、`backfill_color_vectors.py`
- [x] **评测集**：`backend/eval/eval_set_v3.5.0.json`（初建 **70 对 = 30 正 / 40 负**；剔除 6 对同图自比退化对后有效 24 正 / 40 负，n=64；→ 2026-09-14 扩充轮后 **84 对**，有效 36 正 / 42 负，n=78）
- [x] **维度错配运行期防线**：编码后 `_assert_embed_dim` 断言 + `/match` 打分前维度预检 → **HTTP 500**（不再静默空集）
- [x] 自动化测试扩至 **209 用例（207 通过 / 2 门控跳过）**
- ✅ **已用真实模型验证**：真实 Chinese-CLIP 权重（3.83GB）已在本机下载并端到端验证；⚠️ **分层阈值 `AUTO`/`EMAIL` 仍不可用**：扩充评测集复标后 Precision 上界 0.6129 → 0.6889，仍 ＜ 0.90（**结构性无解**），权重只能给方向性结论 —— 详见 `docs/review/threshold-calibration-v3.5.0.md`
- ✅ **生产库全量重嵌入已执行**（2026-09-14，用户授权）：冷备 `lost_found.db.bak-20260914121815` → 6 条全部重算为 1024 维（`ok=6/failed_encode=0`，EXIT=0，34s，`color_vector` 逐字节未动）→ 端到端实测 `POST /api/items/match` **HTTP 200**（查询「蓝牙耳机」命中同类 item68，score=0.3872 过手动阈值 0.35）；`AUTO_MATCH_ENABLED=false` 灰度保持，`AUTO`/`EMAIL` 阈值回填（门禁步骤 8）仍待评测集扩充后复标

#### V3.6.0 — 打分口径重构 + 社区化融合 ✅ 已完成 (2026-10-14)
- [x] **打分口径重构**：按查询形态三种检索模式（文字/图片/图文混合）；权重改「主证据 + 辅助证据」（同模态 0.75 / 跨模态 0.25，缺通道归一化自动成形）
- [x] **跨模态尺度映射**：0.194→0 / 0.298→1 线性拉伸（仅外层加权与展示；阶段5 仍用原始余弦）
- [x] **证据链**：`level` / `basis` / `channels` + 三分数分离（`content_score` 判定 / `match_score` 排序 / `reference_score` 展示）
- [x] **时间衰减失效修复**（naive/aware 相减 TypeError 被静默吞掉 → `utils/time_utils.days_since_utc()`）+ 参数调温和（90→240 天、下限 0.2→0.6）
- [x] **三档阈值首次标定成功**：MANUAL 0.624956 / AUTO 0.733952 / EMAIL 0.832069（内容分尺度）；`Recall@1` 0.75 → 0.7778
- [x] **自动匹配尺度修正**：判定改 `content_score`、排序 `match_score`、展示 `reference_score`；通知/邮件含等级与依据；开关开启
- [x] **融合参考项目八大设计**：认领闭环 / 举报体系 / 留言互动 / 多图上传（1-3 张）/ 管理端统计看板 / 相似推荐与推荐位 / 证据链前端可视化 / 内容运营（轮播图·分类管理·公告草稿）
- [x] **DB 迁移**：items 表重建扩展 status 枚举（新增 `claiming`，显式列名对齐防 `SELECT *` 错位）+ 5 张新表（claims / reports / comments / banners / categories）+ items 3 列（cover_image / images / is_recommend）
- [x] 自动化测试扩至 **313 用例（311 通过 / 2 门控跳过）**
- [x] `APP_VERSION` → `3.6.0`；PROJECT / SRS / README / docs 索引同步

#### V3.5 — 体验飞升（计划中）
- [ ] 微信小程序端
- [ ] 向量数据库迁移（pgvector 或 FAISS）
- [x] 多图上传（v3.6.0 已实现 1-3 张）
- [ ] AI 防冒领验证
- [ ] 激励机制（积分/排行榜）
- [ ] 多模型融合（CLIP + DINOv2）

#### V4.0 — 架构升级（长期）
- [ ] PostgreSQL + pgvector 全面迁移
- [ ] Celery + Redis 异步任务队列
- [ ] 对象存储（OSS/S3）
- [ ] 移动端 PWA 支持
- [ ] OAuth 登录（微信/企业微信）
- [ ] 多校区支持

---

> **文档维护者**：开发团队  
> **最后更新**：2026-10-14  
> **相关文档**：[文档索引](docs/README.md) | [SRS](SRS.md) | [v3.3 PRD](docs/product/PRD-v3.3.md) | [v3.5.0 增量 PRD](docs/product/PRD-v3.5.0-incremental.md) | [竞品分析报告](docs/product/competitive-analysis.md) | [用户角色与场景](docs/product/personas-and-scenarios.md)  
> **质量文档**：[架构评审报告 2026-09-12](docs/archive/architecture-review-2026-09-12.md) | [文档与代码同步说明](docs/archive/doc-sync-2026-09-12.md) | [增量修复设计](docs/archive/design-fix-batch-2026-09-12.md) | [v3.4.0 变更总结](docs/archive/v3.4.0-change-summary-2026-09-12.md) | [v3.5.0 增量架构设计](docs/archive/v3.5.0-incremental-design.md) | [v3.5.0 QA 回归](docs/review/qa-v3.5.0-regression-2026-09-13.md)
