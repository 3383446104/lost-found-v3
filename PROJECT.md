# 校园失物检索平台 — 项目文档

> 版本：v3.5.0 | 日期：2026-09-14 | 技术栈：FastAPI + Vue 3 + CLIP（Chinese-CLIP / open_clip 双后端）
>
> **v3.3 核心变更**：去除访客 | 自标记认领 | 个人中心重构 | 批量审核 | 总计找回 | 历史记录
> **v3.3.1 修复**：统计过滤 | 批量审核路由 | 认领文案 | 列表过滤 | mark-claimed 路由 | 自动匹配通知
> **v3.3.3 工程加固**：新增自动化测试套件 | P0 修复（禁用用户鉴权 / 今日统计时区 / 依赖声明）| 文档与代码对齐（详见 [CHANGELOG](CHANGELOG.md) 与本轮评审报告）
> **v3.4.0 语义与性能加固**：账户状态拆分（`role` × `status`）| 颜色特征持久化（`items.color_vector`）| 公开接口账号状态校验 | 邮件异步化 | 路由 `:int` 健壮化 | 请求体 Pydantic 化 | 死代码清理 | 自动化测试扩至 **70 用例**
> **v3.4.1 契约补齐**：补齐 `POST /api/items/match` 鉴权（需登录；缺 token → 403 / 非法 token → 401）| 自动化测试扩至 **72 用例**
> **v3.5.0 中文化模型 + 跨模态检索**：默认模型换为 **Chinese-CLIP ViT-H-14**（`cn_clip`，`open_clip ViT-B-32` 可回滚）| 启用 **img·text 跨模态**四通道打分 | 阶段5 升级为**真跨模态一致性惩罚** | 阈值/权重 config 化并重标定 | `/match` 结果新增 `match_source`、响应新增 `legend` | 全量重嵌入 / 标定 / 颜色回填三个脚本 | 自动化测试扩至 **185 用例（183 通过 / 2 门控跳过）**。⚠️ **真实权重未在本机下载验证，结论均为打桩验证；阈值与权重为初值待标定**（详见 §9 / §11）

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
| **认领/归还流程** | 失物→"我要归还"、拾物→"我要认领"，通知含申请人手机号；发布者自行标记"已找回/已认领" |
| **管理员审核** | 审核通过/驳回+邮件通知；一键批量通过；用户管理（角色/禁用/逻辑删除） |
| **数据看板** | 首页统计卡片（展示中/今日失物/今日拾物/总计找回） |
| **个人中心** | Tab 分段式布局：账户设置 + 联系方式 + 历史记录；首字母头像(纯展示)；注销账号 |
| **完整闭环** | 发布 → 审核 → 匹配 → 通知 → 认领/归还 → 自标记 → 历史记录 |

### 1.3 用户角色

| 角色 | 权限 |
|------|------|
| **普通用户** | 浏览物品；发布/编辑/删除自己的物品；使用智能匹配；申请认领/归还；标记自己物品"已找回/已认领"；查看通知；个人中心（含历史记录） |
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
│   ├── scripts/            ← 运维脚本（reembed_all_vectors.py 全量重嵌入 / calibrate_thresholds.py 阈值标定 / backfill_color_vectors.py 颜色向量回填）
│   ├── eval/               ← 评测集（eval_set_v3.5.0.json，60 对构造样本）
│   ├── tests/              ← 自动化测试套件（185 用例）
│   │   ├── conftest.py
│   │   ├── test_auth.py / test_items.py / test_admin.py / test_stats.py
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
│       ├── api/            ← 路由（auth/items/admin/notifications/stats/announcements）
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
        ├── views/           ← 9 个页面组件
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

