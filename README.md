# 校园失物检索平台

> 基于 CLIP 多模态匹配的智能失物招领平台 | Vue 3 + FastAPI + AI

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.5+-4FC08D?logo=vue.js&logoColor=white" alt="Vue">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/CLIP-ViT--B--32-FF6F00?logo=openai&logoColor=white" alt="CLIP">
  <img src="https://img.shields.io/badge/Inter-font-6C6CE5?logo=googlefonts&logoColor=white" alt="Inter">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## 项目简介

一个面向高校校园的**智能化失物检索平台**。利用 OpenAI **CLIP 多模态模型**实现「以图搜图」「以文搜图」「图文混合+颜色」多维度匹配，五阶段优化算法（类别/位置调节 + 时间衰减 + 分层阈值 + 动态权重 + 交叉验证 + 颜色增强）。

**完整闭环**：发布 → 审核 → 匹配 → 通知 → 认领/归还 → 自标记 → 历史记录

---

## 核心功能

| 模块 | 功能 |
|------|------|
| 🔐 **用户认证** | 注册/登录、JWT 鉴权、权限分级（用户/管理员/已禁用/已注销） |
| 📦 **物品管理** | 发布失物/拾物、分类筛选、关键词搜索、编辑/删除、图片上传 |
| 🤖 **智能匹配** | CLIP 图文+颜色特征提取、五阶段加权相似度、Top 20 排序 |
| ✅ **审核管理** | 审核通过/驳回+邮件通知、批量通过、用户管理 CRUD |
| 🔔 **消息通知** | 站内通知 + HTML 邮件、未读红点、30 秒轮询、一键全部已读 |
| 🎨 **现代化 UI** | 深/浅色模式、骨架屏加载、毛玻璃认证页、Inter 字体、1440px+ 桌面适配 |
| 👤 **个人中心** | 修改用户名/密码/联系方式、注销账号 |
| 🤝 **认领/归还** | 失物→我要归还、拾物→我要认领、发布者自标记找回/归还 |
| 📊 **数据看板** | 展示中/今日失物/今日拾物/总计找回 + 分类占比饼图 |
| 📢 **公告系统** | 管理员发布/编辑/删除、可见范围设置、首页抽屉展示 |

---

## 技术架构

```
┌──────────────────────────────────────┐
│  前端: Vue 3 + Element Plus + ECharts │
│  Pinia + Vue Router 5 + Vite 8       │
│  Inter 字体 + CSS 变量设计系统        │
└──────────────┬───────────────────────┘
               │ REST API (JWT)
┌──────────────▼───────────────────────┐
│  后端: FastAPI (Python 3.11)         │
│  Pydantic 2 + SQLite + bcrypt       │
│  CLIP ViT-B-32 + 颜色直方图          │
│  BackgroundTasks 异步匹配             │
└──────────────┬───────────────────────┘
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
 SQLite    CLIP 模型    SMTP 邮件
(本地)     (~600MB)     (可选)
```

## 快速开始

### 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 20
- **磁盘空间** ≥ 2GB

### 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动前端

```bash
cd lost-found-frontend
npm install
npm run dev                    # → http://localhost:5173
```

### 创建管理员

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

---

## API 接口

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/register` | 用户注册 |
| POST | `/api/login` | 用户登录 |
| GET | `/api/me` | 获取个人信息 |
| PUT | `/api/me` | 更新个人资料 |
| DELETE | `/api/me` | 注销账号 |
| POST | `/api/me/avatar` | 上传头像 |

### 物品 & 匹配
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/items/` | 发布物品 |
| GET | `/api/items/` | 物品列表 |
| GET | `/api/items/{id}` | 物品详情 |
| PUT | `/api/items/{id}` | 编辑物品 |
| DELETE | `/api/items/{id}` | 删除物品 |
| POST | `/api/items/match` | 智能匹配 |
| POST | `/api/items/{id}/claim` | 申请认领/归还 |
| PUT | `/api/items/{id}/mark-claimed` | 自标记 |

### 管理 & 通知
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/admin/reviews` | 审核列表/操作 |
| GET/PUT/POST/DELETE | `/api/admin/users` | 用户管理 |
| GET/PUT | `/api/admin/items` | 物品管理 |
| POST | `/api/admin/items/batch` | 批量操作 |
| GET/POST/PUT/DELETE | `/api/announcements` | 公告 CRUD |
| GET | `/api/notifications/unread` | 未读列表 |
| PUT | `/api/notifications/read-all` | 一键已读 |
| GET | `/api/stats/dashboard` | 数据看板 |

---

## 设计系统

- **品牌色**：`#1B4D3E` 深翠绿 | **字体**：Inter + 系统中文字体栈
- **深色模式**：完整暗色变量覆盖 + 系统主题跟随
- **响应式**：480px / 768px / 1024px / 1440px / 1920px 五级断点
- **匹配算法**：五阶段优化（类别/位置双向调节 + 时间衰减 + 分层阈值 + 动态权重 + 交叉验证 + 颜色直方图增强）

---

## 迭代路线

| 版本 | 主题 | 状态 |
|------|------|:--:|
| V3.0 | 核心功能 + 现代 UI | ✅ |
| V3.1 | 骨架屏/深色模式/个人中心/认领流程/轮询 | ✅ |
| V3.1.1 | 头像上传/认领邮件/详情重构/一键已读/UI修复 | ✅ |
| V3.2 | 登录跳转/管理面板/数据看板/个人中心补全 | ✅ |
| V3.3 | 公告系统/五阶段匹配/颜色特征/物品管理/消息优化 | ✅ |

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 许可证

MIT License © 2026
