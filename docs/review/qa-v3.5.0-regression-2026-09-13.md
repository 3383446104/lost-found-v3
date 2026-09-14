# QA 独立回归报告 — v3.5.0（换中文 CLIP 模型 + 图文跨模态检索）

- 报告人：yan-qa（Edward，QA）
- 日期：2026-09-13
- 被测改动：`app/clip_backend.py`(新)、`app/clip_service.py`、`app/config.py`、`app/api/items.py`、`app/services/match_service.py`、`scripts/reembed_all_vectors.py`(新)、`scripts/calibrate_thresholds.py`(新)
- 被测版本：`APP_VERSION = 3.5.0`
- 新增测试：`tests/test_qa_v350_math.py`、`tests/test_qa_v350_contract.py`、`tests/test_qa_v350_reembed_safety.py`、`tests/test_qa_v350_dimension.py`（共 54 例）
- **未修改任何源码 / 任何既有测试文件。**

> 说明：本机 pytest 退出码不可信（沙箱 SAFE_DELETE 告警导致恒为 1），以下所有结论均以 `--junitxml` 内的 `failures/errors` 计数为准。

---

## 0. 权威读数（junitxml）

| 运行 | tests | failures | errors | skipped | 说明 |
|------|:--:|:--:|:--:|:--:|------|
| 基线（改动前既有套件） | 111 | 0 | 0 | 2 | 与团队给定基线一致 |
| 本次新增 QA 用例 | 54 | **1** | 0 | 0 | 唯一失败 = **故意置红的缺陷探测器**（见 §2-D1） |
| **全量（既有 111 + QA 54）** | **165** | **1** | **0** | **2** | 既有 111 例**零回归**；2 跳过为 `RUN_REAL_CLIP` 门控 |

- 失败用例：`tests/test_qa_v350_dimension.py::test_D_declared_embed_dim_matches_cn_clip_reality`
  → 断言「`ChineseClipBackend.embed_dim` 应等于 cn_clip 真实输出维度」，实测 `512 != 1024`。**这是本报告头号缺陷的证据，非测试缺陷。**

---

## 1. 三档验证清单（严格分档，不混）

### ① 已验证（打桩 / 纯数学 / 静态分析）