### 3.3 智能匹配模块 (FR-MATCH)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-MATCH-01 | 以图搜图 | ✅ POST /api/items/match | ✅ MatchView | ✅ |
| FR-MATCH-02 | 以文搜图（**真跨模态**：查询文字 × 目标图片） | ✅ POST /api/items/match | ✅ MatchView | ✅ |
| FR-MATCH-03 | 图文混合匹配 | ✅ 四通道加权融合 | ✅ MatchView | ✅ |
| FR-MATCH-04 | 加权相似度（图-图 0.35 + **跨模态 0.35** + 文-文 0.15 + 色 0.15，缺维度动态归一化） | ✅ compute_weighted_similarity | — | ✅ |
| FR-MATCH-05 | 结果排序（Top 20） | ✅ sorted[:20] | ✅ 卡片列表 | ✅ |
| FR-MATCH-06 | 匹配范围限定（已审核+活跃） | ✅ WHERE status='active' | — | ✅ |
| FR-MATCH-07 | 可配置阈值（手动 0.35 / 自动 0.55 / 邮件 0.70 三级分层，均为**初值待标定**） | ✅ MATCH_THRESHOLD_MANUAL / _AUTO / _EMAIL | — | ✅ |
| FR-MATCH-08 | 匹配来源标注（`match_source` ∈ text/image/mixed） | ✅ 随每条结果下发 | ✅ 结果卡片来源标签 | ✅ |
| FR-MATCH-09 | 前端图例随阈值派生（响应 `legend: {high, mid}`） | ✅ resolve_legend() | ✅ 结果图例 | ✅ |

### 3.4 管理员审核模块 (FR-ADMIN)

| 编号 | 需求 | 后端 | 前端 | 状态 |
|------|------|:----:|:----:|:----:|
| FR-ADMIN-01 | 待审核列表（分页） | ✅ GET /api/admin/reviews | ✅ AdminView | ✅ |
| FR-ADMIN-02 | 审核通过（→active，触发匹配） | ✅ PUT /api/admin/reviews/{id} | ✅ AdminView | ✅ |
| FR-ADMIN-03 | 审核驳回（→rejected + 理由+通知+邮件） | ✅ 驳回理由必填验证 | ✅ 驳回 Dialog | ✅ |
| FR-ADMIN-04 | 自动匹配推送（≥0.65） | ✅ BackgroundTasks 异步 | — | ✅ |
| FR-ADMIN-05 | 批量审核通过 | ✅ POST batch-approve | ✅ 多选+工具栏 | ✅ |

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

### 3.6 非功能需求覆盖

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
| 物品管理 | 9 | 9 | 100% |
| 智能匹配 | 9 | 9 | 100% |
| 管理员审核 | 4 | 4 | 100% |
| 消息通知 | 6 | 6 | 100% |
| 非功能需求 | 13 | 12 | 92% |
| **总计** | **47** | **46** | **98%** |

---

## 4. 数据库设计

> **v3.4.0 迁移**：`init_db()` 启动时经 `PRAGMA table_info` 守卫执行两段**幂等**迁移——为 `users` 增补 `status`（在「加列」分支内一次性把历史 `role='disabled'/'deleted'` 映射到 `status` 并把 `role` 复位为 `user`），为 `items` 增补 `color_vector`（老数据置 NULL，由 `backend/scripts/backfill_color_vectors.py` 回填）。见源码 `app/database.py:126-143`。

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
| image_path | TEXT | | 图片路径 |
| image_vector | TEXT | | CLIP 图像特征 (JSON) |
| text_vector | TEXT | | CLIP 文本特征 (JSON) |
| color_vector | TEXT | | 27 维颜色直方图 (JSON，L1 归一化)（**v3.4.0 新增**，评审 R4） |
| contact | TEXT | | 联系方式 |
| location | TEXT | | 地点 |
| status | TEXT | CHECK(6 states) | pending/active/claimed/done/rejected/closed |
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
| POST | `/api/items/` | ✅ | 发布物品（FormData） |
| GET | `/api/items/` | ❌ | 物品列表（分页+筛选） |
| GET | `/api/items/{id}` | ❌ | 物品详情（公开；内部解析 token，未审核物品仅发布者/管理员可见） |
| PUT | `/api/items/{id}` | ✅ | 编辑物品（本人/管理员） |
| DELETE | `/api/items/{id}` | ✅ | 删除物品（本人/管理员） |
| POST | `/api/items/match` | ✅ | 智能匹配（JSON body，需登录） |
| POST | `/api/items/temp-upload` | ✅ | 临时上传图片 |
| POST | `/api/items/{id}/claim` | ✅ | 申请认领/归还（通知含申请人手机号） |
| PUT | `/api/items/{id}/mark-claimed` | ✅ | 发布者标记物品已找回/已认领 |
| GET | `/api/items/categories` | ❌ | 类别列表（公开） |
| GET | `/api/items/uploads/{filename}` | ❌ | 访问图片（公开） |

