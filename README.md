# 校园失物检索平台

> 基于加权融合相似度算法的校园失物检索系统 | Vue 3 + FastAPI + AI
>
> **当前版本：v3.6.0** | 更新日期：2026-10-14 | 文档索引见 [`docs/README.md`](docs/README.md)

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

一个面向高校校园的**智能化失物检索平台**。默认采用 **Chinese-CLIP ViT-H-14**（`open_clip ViT-B-32` 可回滚）多模态模型实现「以图搜图」「以文搜图」「图文混合」多维度匹配；打分按查询形态分**三种检索模式**（文字 / 图片 / 图文混合），采用**主证据 + 辅助证据**加权（同模态 0.75 / 跨模态 0.25，缺通道动态归一化 ⇒ 三模式自动成形）+ **跨模态尺度映射** + 五阶段优化（类别/位置调节 + 时间衰减 + 分层阈值 + 跨模态一致性惩罚），并输出**证据链**（证据等级 / 命中依据 / 通道原始值）；三档阈值已用真实模型标定（手动 0.625 / 自动 0.734 / 邮件 0.832，内容分尺度）。

**完整闭环**：发布 → 审核 → 匹配 → 通知 → 认领申请 → 审批（互斥）→ 归还确认 → 历史记录

---

## 核心功能

| 模块 | 功能 |
|------|------|
| 🔐 **用户认证** | 注册/登录、JWT 鉴权、权限分级（角色 `user`/`admin` + 账号状态 `active`/`disabled`/`deleted`） |
| 📦 **物品管理** | 发布失物/拾物（**1-3 张图**、拖拽排序、首图封面）、分类筛选、关键词搜索、编辑/删除 |
| 🤖 **智能匹配** | Chinese-CLIP 图文特征、**三种检索模式**（文字/图片/图文混合，主辅证据加权）、跨模态尺度映射、五阶段优化、Top 20、来源标签（`match_source`）+ **证据链（等级/依据/通道）** |
| ✅ **审核管理** | 审核通过/驳回+邮件通知、批量通过、用户管理 CRUD、**设为首页推荐** |
| 🔔 **消息通知** | 站内通知 + HTML 邮件（含匹配等级与命中依据）、未读红点、30 秒轮询、一键全部已读 |
| 🤝 **认领闭环** | 申请（特征描述 + 证明图）、发布者审批、**互斥自动拒绝**同物品其他申请、联系方式脱敏、确认归还 + 找回计数 |
| 🚩 **举报体系** | 五类举报 + 处理留痕（结论/处理人/时间）、「我的举报」进度查询 |
| 💬 **留言互动** | 楼中楼留言、公开可见 / 登录可发 / 本人可删 / 管理员隐藏、删除父留言级联删回复 |
| 🎯 **推荐与相似** | 详情页相似物品推荐（反类型 + 同口径打分）、首页「为你推荐」推荐位 |
| 📊 **数据看板** | 首页统计卡片 + 分类占比饼图；**管理端统计看板**（找回率仪表盘 / 近 30 天发布趋势 / 分类占比） |
| 📢 **内容运营** | 轮播图、分类管理（表驱动 + 使用中删除保护）、公告草稿/发布分离 |
| 🎨 **现代化 UI** | 深/浅色模式、骨架屏加载、毛玻璃认证页、Inter 字体、1440px+ 桌面适配 |
| 👤 **个人中心** | 修改用户名/密码/联系方式、注销账号、历史记录 |

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
│  CLIP: cn(H-14)/oc(B-32) 双后端       │
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

项目自带自动化测试套件（pytest，**313 用例：311 通过 / 2 门控跳过**〔数值随套件演进，以 `--junitxml` 为准〕），无需下载 CLIP 模型即可运行（测试内以确定性假向量桩替换特征提取，并使用临时数据库；2 个 skip 是 `test_real_clip_smoke.py` 的真实权重门控用例——权重已在本机下载，设 `RUN_REAL_CLIP=1` 时这 2 例转通过）：

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
| POST | `/api/items/` | 发布物品（FormData，支持 1-3 张图） |
| GET | `/api/items/` | 物品列表 |
| GET | `/api/items/{id}` | 物品详情 |
| PUT | `/api/items/{id}` | 编辑物品（多图 `keep` 保留顺序 + 新增） |
| DELETE | `/api/items/{id}` | 删除物品 |
| POST | `/api/items/match` | 智能匹配（需登录，支持多图 `image_paths`） |
| GET | `/api/items/recommend` | 首页推荐位（管理员设为推荐） |
| GET | `/api/items/{id}/similar` | 详情页相似物品推荐 |
| POST | `/api/items/{id}/claim` | 申请认领/归还（兼容薄包装） |
| PUT | `/api/items/{id}/mark-claimed` | 自标记找回/归还 |