| 编号 | 验证项 | 结论 |
|:--:|------|------|
| A1 | 跨模态四通道可用性判据（`has_ii/has_tt/has_t2i/has_i2t`） | ✅ 与 docstring 一致；纯文查询 × 图文目标走 `tt+t2i`、纯图走 `ii+i2t`、图文全通 |
| A2 | 缺维度动态归一化 | ✅ 只通一通道时结果**恰等于该通道相似度**（未被权重稀释）；全缺 → `0.0`，非 NaN、不抛异常 |
| A3 | 权重来源 | ✅ `None` 回落 `settings.*`；传参覆盖生效；跨模态内权重默认 = 两方向算术平均 |
| A4 | 关键字专用（`*` 之后） | ✅ 第 15 个位置实参触发 `TypeError` |
| B1 | 惩罚因子范围 | ✅ cc∈[0,1] 全扫，`∈[FLOOR=0.5, 1.0]` |
| B2 | 单调性 / 连续性 | ✅ 对 cc 单调不减；`CC_LOW(0.10)`/`CC_HIGH(0.30)` 邻域连续，无跳变 → **未发现反例** |
| B3 | 触发门限 | ✅ `max(self) < SELF_HIGH(0.55)` 恒 1.0；`>= 0.55` 才触发；缺失跨模态/缺失自相似恒 1.0 |
| B4 | 开关 | ✅ `CROSS_PENALTY_ENABLED=False` 与惩罚前结果完全一致 |
| B5 | 只降权 | ✅ 惩罚因子恒 ≤1（≥FLOOR） |
| C1 | `match_source` 三分支 | ✅ `text`/`image`/`mixed` 与实际使用的入参一致（含「给了不存在的 image_path + text → 实际走 text」） |
| C2 | `legend{high,mid}` 派生 | ✅ 改 `MATCH_THRESHOLD_AUTO/MANUAL` 后 legend 随之变化；`MATCH_LEGEND_*` 覆盖生效；空结果也下发 legend |
| C3 | `matches[:20]` 上限 | ✅ 21 个候选时返回 20 条，且截断前已按相似度降序 |
| C4 | 鉴权契约 | ✅ 无 token → 403 `Not authenticated`；坏 token → 401 含「无效或过期」 |
| C5 | 路由顺序（隐性契约） | ✅ `/categories`、`/uploads/{filename:path}`、`/{item_id}`、`/{item_id}/mark-claimed` 均正确命中，未被参数化路由吞掉 |
| E1 | `--dry-run` 不写库、不落断点 | ✅ DB 逐字节不变；无 state 文件；不覆盖既有 state |
| E2 | `--backup-only` | ✅ 产出 `<db>.bak-*`，sha256 长度 64，备份为合法 sqlite，不改原库 |
| E3 | `--limit N` | ✅ 只处理 N 条 |
| E4 | 断点指纹 | ✅ 指纹不符拒绝续跑（`RuntimeError`）；`--no-resume` 忽略断点重跑；state 记录 `backend/model_name/last_id` |
| E5 | 幂等 / 失败隔离 / 不碰 color_vector | ✅ 连跑两次向量逐元素相等；图片编码失败仅计入 `failed_encode` 且不污染原图向量、文本仍更新；`color_vector` 不被改写 |
| D1 | **cn_clip ViT-H-14 真实输出维度 = 1024** | ✅ **静态架构确定**：`model_configs/ViT-H-14.json` `embed_dim=1024` → `VisualTransformer(..., output_dim=embed_dim)`、`text_projection[*, embed_dim]` → `encode_*` 输出 1024 维；并用同构小模型验证「投影输出维度 == output_dim」。**此结论无需下载权重** |
| F1 | 公开接口身份降级 | ✅ disabled 用户带合法 token 访问 `GET /items/{id}` → 404（降级匿名），未越权看到未审核物品；`GET /items/` 同理 |
| F2 | 换模型未重嵌入的后果 | ✅ 1024 维查询 × 512 维库向量 → `np.dot` 抛 `ValueError` → `/match` 吞异常**静默返回空集** |

### ② 已验证（真实模型）

**空。** 本机无权重（`models/` 不存在、无 `.pt`），且硬约束禁止下载 ~3.83GB 权重，故**没有任何结论来自真实模型前向**。凡涉及数值语义（相似度数值、Recall、阈值标定）的结论一律归入 §3「未能验证」。

> **⚠️ 后续更新（2026-09-14，本报告结论已部分失效）**：真实权重 **3.83GB 已在本机下载并端到端验证**（经 ModelScope 源，无需 `pip install modelscope`；`CLIP_CN_CKPT_PATH` 零网络加载）。因此下表 **V1 / V2 / V3 已由「未能验证」转为「已用真实模型验证」**：
> - V1 ✅ 已验证：编码 **1024 维 + L2 归一**、语义合理（`cos(查询,正例) > cos(查询,跨类别负例)`），见 `scripts/verify_real_clip.py`；
> - V2 ✅ 已验证：真实标定 `Recall@3=1.0` / `Recall@1=0.7917`，见 `docs/review/threshold-calibration-v3.5.0.md`；
> - V3 ✅ 已验证：真实加载耗时 16.2s、设备 `cpu`、ModelScope 路径走通；
> - **V5 ✅ 已验证（2026-09-14 更新）**：生产库已完成全量重嵌入（冷备 + `_exit_code` 守卫，6 条全部 1024 维），端到端实测 `POST /api/items/match` **HTTP 200**——查询「蓝牙耳机」命中同类 item68（score=0.3872 过手动阈值 0.35），4 条候选跨模态打分正常，found 类正确排除（详见 `CHANGELOG.md` §10）。
> - **V4 ✅ 已验证（2026-09-14 实验闭环）**：50 汉字截断真实语义已量化 —— ① 截断一致性：64 字完整串 vs 人工前 50 字向量 cos=1.000000（截断点=50 字、静默无异常）；② 关键信息完全落在窗口外时 cos 0.6736→0.5220（**相对损失 ~22.5%**）；③ 长文本本身有稀释效应（74 字长查询 0.67 vs 短查询 0.84）。工程结论：物品特征前置可显著保住检索力，前端 maxlength=300 与真实 50 字矛盾应加提示。
>
> 同时，在真实权重下**新发现并修复 3 处「桩路径掩盖真实路径」的缺陷**（编码器接口漂移 / 候选集重复计数 / 标定未接颜色通道），详见 `CHANGELOG.md` §9；重嵌入脚本自身的第 4 处同型缺陷（假绿迁移）亦已修复，详见 `CHANGELOG.md` §9 之后的执行轮记录。

