# 🏫 校园失物智能寻回系统

> 基于 CLIP 多模态匹配的智能失物招领平台 | Vue 3 + FastAPI + AI

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.5+-4FC08D?logo=vue.js&logoColor=white" alt="Vue">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/CLIP-ViT--B--32-FF6F00?logo=openai&logoColor=white" alt="CLIP">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

------

## 📖 项目简介

一个面向高校校园的 **智能化失物招领平台**。传统校园失物招领依赖 QQ 群、BBS、服务台等分散渠道，失主查询困难，找回率低（传统 BBS 仅约 6.97%）。

本系统利用 OpenAI **CLIP 多模态模型**实现「以图搜图」「以文搜图」「图文混合匹配」，变“被动查询”为“主动发现”。管理员审核通过后自动匹配异类物品，**双向推送**站内通知 + 邮件，形成 **发布 → 审核 → 匹配 → 通知 → 认领** 的完整闭环。

<p align="center">
  <strong>✨ 在线体验：待部署 &nbsp;|&nbsp; 📚 <a href="#-快速开始">快速开始</a> &nbsp;|&nbsp; 📄 <a href="PROJECT.md">完整文档</a></strong>
</p>

------

## 🎯 核心功能

| 模块            | 功能                                               |
| --------------- | -------------------------------------------------- |
| 🔐 **用户认证**  | 注册/登录、JWT 鉴权、权限分级（用户/管理员）       |
| 📦 **物品管理**  | 发布失物/拾物、分类筛选、关键词搜索、编辑/删除     |
| 🤖 **智能匹配**  | CLIP 图文特征提取、加权相似度计算、Top 20 结果排序 |
| ✅ **审核管理**  | 管理员审核通过/驳回、审核后自动匹配推送            |
| 🔔 **消息通知**  | 站内通知 + HTML 邮件、未读红点、30 秒轮询          |
| 🎨 **现代化 UI** | 深/浅色模式、骨架屏加载、毛玻璃认证页、响应式布局  |
| 👤 **个人中心**  | 修改密码、更新联系方式                             |
| 🤝 **物品认领**  | 申请认领 → 通知发布者 → 确认/拒绝 → 状态变更       |

------

## 🖼️ 界面预览

|          登录页           |            首页            |          物品详情          |
| :-----------------------: | :------------------------: | :------------------------: |
| 校园航拍背景 + 毛玻璃卡片 | 卡片网格 + 筛选栏 + 骨架屏 | 两栏布局 + 状态标签 + 认领 |

|    智能匹配     |      审核管理       |     深色模式     |
| :-------------: | :-----------------: | :--------------: |
| AI 相似度进度条 | 表格展开 + 批量操作 | 一键切换暗色主题 |

------

## 🏗️ 技术架构

```
┌──────────────────────────────────┐
│  前端: Vue 3 + Element Plus      │
│  Pinia + Vue Router + Vite 8    │
│  CSS 变量设计系统 + 深色模式     │
└──────────────┬───────────────────┘
               │ REST API (JWT)
┌──────────────▼───────────────────┐
│  后端: FastAPI (Python 3.11)     │
│  Pydantic 2 + SQLite + bcrypt   │
│  CLIP ViT-B-32 (OpenCLIP)       │
│  BackgroundTasks 异步匹配        │
└──────────────┬───────────────────┘
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
 SQLite    CLIP 模型    SMTP 邮件
(本地DB)   (~600MB)     (可选)
```

### 技术选型

| 技术                        | 用途                                  |
| --------------------------- | ------------------------------------- |
| **Vue 3** (Composition API) | 前端框架，`<script setup>` 语法       |
| **Element Plus 2.14**       | UI 组件库，CSS 变量全局覆盖           |
| **Pinia**                   | 状态管理（auth / notification store） |
| **Vue Router 5**            | 路由 + 导航守卫                       |
| **Vite 8** (Rolldown)       | 构建工具，API 代理                    |
| **FastAPI**                 | 后端框架，自动生成 Swagger 文档       |
| **SQLite**                  | 数据库（毕设阶段零配置）              |
| **JWT (HS256)**             | 无状态认证，7 天有效期                |
| **bcrypt**                  | 密码加盐哈希                          |
| **OpenCLIP**                | ViT-B-32 图文跨模态特征提取           |
| **smtplib**                 | QQ 邮箱 SMTP 邮件通知                 |

------

## 🚀 快速开始

### 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 20
- **磁盘空间** ≥ 2GB（CLIP 模型首次下载约 600MB）

### 1. 克隆项目

```bash
git clone https://github.com/3383446104/lost-found-v3.git
cd lost-found-v3
```

### 2. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（已提供默认值，生产环境请修改 SECRET_KEY）
cp .env.example .env            # 如有模板文件

# 启动服务（首次启动自动下载 CLIP 模型 ~600MB）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端启动后访问：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 3. 启动前端

```bash
cd lost-found-frontend

# 安装依赖
npm install

# 开发模式启动
npm run dev                    # → http://localhost:5173

# 生产构建
npm run build                  # → dist/
```

### 4. 创建管理员账号

```bash
cd backend
python -c "
from app.database import get_db_connection
import bcrypt
pw = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
with get_db_connection() as conn:
    conn.execute('INSERT OR IGNORE INTO users (username,password_hash,role) VALUES (?,?,?)', ('admin', pw, 'admin'))
    print('管理员已创建: admin / admin123')
"
```

------

## 📁 项目结构