> **v3.4.0（C1）**：公开端点 `GET /api/items/` 与 `GET /api/items/{id}` 的身份解析统一走 `resolve_optional_viewer()`——仅当 token 合法且 `status='active'` 时才认作 viewer，`disabled` / `deleted` 一律**降级为匿名**，避免其以「属主」身份看到自己的未审核物品（见 `app/dependencies/auth.py:89-113`）。
>
> **v3.4.1**：`POST /api/items/match` 由**无鉴权裸端点**补齐为需登录——缺 `Authorization` 头 → 403 `{"detail":"Not authenticated"}`（`HTTPBearer` auto_error）；token 非法 / 过期 → 401 `{"detail":"无效或过期的 Token"}`（见 `app/api/items.py` 的 `match_items`）。
>
> **v3.5.0**：`POST /api/items/match` 结果项**新增 `match_source`**（∈ `text` / `image` / `mixed`），响应顶层**新增 `legend: {high, mid}`**——`legend.high` 默认派生自 `MATCH_THRESHOLD_AUTO`、`legend.mid` 默认派生自 `MATCH_THRESHOLD_MANUAL`（可由 `MATCH_LEGEND_HIGH` / `MATCH_LEGEND_MID` 覆盖），彻底消除前端硬编码图例（见 `resolve_legend()`）。**未新增任何端点**。

**列表查询参数：** `type`, `category`, `keyword`, `user_id`, `limit`, `offset`

**匹配请求体：**
```json
{
  "image_path": "temp_xxx.jpg (可选)",
  "text": "描述文字 (可选)",
  "target_type": "lost | found",
  "threshold": 0.35,
  "category": "类别 (可选，用于类别增强)",
  "location": "地点 (可选，用于位置增强)"
}
```

> `threshold` 省略时默认取 `MATCH_THRESHOLD_MANUAL`（**0.35**，v3.5.0 初值，待标定）。
>
> **匹配响应（v3.5.0）：**
> ```json
> {
>   "matches": [
>     { "id": 80, "title": "黑色中性笔", "similarity": 0.61,
>       "match_source": "mixed", "...": "其余字段略" }
>   ],
>   "legend": { "high": 0.55, "mid": 0.35 }
> }
> ```
> `matches` 最多返回 Top-20；`match_source` 按**查询实际可用输入**判定：仅文 → `text`、仅图 → `image`、图文 → `mixed`。

### 5.3 管理员接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/api/admin/reviews` | Admin | 待审核列表（分页） |
| PUT | `/api/admin/reviews/{id}` | Admin | 审核操作（通过/驳回+通知+邮件） |
| POST | `/api/admin/reviews/batch-approve` | Admin | 批量审核通过 |
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
| GET | `/api/announcements` | ❌ | 公告列表（公开；`all=true` 且为管理员时可见全量） |
| POST | `/api/announcements` | Admin | 发布公告 |
| PUT | `/api/announcements/{ann_id}` | Admin | 编辑公告 |
| DELETE | `/api/announcements/{ann_id}` | Admin | 删除公告 |

### 5.6 数据统计接口

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| GET | `/api/stats/dashboard` | 首页看板（展示中/今日失物/今日拾物/总计找回 + 分类占比） | 是 |

> 「今日失物/今日拾物」以**北京时间（UTC+8）当日 00:00–24:00** 为口径统计。`items.created_at` 由 SQLite `CURRENT_TIMESTAMP` 写入 UTC 时间，接口内部换算为对应的 UTC 半开区间后再比较。