### ③ 未能验证（写明原因）

| 编号 | 未能验证项 | 原因 |
|:--:|------|------|
| V1 | 真实 Chinese-CLIP 的 `encode_image/encode_text` **数值**（是否 L2 归一化、相似度分布） | 无权重，禁止下载 |
| V2 | 真实模型的阈值标定 / PR 曲线 / Recall@K（`calibrate_thresholds.py`） | 同上；`eval_set_v3.5.0.json` 存在但需真实编码 |
| V3 | `is_available()` 在完整运行环境下的端到端加载（设备选择、ModelScope/HF 路径） | 无权重 |
| V4 | 54 汉字截断对真实语义的实际影响 | 无权重（文本塔结构串 `RoBERTa-wwm-ext-large-chinese`、`context_length=52` 已静态核对） |
| V5 | 6 条真实物品换模型后的匹配质量 | 需真实重嵌入 |

---

## 2. 缺陷清单

### D1 —【高】`ChineseClipBackend.embed_dim` 声明错误（512 vs 真实 1024），且**无任何维度护栏**

- 位置：`backend/app/clip_backend.py:175`（`embed_dim = 512`）；对照 `:83`（`OpenClipBackend.embed_dim = 512`，此项正确）
- 复现：`tests/test_qa_v350_dimension.py::test_D_declared_embed_dim_matches_cn_clip_reality`
  ```
  AssertionError: ChineseClipBackend.embed_dim=512 与 cn_clip ViT-H-14 真实输出维度 1024 不一致
  ```
- 观察 vs 期望：
  - **观察**：`ChineseClipBackend.embed_dim = 512`；实装 `cn_clip` 的 `model_configs/ViT-H-14.json` → `embed_dim = 1024`，`create_model` 用该值作为视觉塔/文本塔投影维度（`VisualTransformer(..., output_dim=embed_dim)`、`text_projection[*, embed_dim]`），故 `encode_image/encode_text` **真实返回 1024 维**。
  - **期望**：声明值应等于真实输出维度（1024）；或提供显式投影把 1024 → 512（当前**没有**任何投影，见 `clip_backend.py:259-286`）。文件头铁律 3 与 `ClipBackend` 协议均声称「必须返回 512 维」，与实现自相矛盾。
- 影响链（放大风险）：
  1. `embed_dim` 字段**在运行期无人读取**（全仓 grep 仅声明处与测试引用）→ 属于「错误契约 + 无护栏」，本身不会直接炸；
  2. 一旦部署 `cn_clip` 而**未先重嵌入**：查询 1024 维 vs 库中 512 维（`backend/lost_found.db` 实测 512 维）→ `np.dot` 抛 `ValueError` → `/match` 在 `items.py:570-572` 被 `except: continue` 吞掉 → **静默返回空集**（用户看到「无结果」而非「模型不兼容」）；`match_service` 同理被外层 `except` 吞掉；
  3. **工程师自带测试把错误假设固化为绿色**（见 §3），真实模型冒烟被门控跳过 → 对真实路径产生**虚假信心**。