```
lost-found-v3/
├── README.md                 ← 本文件
├── PROJECT.md                ← 完整项目文档（632行）
├── CHANGELOG.md              ← 版本迭代日志
├── backend/                  ← 后端 (FastAPI)
│   ├── .env                  ← 环境变量
│   ├── requirements.txt      ← Python 依赖
│   ├── lost_found.db         ← SQLite 数据库
│   ├── uploads/              ← 图片文件
│   └── app/
│       ├── main.py           ← 应用入口
│       ├── config.py         ← 配置中心
│       ├── database.py       ← 数据库 + 向量工具
│       ├── clip_service.py   ← CLIP 特征提取服务
│       ├── api/              ← 路由 (auth/items/admin/notifications)
│       ├── services/         ← 业务逻辑 (自动匹配)
│       ├── dependencies/     ← JWT 鉴权依赖
│       └── utils/            ← 工具 (邮件/文件/时间)
└── lost-found-frontend/      ← 前端 (Vue 3)
    ├── index.html
    ├── vite.config.js        ← Vite + API 代理
    ├── public/
    │   └── campus-aerial.jpg ← 校园航拍背景
    └── src/
        ├── main.js           ← 入口 (Element Plus + 主题)
        ├── App.vue           ← 根组件
        ├── styles/theme.css  ← 全局设计系统 (700+ 行)
        ├── layouts/          ← 布局组件
        ├── views/            ← 9 个页面组件
        ├── components/       ← 可复用组件
        ├── composables/      ← 组合式函数
        ├── stores/           ← Pinia 状态管理
        ├── api/              ← API 封装
        ├── router/           ← 路由配置
        └── utils/            ← 工具函数
```

------

## 🔌 API 接口

### 认证

| 方法 | 路径            | 说明         |
| ---- | --------------- | ------------ |
| POST | `/api/register` | 用户注册     |
| POST | `/api/login`    | 用户登录     |
| GET  | `/api/me`       | 获取个人信息 |
| PUT  | `/api/me`       | 更新个人信息 |

### 物品

| 方法   | 路径                            | 说明                  |
| ------ | ------------------------------- | --------------------- |
| POST   | `/api/items/`                   | 发布物品              |
| GET    | `/api/items/`                   | 物品列表（分页/筛选） |
| GET    | `/api/items/{id}`               | 物品详情              |
| PUT    | `/api/items/{id}`               | 编辑物品              |
| DELETE | `/api/items/{id}`               | 删除物品              |
| POST   | `/api/items/match`              | 智能匹配              |
| POST   | `/api/items/{id}/claim`         | 申请认领              |
| PUT    | `/api/items/{id}/claim/confirm` | 确认认领              |

### 管理员 & 通知

| 方法 | 路径                              | 说明       |
| ---- | --------------------------------- | ---------- |
| GET  | `/api/admin/reviews`              | 待审核列表 |
| PUT  | `/api/admin/reviews/{id}`         | 审核操作   |
| GET  | `/api/notifications/unread/count` | 未读数量   |
| GET  | `/api/notifications/unread`       | 未读列表   |
| PUT  | `/api/notifications/{id}/read`    | 标记已读   |

------

## 🎨 设计系统

- **品牌色**：`#1B4D3E` 深翠绿（学院风）
- **中性色**：9 阶暖灰（`--neutral-50` ~ `--neutral-900`）
- **阴影**：5 级深度（xs～xl）+ 焦点光环
- **圆角**：6 级（4px～9999px）
- **间距**：4px 网格（4～48px）
- **字体**：11～32px 共 10 级
- **动效**：150/200/300/350ms 四级缓动
- **深色模式**：完整暗色变量覆盖 + 系统主题跟随

------

## 🧪 核心算法

### 加权相似度融合

```
Similarity = 0.6 × CosSim(Image1, Image2) + 0.4 × CosSim(Text1, Text2)
```

- 双方均有图：标准加权
- 纯文本匹配：直接使用文本相似度（不降权），确保可达 0.6 自动推送阈值

### 自动匹配流程

```
管理员审核通过
  → BackgroundTasks 异步启动
  → 查询异类活跃物品
  → 逐对计算加权相似度
  → 筛选 ≥ 0.6 的匹配
  → 双向发送通知（新物品发布者 + 目标物品拥有者）
  → 有邮箱的用户同步推送 HTML 邮件
```

------

## 📊 需求覆盖

| 模块       | 需求数 | 覆盖率  |
| ---------- | :----: | :-----: |
| 用户认证   |   6    |  100%   |
| 物品管理   |   9    |  100%   |
| 智能匹配   |   7    |  100%   |
| 管理员审核 |   4    |  100%   |
| 消息通知   |   6    |  100%   |
| 非功能需求 |   12   |   92%   |
| **总计**   | **44** | **98%** |

详见 [PROJECT.md](PROJECT.md) 完整需求覆盖矩阵。

------

## 🗺️ 迭代路线

| 版本 | 主题                                               |    状态    |
| ---- | -------------------------------------------------- | :--------: |
| V3.0 | 核心功能 + 现代 UI                                 |  ✅ 已完成  |
| V3.1 | 骨架屏 / 深色模式 / 个人中心 / 认领流程 / 轮询     |  ✅ 已完成  |
| V3.2 | 多图上传 / WebSocket / 搜索高亮 / 数据仪表盘       |  📋 计划中  |
| V4.0 | PostgreSQL + pgvector / Celery / OSS / PWA / OAuth | 💡 远期规划 |

详见 [CHANGELOG.md](CHANGELOG.md) 版本迭代记录。

------

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request。

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'feat: add amazing feature'`
4. 推送到分支：`git push origin feature/amazing-feature`
5. 提交 Pull Request

------

## 📄 许可证

MIT License © 2026

------

<p align="center">
  <em>让每一件失物都能回家 🏠</em>
</p>