### 认领闭环 & 社区
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/claims` / `/api/claims/proof-upload` | 提交认领申请 / 证明图上传 |
| GET | `/api/claims/mine` / `/api/claims/received` | 我的申请 / 收到的申请 |
| GET | `/api/claims/{id}` / `/api/claims/status/{item_id}` | 申请详情（脱敏联系方式）/ 按钮态 |
| POST | `/api/claims/{id}/approve\|reject\|complete\|cancel` | 审批（互斥）/ 拒绝 / 确认完成 / 撤销 |
| POST/GET | `/api/reports` / `/api/reports/mine` | 提交举报（五类）/ 我的举报进度 |
| GET/PUT | `/api/reports/admin*` | 管理端举报列表 / 处理 |
| GET/POST/DELETE | `/api/comments*` | 留言列表 / 发表 / 删除（级联） |

### 管理 & 通知
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | `/api/admin/reviews` | 审核列表/操作（含设为推荐） |
| GET/PUT/POST/DELETE | `/api/admin/users` | 用户管理 |
| GET/PUT | `/api/admin/items` | 物品管理 |
| POST | `/api/admin/items/batch` | 批量操作 |
| GET/POST/PUT/DELETE | `/api/announcements` | 公告 CRUD（含草稿/发布/下架） |
| GET/POST/PUT/DELETE | `/api/banners*` | 轮播图管理（`/upload` 上传 + `/admin` CRUD） |
| GET/POST/PUT/DELETE | `/api/categories/admin*` | 分类管理（使用中删除保护） |
| GET | `/api/notifications/unread` | 未读列表 |
| PUT | `/api/notifications/read-all` | 一键已读 |
| GET | `/api/stats/dashboard` | 首页数据看板 |
| GET | `/api/stats/admin/*` | 管理端统计（overview / recovery / publish-trend / category-pie） |

---

## 设计系统

- **品牌色**：`#1B4D3E` 深翠绿 | **字体**：Inter + 系统中文字体栈
- **深色模式**：完整暗色变量覆盖 + 系统主题跟随
- **响应式**：480px / 640px / 768px（移动 / 平板）+ 1440px / 1920px（桌面宽屏）五级断点，以源码 `styles/theme.css` 与各视图 `@media` 为准
- **匹配算法**：按查询形态三种检索模式（文字 / 图片 / 图文混合）+ 主证据·辅助证据加权（同模态 0.75 / 跨模态 0.25，缺通道动态归一化）+ 跨模态尺度映射 + 五阶段优化（类别/位置双向调节 + 时间衰减 240 天·下限 0.6 + 分层阈值 + 跨模态一致性惩罚）+ 证据链输出；颜色通道已于 2026-09-16 废弃

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
| **V3.5.0** | **中文化模型替换（Chinese-CLIP ViT-H-14，可回滚 open_clip）/ 图文跨模态四通道检索 + 阶段5 重构 / 阈值·权重 config 化并重标定 / `match_source`+`legend` 契约 / 全量重嵌入·标定·颜色回填三脚本 / 评测集 84 对（扩充轮复标，AUTO/EMAIL 结构性无解）/ 修复重嵌入脚本「假绿迁移」缺陷 / 生产库已完成全量重嵌入（1024 维，`/match` 实测恢复）/ 测试扩至 209 用例（207 通过 / 2 门控跳过）/ 真实权重已下载并端到端验证（真实 Recall@3=1.0；分层阈值 AUTO/EMAIL 仍无解）** | ✅ |
| **V3.6.0** | **打分口径重构（按查询形态三种检索模式 + 跨模态尺度映射 + 证据链；AUTO/EMAIL 阈值首次标定成功）/ 时间衰减失效修复与参数调温和 / 自动匹配阈值尺度修正 / 融合参考项目八大设计（认领闭环 · 举报 · 留言 · 多图 · 统计看板 · 相似推荐 · 证据链可视化 · 内容运营）/ 测试扩至 304 用例（302 通过 / 2 门控跳过）** | ✅ |

详见 [CHANGELOG.md](CHANGELOG.md)

---

## 许可证

MIT License © 2026