- 建议：`ChineseClipBackend.embed_dim = 1024`；并在 `encode_*` 返回前加断言 `features.shape[-1] == self.embed_dim`（或统一在 facade 处校验），使维度不匹配**显式失败**而非静默空集。

### D2 —【中】`/match` 默认阈值是 import 期冻结的第三份魔数，与 legend 的「单一数据源」承诺不一致

- 位置：`backend/app/api/items.py:25`（`MATCH_THRESHOLD = getattr(settings, "MATCH_THRESHOLD_MANUAL", 0.20)`，**模块导入时快照**）；与 `resolve_legend()`（`:29-46`，读取**实时** `settings`）并存。
- 复现（探针输出）：
  ```
  items.MATCH_THRESHOLD (import 时快照) = 0.35
  after set settings.MATCH_THRESHOLD_MANUAL=0.99
  items.MATCH_THRESHOLD (仍冻结) = 0.35
  resolve_legend() (live) = {'high': 0.55, 'mid': 0.99}
  ```
- 观察 vs 期望：legend.mid 会随 config 变，但 `/match` 无 `threshold` 时实际过滤仍用 0.35 → **图例与真实行为可能背离**。
- 影响：生产环境 config 只在启动时加载一次，通常两者一致；但任何**运行期改 config**（测试、热调参、`settings` 对象被改）都会造成 legend 骗人。宣称「消除两套魔数」的同时引入了**第三份副本**。
- 建议：`/match` 内直接用 `settings.MATCH_THRESHOLD_MANUAL`（与 legend 同源），删除模块级快照。

### D3 —【低】`--dry-run` 仍会创建 `<db>.bak-*`（文件系统副作用）

- 位置：`backend/scripts/reembed_all_vectors.py:200-213`（`backup_db` 在 `dry_run` 判断**之前**无条件执行）。
- 观察 vs 期望：docstring/铁律称「只读干跑」，但干跑会写出一份完整 DB 副本（大库代价可观，且可能因目录只读而失败中断干跑）。任务口径未禁止备份文件，故定级低。
- 证据：`tests/test_qa_v350_reembed_safety.py::test_E_dry_run_still_creates_backup_side_effect`。
- 建议：`dry_run` 时跳过冷备（或改为 `--backup-only` 显式触发）。

### D4 —【低/设计观察】换模型后**查询期**无「嵌入空间/模型指纹」标记

- 位置：DB 仅有向量列，无模型版本列；`reembed_all_vectors.py:215-231` 的指纹**仅用于续跑**校验，**无法**在查询时识别「库向量是旧模型算的」。
- 观察 vs 期望：真正的保护应是「查询期发现向量/模型不匹配即**显式报错**」。当前只能靠运维纪律（记得重嵌入），否则踩到 D1 的静默空集。
- 建议：重嵌入完成后向 DB 写入 `embedding_model` 元数据（新表/`meta` 键均可，不改现有列），启动/查询时比对。

---

## 3. 工程师测试自身的问题（比单个 bug 更值得说）

1. **桩向量抹平了一切区分度（假绿）** — `tests/conftest.py:47-53`：`_fake_image_feature` 与 `_fake_text_feature` 都返回**同一个** `np.ones(512)/√512`。其后果是所有 CLIP 相似度恒为 `1.0`，于是 `tests/test_match_contract_v350.py` 的 `match_source` 三分支、`test_v350_text_search_hits_image_only_target` 等**无论跨模态通道是否真的生效都会通过**。→ 我另写 `test_C_text_search_hits_image_only_target_with_distinct_vectors`，用「目标仅有图片」把唯一可用通道**锁定为跨模态**，才真正判定通道生效。

