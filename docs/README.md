# 文档索引 (docs/README.md)

> 校园失物检索平台 — 全部工程与产品文档的总入口。
>
> **当前工程版本：v3.6.0（2026-10-14）**
>
> ⚠️ 本目录 `product/*` 为 **v3.3 产品阶段的历史快照**；系统的 schema、角色模型、匹配算法与接口契约，**一律以仓库根 `PROJECT.md` 与源码（v3.6.0）为准**。

---

## A. 工程现状（现行，优先阅读）

| 文档 | 路径 | 一句话说明 | 阅读顺序 |
|------|------|-----------|:--:|
| 项目总纲 | [`../PROJECT.md`](../PROJECT.md) | 架构、目录树、覆盖矩阵、数据库、API、算法、测试、版本演进 | ① |
| 快速上手 | [`../README.md`](../README.md) | 环境依赖、启动步骤、功能与接口概览 | ② |
| 软件需求规格说明书 | [`../SRS.md`](../SRS.md) | v3.6.0 功能性/非功能性需求、接口与数据需求 | ③ |
| 迭代日志 | [`../CHANGELOG.md`](../CHANGELOG.md) | 各版本迭代记录（含最新 V3.6.0；V3.5.0 条目含 §12–§15 打分口径重构/尺度修正） | ⑧ |

## B. 质量与整改（现行）

| 文档 | 路径 | 一句话说明 | 阅读顺序 |
|------|------|-----------|:--:|
| 架构评审报告 | [`review/architecture-review-2026-09-12.md`](review/architecture-review-2026-09-12.md) | 交付前架构评审：P0×3 / P1×4 / P2×4 及整改结论 | ④ |
| 文档与代码同步说明 | [`review/doc-sync-2026-09-12.md`](review/doc-sync-2026-09-12.md) | V3.3.3 文档与代码逐条对齐记录（D1–D11） | ⑤ |
| 增量修复设计 | [`review/design-fix-batch-2026-09-12.md`](review/design-fix-batch-2026-09-12.md) | v3.4.0 批量修复项（C1/C2/R4–R10/O2）的设计与任务分解 | ⑥ |
| 本轮变更总结 | [`review/v3.4.0-change-summary-2026-09-12.md`](review/v3.4.0-change-summary-2026-09-12.md) | v3.4.0 代码 + 文档落地总结 | ⑦ |
| 文档资源盘点与整合映射 | [`review/doc-consolidation-map-2026-09-12.md`](review/doc-consolidation-map-2026-09-12.md) | 全仓文档盘点、整合决策与目标目录结构 | — |
| **v3.5.0 增量架构设计** | [`review/v3.5.0-incremental-design.md`](review/v3.5.0-incremental-design.md) | v3.5.0 中文化模型替换 + 图文跨模态检索的架构设计与任务分解（T01–T05） | ⑨ |
| **v3.5.0 QA 回归报告** | [`review/qa-v3.5.0-regression-2026-09-13.md`](review/qa-v3.5.0-regression-2026-09-13.md) | v3.5.0 回归 + 跨模态新功能测试：维度错配（D1）等发现与修复验证；V1–V5 **全部已转「已用真实模型验证」**（重嵌入完成、`/match` 三模式实测恢复；V4 截断实验已闭环：关键信息被截掉 → 相对损失 ~22.5%） | ⑩ |
| **v3.5.0 阈值标定报告** | [`review/threshold-calibration-v3.5.0.md`](review/threshold-calibration-v3.5.0.md) | 报告快照（2026-09-14 扩充轮）：84 对 / 有效 36 正 42 负 + 真实 `Recall@3=1.0`；报告时点 `AUTO`/`EMAIL` 尚无解（Precision 上界 0.6889）。**✅ 2026-09-21 打分口径重构（三检索模式 + 跨模态尺度映射）后首次标定成功**：MANUAL 0.624956 / AUTO 0.733952 / EMAIL 0.832069（详见 CHANGELOG V3.5.0 §14；`EMAIL` 召回 19.4%，建议灰度观察） | — |
| **v3.5.0 增量 PRD（现行）** | [`product/PRD-v3.5.0-incremental.md`](product/PRD-v3.5.0-incremental.md) | v3.5.0 增量需求（中文化模型 + 图文跨模态检索）：产品目标 / 用户故事 / 需求池 / 验收标准（**现行**，非 C 组历史快照） | — |

## C. 产品设计（历史快照，v3.3 阶段）

> 以下文档记录 v3.3 产品设计与研究过程，正文按历史原样保留；涉及 schema、角色模型、算法与接口的表述，请以 A 组现行文档为准。

| 文档 | 路径 | 一句话说明 |
|------|------|-----------|
| v3.3 产品需求文档 (PRD) | [`product/PRD-v3.3.md`](product/PRD-v3.3.md) | v3.3 产品需求（PRD） |
| 竞品分析与产品定位 | [`product/competitive-analysis.md`](product/competitive-analysis.md) | 竞品分析与产品定位报告 |
| 核心用户角色与场景 | [`product/personas-and-scenarios.md`](product/personas-and-scenarios.md) | 3 Persona / 15 场景设计 |
| 信息架构与路由设计 | [`product/information-architecture.md`](product/information-architecture.md) | 信息架构与前端路由设计 |
| 关键页面重设计方案 | [`product/page-redesign.md`](product/page-redesign.md) | 关键页面重设计方案 |
| UI 功能测试用例 | [`product/ui-test-cases.md`](product/ui-test-cases.md) | UI 界面功能测试用例（226 条） |
| 需求规格修改意见 | [`product/requirement-revision-notes.md`](product/requirement-revision-notes.md) | v3.3 需求的原始「修改意见」 |

## D. 图件

| 图件 | 路径 | 说明 |
|------|------|------|
| 关键流程时序图 | [`diagrams/sequence-diagram.mermaid`](diagrams/sequence-diagram.mermaid) | 关键操作调用时序（Mermaid sequenceDiagram） |
| 数据模型与服务类图 | [`diagrams/class-diagram.mermaid`](diagrams/class-diagram.mermaid) | 数据模型与服务类结构（Mermaid classDiagram） |
| **v3.5.0 后端抽象层类图** | [`diagrams/class-diagram-v3.5.0.mermaid`](diagrams/class-diagram-v3.5.0.mermaid) | `ClipBackend` 双后端 + 跨模态通道 + match 契约（Mermaid classDiagram） |
| **v3.5.0 匹配时序图** | [`diagrams/sequence-diagram-v3.5.0-match.mermaid`](diagrams/sequence-diagram-v3.5.0-match.mermaid) | `POST /api/items/match` 跨模态匹配（Mermaid sequenceDiagram） |
| **v3.5.0 重嵌入时序图** | [`diagrams/sequence-diagram-v3.5.0-reembed.mermaid`](diagrams/sequence-diagram-v3.5.0-reembed.mermaid) | 冷备→干跑→重嵌入→标定→启用/回滚（Mermaid sequenceDiagram） |

---

> **维护约定**：`A`、`B`、`D` 组为**现行文档**，随代码演进同步更新；`C` 组为**历史快照**，仅追加「实现以代码为准」性质的横幅/脚注，不重写正文。