> **端点总数**：认证 6 + 物品 11 + 管理员 10 + 通知 4 + 公告 4 + 统计 1 = **36**。

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
| `/items` | HomeView | DefaultLayout | 登录 | 公告栏 + 统计卡片 + 筛选栏 + 卡片网格 + 骨架屏 |
| `/items/:id` | ItemDetailView | DefaultLayout | 登录 | 两栏详情 + 自标记操作区 |
| `/publish` | PublishView | DefaultLayout | 登录 | 表单卡片 + 图片上传 |
| `/match` | MatchView | DefaultLayout | 登录 | 匹配面板 + 结果进度条 |
| `/admin` | AdminView | DefaultLayout | 管理员 | 物品审核(含批量) + 用户管理(含逻辑删除) + 公告管理 |
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
MATCH_W_IMG_IMG              图像自相似权重，默认 0.35
MATCH_W_CROSS                跨模态权重，默认 0.35
MATCH_W_TEXT_TEXT            文本自相似权重，默认 0.15
MATCH_W_COLOR                颜色权重，默认 0.15
CROSS_PENALTY_ENABLED        阶段5 跨模态一致性惩罚开关，默认 True
MATCH_THRESHOLD_MANUAL       手动匹配阈值，默认 0.35（v3.5.0 初值，原 0.20）
MATCH_THRESHOLD_AUTO         自动匹配通知阈值，默认 0.55（v3.5.0 初值，原 0.65）
MATCH_THRESHOLD_EMAIL        邮件通知阈值，默认 0.70（v3.5.0 初值，原 0.75）
AUTO_MATCH_ENABLED           自动推送总开关，默认 True（灰度期置 false）
MATCH_LEGEND_HIGH            前端图例上界，默认 None → 派生为 MATCH_THRESHOLD_AUTO
MATCH_LEGEND_MID             前端图例下界，默认 None → 派生为 MATCH_THRESHOLD_MANUAL
MAX_AUTO_MATCH_NOTIFICATIONS 自动匹配推送上限，默认 3
MAIL_SERVER                  SMTP 服务器地址
MAIL_PORT                    SMTP 端口
MAIL_USERNAME                SMTP 用户名
MAIL_PASSWORD                SMTP 密码
```

> ⚠️ 上述阈值/权重均为 **v3.5.0 初值、尚未用真实模型标定**；须经 `scripts/calibrate_thresholds.py`（`--grid` + `Recall@3` 断言）回填后才可视为收敛。
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

### 9.2 加权相似度融合（四通道跨模态 + 五阶段）

基础融合为**四通道加权**（图像自相似 `sim_img_img` 0.35 + **跨模态 `sim_cross` 0.35** + 文本自相似 `sim_text_text` 0.15 + 颜色 `sim_color` 0.15），并对缺失维度做
**动态权重归一化**——按比例把缺失维度的权重重分配给可用维度，保证权重和恒为 1.0，
使「纯文本/纯图像匹配」不被整体降权（否则可能永远够不到阈值）：

```
通道（q=查询，t=目标；· = 余弦，向量均已 L2 归一化）：
  sim_img_img   = q_img · t_img      图像自相似
  sim_text_text = q_text · t_text    文本自相似
  sim_cross_t2i = q_text · t_img     查询文字 × 目标图片（描述搜图核心）
  sim_cross_i2t = q_img · t_text     查询图片 × 目标文字
  sim_cross     = 可用跨模态方向的加权平均（内权重 W_CROSS_T2I / W_CROSS_I2T = 0.5 / 0.5）
  sim_color     = cos(q_color, t_color)

基础分 = Σ(wᵢ · simᵢ) / Σ(wᵢ)     （仅在双方该维度均存在时计入 wᵢ；全缺 → 0.0）

阶段1 类别/位置调节：同类 +0.05 / 异类 -0.08；同位 +0.03 / 异位 -0.04
阶段2 时间衰减：     base ×= max(0.2, 1 − 已发布天数 / 90)
阶段3 分层阈值：     由调用方按场景施加（手动 0.35 / 自动 0.55 / 邮件 0.70，均为初值待标定）
阶段4 动态权重：     缺维按比例重分配，见上式
阶段5 跨模态一致性惩罚：真跨模态——cc = min(可用跨模态方向)；
                     仅当 max(sim_ii, sim_tt) ≥ 0.55 触发；只降权、对 cc 单调，
                     因子 ∈ [0.5, 1.0]（腰斩上限）；CROSS_PENALTY_ENABLED 可一键关闭
```

> ⚠️ 四个外层权重（0.35/0.35/0.15/0.15）、跨模态内权重（0.5/0.5）、阶段1/5 各参数与三档阈值均为 **v3.5.0 初值，尚未用真实模型标定**，须经 `scripts/calibrate_thresholds.py`（`--grid` + `Recall@3 不下降` 断言）回填。
>
> 旧「阶段5 交叉验证」（拿两个自相似度 img>0.7/text<0.15 比大小）在 v3.5.0 已被上述**真跨模态一致性惩罚**取代。

### 9.3 自动匹配流程

```
管理员审核通过
  → 若 AUTO_MATCH_ENABLED=false 直接短路（灰度期）
  → BackgroundTasks 异步启动 auto_match_and_notify()
  → 查询所有异类活跃物品 (type=相反, status=active, review_status=approved)
  → 维度预检：库中向量维度 ≠ 当前模型维度 → 记 ERROR 并跳过（提示先重嵌入）
  → 逐对计算四通道跨模态 + 五阶段加权相似度
  → 筛选 ≥ 0.55（MATCH_THRESHOLD_AUTO，初值）的匹配
  → 按相似度降序，仅保留 Top-3（MAX_AUTO_MATCH_NOTIFICATIONS）
  → 批量插入 matches 表
  → 双向发送站内通知（新物品发布者 + 目标物品拥有者）
  → 相似度 ≥ 0.70（MATCH_THRESHOLD_EMAIL，初值）且有邮箱时，发送 HTML 邮件