2. **断言与实现互为镜像** — `tests/test_cross_modal_scoring.py:74,92` 把期望值写成与实现**同一公式**（`(w_ii*1+w_cross*0+w_tt*1)/(w_ii+w_cross+w_tt)`）。若实现公式本身写错（例如把 cross 漏乘权重），测试会一起错。→ 我用**手算常量**（0.7 / 0.5 / 0.588235）对拍，才具备独立判据。

3. **把错误契约固化为绿色** — `tests/test_config_rollback.py:33` 断言 `ChineseClipBackend.embed_dim == 512`。这**恰好锁死了 D1 缺陷**：真实维度是 1024。该用例的存在使缺陷再也无法被「跑测试」发现。

4. **真实模型冒烟写错期望形状且被门控跳过** — `tests/test_real_clip_smoke.py:43,57` 断言 `vec.shape == (512,)`。若真跑 `RUN_REAL_CLIP=1`，在真实 cn_clip 下**必然失败**（真实 1024 维）；而它默认 `skip`，于是「真实模型路径」给人以**已被覆盖**的错觉。→ 这正是本报告把 ② 档留空、并把 V1 明确列入「未能验证」的原因。

5. **`--dry-run` 的副作用被当作正常行为断言** — `tests/test_reembed_script.py:112` 主动断言干跑**应当**产生 `.bak-*`（即把 D3 固化）。建议改为断言「不产生任何新文件」。

---

## 4. 结论

- **既有 111 例零回归**，本次新增 54 例中 53 例通过；唯一失败为**故意置红的缺陷探测器**（D1）。
- v3.5.0 的**跨模态数学与阶段5 惩罚**在打桩/纯数学层面**正确**（含缺维度归一化、单调性、门限、开关等易错点均未见反例）。
- `/match` 契约（match_source / legend / 20 上限 / 403·401 鉴权 / 路由顺序）**未被本次改动破坏**；公开接口身份降级亦未变差。
- 重嵌入脚本的破坏性操作**安全**（dry-run 不写库、backup-only、limit、指纹拒跑均通过），仅 D3 为低severity 副作用。
- **头号风险 D1**：`ChineseClipBackend` 的真实输出维度是 **1024**，而声明为 512；配合「查询期无模型标记 + `/match` 静默吞异常」，任何「切模型但漏重嵌入」都会**静默返回空结果**。建议在发版前修正声明并补一条维度断言，同时修正 §3 中被固化/写错的测试期望。

### 备注：真实模型验证待办（发版门禁）
以下必须在具备真实权重（或 CI 缓存权重）的环境补跑，本报告**不代跑、不臆测**：
1. `RUN_REAL_CLIP=1 pytest tests/test_real_clip_smoke.py`（并先把期望形状改为真实维度）；
2. `scripts/reembed_all_vectors.py --dry-run` 与正式重嵌入，核对重嵌入后 `/match` 非空；
3. `scripts/calibrate_thresholds.py` 回填 `MATCH_THRESHOLD_*` 与 `MATCH_W_*`。

> **✅ 执行状态更新（2026-09-14）**：
> - 待办 1 ✅ 已完成：`RUN_REAL_CLIP=1` 时 2 用例由 skip 转通过（全套件 209 用例 / 207 通过 / 2 门控 skip / 0 failed）。
> - 待办 2 ✅ 已完成：干跑验证 `ok=6/failed_encode=0`（DB 只读）；正式重嵌入已执行（冷备 `lost_found.db.bak-20260914121815`），`/match` 端到端实测 HTTP 200。
> - 待办 3 ❌ **仍禁止**：2026-09-14 扩充轮（评测集 70→84 对，n=64→78）复标后 Precision 上界 0.6129 → **0.6889**，仍 ＜ 0.90，`AUTO`/`EMAIL` 无解（返回 None）——**结构性瓶颈**（同类近重复与正样本分数不可分），继续堆查询变体收益已边际化；须待真实物品类别多样性增长复标，**不得为凑出 0.90 而放宽口径**。
