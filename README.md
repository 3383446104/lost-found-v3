# 校园失物检索平台

> 基于 CLIP 多模态匹配的智能失物招领平台 | Vue 3 + FastAPI + AI
>
> **当前版本：v3.5.0** | 更新日期：2026-09-14 | 文档索引见 [`docs/README.md`](docs/README.md)

<p align="center">
  <img src="https://img.shields.io/badge/Vue-3.5+-4FC08D?logo=vue.js&logoColor=white" alt="Vue">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/CLIP-Chinese--CLIP%20ViT--H--14-FF6F00?logo=openai&logoColor=white" alt="CLIP">
  <img src="https://img.shields.io/badge/Inter-font-6C6CE5?logo=googlefonts&logoColor=white" alt="Inter">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## 项目简介

一个面向高校校园的**智能化失物检索平台**。默认采用 **Chinese-CLIP ViT-H-14**（`open_clip ViT-B-32` 可回滚）多模态模型实现「以图搜图」「以文搜图」「图文混合+颜色」多维度匹配；**四通道跨模态**加权打分（图-图 0.35 / 跨模态 0.35 / 文-文 0.15 / 色 0.15）+ 五阶段优化（动态权重归一化 + 类别/位置调节 + 时间衰减 + 分层阈值 + 跨模态一致性惩罚）。

**完整闭环**：发布 → 审核 → 匹配 → 通知 → 认领/归还 → 自标记 → 历史记录

---

## 核心功能

| 模块 | 功能 |
|------|------|
| 🔐 **用户认证** | 注册/登录、JWT 鉴权、权限分级（角色 `user`/`admin` + 账号状态 `active`/`disabled`/`deleted`） |
| 📦 **物品管理** | 发布失物/拾物、分类筛选、关键词搜索、编辑/删除、图片上传 |
| 🤖 **智能匹配** | Chinese-CLIP 图文+颜色特征、**四通道跨模态**加权（含「描述搜图」真跨模态）、五阶段优化、Top 20 排序、来源标签（`match_source`） |
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
│  CLIP: cn(H-14)/oc(B-32) + 颜色直方图 │
│  BackgroundTasks 异步匹配             │
└──────────────┬───────────────────────┘
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
 SQLite    CLIP 模型    SMTP 邮件
(本地)     (3.8G/600M)  (可选)
```

## 快速开始

### 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 20
- **磁盘空间** ≥ 5GB（默认 Chinese-CLIP ViT-H-14 权重约 3.83GB；回滚后端 open_clip ViT-B-32 约 600MB）

### 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
# ⚠️ cn_clip 须用 --no-deps 安装：其 setup.py 硬钉 lmdb==1.3.0，
#    Windows 无 wheel 会编译失败；推理不需要 lmdb。
pip install cn_clip --no-deps
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> **模型权重**：默认 `CLIP_BACKEND=cn_clip` → Chinese-CLIP ViT-H-14，首次启动自动下载约 3.83GB（默认走 ModelScope，`CLIP_CN_USE_MODELSCOPE=True`，国内直连）；若离线部署，置 `CLIP_CN_CKPT_PATH` 指向本地 `.pt` 使**运行期零网络**。可切 `CLIP_BACKEND=open_clip` 回滚到 ViT-B-32（约 600MB）；**两代向量空间不兼容，切换后必须重嵌入全库向量**（`scripts/reembed_all_vectors.py`）。

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

### 运行测试

项目自带自动化测试套件（pytest，**185 用例：183 通过 / 2 门控跳过**〔数值随套件演进，以 `--junitxml` 为准〕），无需下载 CLIP 模型即可运行（测试内以确定性假向量桩替换特征提取，并使用临时数据库；2 个 skip 是 `test_real_clip_smoke.py` 的真实权重门控用例）：

```bash
cd backend
venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # 首次安装 pytest / httpx
venv\Scripts\python.exe -m pytest tests/ -v
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
| GET | `/api/me/history` | 个人历史记录 |

### 物品 & 匹配
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/items/` | 发布物品 |
| GET | `/api/items/` | 物品列表 |
| GET | `/api/items/{id}` | 物品详情 |
| PUT | `/api/items/{id}` | 编辑物品 |
| DELETE | `/api/items/{id}` | 删除物品 |
| POST | `/api/items/match` | 智能匹配（需登录） |
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
- **响应式**：480px / 640px / 768px（移动 / 平板）+ 1440px / 1920px（桌面宽屏）五级断点，以源码 `styles/theme.css` 与各视图 `@media` 为准
- **匹配算法**：四通道跨模态 + 五阶段优化（动态权重归一化 + 类别/位置双向调节 + 时间衰减 + 分层阈值 + 跨模态一致性惩罚 + 颜色直方图增强）

---

## 迭代路线

| 版本 | 主题 | 状态 |
|------|------|:--:|
| V3.0 | 核心功能 + 现代 UI | ✅ |
| V3.1 | 骨架屏/深色模式/个人中心/认领流程/轮询 | ✅ |
| V3.1.1 | 头像上传/认领邮件/详情重构/一键已读/UI修复 | ✅ |
| V3.2 | 登录跳转/管理面板/数据看板/个人中心补全 | ✅ |
| V3.3 | 公告系统/五阶段匹配/颜色特征/物品管理/消息优化 | ✅ |
| V3.3.1 | 统计过滤 / 批量审核路由 / 认领文案 / 列表过滤 / mark-claimed 路由 / 自动匹配通知 | ✅ |
| V3.3.2 | 五阶段匹配算法重构 / 公告系统 / 物品管理统一 Tab / 桌面适配 | ✅ |
| V3.3.3 | 自动化测试（45 用例）/ P0 修复（禁用鉴权·今日时区·依赖声明）/ 文档与代码对齐 | ✅ |
| V3.4.0 | 账户状态语义拆分（role×status）/ 颜色特征持久化 / 匹配性能·异步 / 路由·契约加固 / 测试扩至 70 用例 | ✅ |
| V3.4.1 | 补齐 `POST /api/items/match` 鉴权（需登录；缺 token 403 / 非法 401）/ 测试扩至 72 用例 | ✅ |
| **V3.5.0** | **中文化模型替换（Chinese-CLIP ViT-H-14，可回滚 open_clip）/ 图文跨模态四通道检索 + 阶段5 重构 / 阈值·权重 config 化并重标定 / `match_source`+`legend` 契约 / 全量重嵌入·标定·颜色回填三脚本 / 评测集 60 对 / 测试扩至 185 用例（183 通过 / 2 门控跳过）** | ✅ |

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 许可证

MIT License © 2026