```

> ⚠️ v3.5.0：自动推送量取决于**新阈值**，三档阈值均为初值，**尚未用真实模型标定**。

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

### 10.2 自动化测试（v3.3.3 新增，v3.5.0 扩容）

仓库自动化测试套件位于 `backend/tests/`，基于 pytest + FastAPI TestClient。**当前 `--collect-only` 收集 185 用例（183 通过 / 2 门控跳过）**〔数值随套件演进，以 `--junitxml` 为准〕。测试通过 `conftest.py` 夹具实现隔离：monkeypatch 数据库路径到临时文件、以确定性假向量桩替换 CLIP（永不加载真实权重）、阻断真实 SMTP、重定向上传目录。

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

**B. v3.5.0 新增/扩展（合计较基线 +113，总收集 185）**

| 文件 | 覆盖重点 |
|------|----------|
| `tests/test_match_contract_v350.py` | `/match` 响应 `match_source` + `legend` 契约；**403/401 契约冻结不变** |
| `tests/test_cross_modal_scoring.py` | 四通道跨模态打分与缺维度动态归一化 |
| `tests/test_cross_consistency_penalty.py` | 阶段5 跨模态一致性惩罚（只降权 / ≤×0.5 / 单调 / 可开关） |
| `tests/test_embed_dim_runtime_contract.py` | `_assert_embed_dim` 运行期维度断言 |
| `tests/test_config_rollback.py` | 模型后端 config 驱动 + 回滚切换 |
| `tests/test_reembed_script.py` | 重嵌入脚本：干跑 ETA / 冷备 / 断点续跑 / 幂等 |
| `tests/test_qa_v350_math.py` / `_contract.py` / `_dimension.py` / `_precheck.py` / `_reembed_safety.py` | QA 回归：打分数学 / 接口契约 / 维度错配防线 / 打分前预检 / 重嵌入安全 |
| `tests/test_real_clip_smoke.py` | **真实权重门控**用例（`RUN_REAL_CLIP` 未设时 skip）；⚠️ **本机从未下载真实权重，默认 2 例 skipped** |

> ⚠️ **门控跳过说明**：`test_real_clip_smoke.py` 的 2 个用例需真实 `cn_clip` 权重与 `RUN_REAL_CLIP=1`，**本机未下载**，故长期 skip——这也意味着「已用真实模型验证」这一档**为空**，v3.5.0 全部结论均为**打桩验证**。

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
| 单张图片 | 每个物品仅支持 1 张图 | 扩展为多图上传 |
| CPU 推理 | CLIP 在 CPU 上较慢 | 生产环境建议 GPU 部署 |
| 无微信小程序 | 仅 Web 端覆盖 | 开发微信小程序端 |
| ~~颜色特征未持久化~~ ✅ v3.4.0 已修复 | 匹配时对每个候选重新计算 27 维直方图（重复磁盘 IO） | 已新增 `items.color_vector` 列持久化（评审 R4） |
| ~~同步邮件~~ ✅ v3.4.0 已修复 | 认领/驳回邮件在 async 端点内同步发送，最坏阻塞事件循环约 10s | 已改用 `BackgroundTasks`（评审 R5） |
| ~~公开物品接口不校验账号状态~~ ✅ v3.4.0 已修复 | 被禁用用户携带旧 token 仍能被解析为 viewer，看到自己的未审核物品 | 已新增 `resolve_optional_viewer()` 校验账号状态（C1） |
| ~~匹配接口未鉴权~~ ✅ v3.4.1 已修复 | `POST /api/items/match` 在后端无鉴权依赖，仅靠前端路由守卫 | 已补 `Depends(get_current_user)`（缺 token → 403 / 非法 token → 401） |
| **真实 Chinese-CLIP 权重未在本机下载验证** | 权重约 3.83GB（本机带宽约 2.2 小时），**从未实际加载**；v3.5.0 全部结论均为**打桩验证** | 上线前须在有带宽/有 GPU 的环境跑 `RUN_REAL_CLIP=1` 冒烟用例与标定脚本，回填阈值 |
| **阈值 / 权重为初值，尚未标定** | `MATCH_THRESHOLD_*`（0.35/0.55/0.70）、四通道权重、阶段5 参数均为**初值**，未经真实模型收敛 | 运行 `scripts/calibrate_thresholds.py --with-penalty --grid` 后回填 `.env`；`Recall@3 < 0.90` 按阻塞性发现处理 |
| **跨模态结果为打桩验证** | 跨模态四通道 + 阶段5 惩罚的**数值行为**仅在假向量桩下被断言；真实分布下的排序质量未知 | 同上，须用真实权重 + 评测集复跑 |
| **两代向量空间不兼容** | 切模型后若未重嵌入，新旧向量比对无物理意义（已加维度防线 → HTTP 500，不再静默空集） | 切换后**必须**先 `scripts/reembed_all_vectors.py` 全量重嵌入（冷备 + 幂等 + 断点续跑） |
| **评测集规模小** | `eval_set_v3.5.0.json` 仅 **60 对**（去除 6 对同图自比退化对后**有效 24 正 / 30 负**），置信区间宽 | 随真实物品增长持续扩充复标；不得表述为「已可靠标定」 |

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
- [x] 文档对齐：PROJECT / README / CHANGELOG 与代码一致化（详见 `docs/review/doc-sync-2026-09-12.md`）

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
- [x] **跨模态四通道打分**：图像自相似 0.35 / 跨模态 0.35 / 文本自相似 0.15 / 颜色 0.15；跨模态内 `q_text·t_img` 与 `q_img·t_text`（0.5/0.5）；缺维度动态归一化
- [x] **阶段5 重构**：由「两自相似比大小」升级为**真跨模态一致性惩罚**（`cc = min(可用跨模态方向)`，仅当 `max(sim_ii,sim_tt) ≥ 0.55` 触发，只降权、≤×0.5、可 `CROSS_PENALTY_ENABLED` 关闭）
- [x] **阈值/权重 config 化**：手动 0.35 / 自动 0.55 / 邮件 0.70（**初值待标定**）
- [x] **接口契约（不新增端点）**：`/match` 结果项新增 `match_source`（text/image/mixed），响应新增 `legend: {high, mid}`（由阈值派生）；**403/401 契约冻结不变**
- [x] **三个运维脚本**：`reembed_all_vectors.py`（冷备 / `--dry-run` ETA / 断点续跑 / 幂等）、`calibrate_thresholds.py`（PR 曲线 + Recall@1/3/5/10 + `--grid` 权重网格）、`backfill_color_vectors.py`
- [x] **评测集**：`backend/eval/eval_set_v3.5.0.json`（**60 对 = 30 正 / 30 负**；剔除 6 对同图自比退化对后**有效 24 正 / 30 负**）
- [x] **维度错配运行期防线**：编码后 `_assert_embed_dim` 断言 + `/match` 打分前维度预检 → **HTTP 500**（不再静默空集）
- [x] 自动化测试扩至 **185 用例（183 通过 / 2 门控跳过）**
- ⚠️ **未用真实模型验证**：真实 Chinese-CLIP 权重（3.83GB）从未在本机下载；本版全部结论为**打桩验证**；阈值/权重为**初值待标定**

#### V3.5 — 体验飞升（计划中）
- [ ] 微信小程序端
- [ ] 向量数据库迁移（pgvector 或 FAISS）
- [ ] 多图上传（最多 5 张）
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
> **最后更新**：2026-09-14  
> **相关文档**：[文档索引](docs/README.md) | [SRS](SRS.md) | [v3.3 PRD](docs/product/PRD-v3.3.md) | [v3.5.0 增量 PRD](docs/product/PRD-v3.5.0-incremental.md) | [竞品分析报告](docs/product/competitive-analysis.md) | [用户角色与场景](docs/product/personas-and-scenarios.md)  
> **质量文档**：[架构评审报告 2026-09-12](docs/review/architecture-review-2026-09-12.md) | [文档与代码同步说明](docs/review/doc-sync-2026-09-12.md) | [增量修复设计](docs/review/design-fix-batch-2026-09-12.md) | [v3.4.0 变更总结](docs/review/v3.4.0-change-summary-2026-09-12.md) | [v3.5.0 增量架构设计](docs/review/v3.5.0-incremental-design.md) | [v3.5.0 QA 回归](docs/review/qa-v3.5.0-regression-2026-09-13.md)
