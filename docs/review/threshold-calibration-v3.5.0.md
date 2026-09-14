# v3.5.0 阈值标定报告（Threshold Calibration Report）

> **状态：真实模型已跑通；但 `AUTO` / `EMAIL` 阈值仍未能标定 → 发布门禁步骤 8 继续禁止**
> **版本**：v1.0（真实模型标定版 / Real-Model-Calibrated）| **日期**：2026-09-14 | **产出**：team-lead（齐活林）
> **上游依据**：[增量设计 §5.5 / §5.8 / §5.9](v3.5.0-incremental-design.md) · [增量 PRD](../product/PRD-v3.5.0-incremental.md) · [评测集说明](../../backend/eval/README.md)
> **脚本**：`backend/scripts/calibrate_thresholds.py` · **下载**：`backend/scripts/download_cn_clip_weights.py` · **端到端验证**：`backend/scripts/verify_real_clip.py`
> **评测集**：`backend/eval/eval_set_v3.5.0.json`

---

## 0. 结论速览（先读这一节）

| 项 | 状态 | 依据 |
|------|:--:|------|
| 真实权重获取（3.83GB，零新增依赖） | ✅ 已完成（字节校验一致） | §1 |
| 真实模型加载（`CLIP_CN_CKPT_PATH`，运行期零网络） | ✅ 已完成（16.2 s） | §2 |
| 真实编码：图/文均 **1024 维 + L2 归一化** | ✅ **已用真实模型验证** | §2 |
| 真实语义合理性（正样本 > 跨类别负样本） | ✅ 已用真实模型验证 | §2 |
| 真实 **Recall@K** | ✅ **已用真实模型验证**（@1 0.7917 / @3 1.0） | §4、§5 |
| 阶段5 跨模态一致性惩罚是否值得开启 | ✅ 开启更优（@1 **0.7917** vs 0.75） | §4.3 |
| **`MATCH_THRESHOLD_AUTO` / `EMAIL`** | ⚠️ **仍未能标定**（默认权重下 Precision≥0.90 不可达） | §5 |
| **`MATCH_THRESHOLD_MANUAL`** | ⚠️ 候选值 0.2977，**但未回填、不可用** | §5 |
| **可否据本报告回填 `.env`** | 🚫 **仍然禁止** | §5.4 |
| 评测集结构 / 退化自检（本机可复现性） | ✅ 同 v0.1，**限定「仅本机」**（见 §6.1） | §6.1 |

> **一句话**：v3.5.0 的**跨模态检索本身已被真实模型验证为可用**（Recall@3 = 1.0），
> 但**分层阈值仍不可用** —— 原因不是模型不行，而是**评测集的负样本全是「跨类别错配」**，
> 它测不出「同类别近重复」这一真实难点，因此 `Precision ≥ 0.90` 在默认权重下达不到。
> 详见 **§5**，解除路径见 **§6.2**。

---

## 1. 本次新增：真实权重获取（v0.1 的「阻塞」已解除）

v0.1 曾判定「本机无法获取权重」（旧结论：ModelScope ≈472 KB/s → 约 2.2 小时，且需 `pip install modelscope`）。**该结论有误，已作废**：

| 项 | 事实 |
|------|------|
| **HF 与 ModelScope 的仓库 ID 不同** | HF：`OFA-Sys/chinese-clip-vit-huge-patch14`（本机不可达）<br>ModelScope：**`AI-ModelScope/chinese-clip-vit-huge-patch14`**（API 0.3 s 可达） |
| **无需 `modelscope` 包** | 仓库直接提供 `clip_cn_vit-h-14.pt`，标准库 `urllib` + HTTP Range 即可下载 |
| 实测吞吐 | **≈1.4–1.5 MB/s**（旧估 472 KB/s 偏低） |
| 实际传输耗时 | **2495.8 s ≈ 41.6 min**（支持断点续传；中途机器休眠会暂停传输） |
| 落盘 | `backend/models/clip_cn_vit-h-14.pt`（`models/` 已 gitignore） |
| 字节校验 | **3,830,716,726 B**，与远端 `Content-Range` 完全一致 ✅ |

**关键核实（避免 40 分钟白等）**：下载文件与 `cn_clip` 自身的下载目标**逐字节一致** ——
`_MODELS["ViT-H-14"] == ("chinese-clip-vit-huge-patch14", "clip_cn_vit-h-14.pt")`、
`_MODELSCOPE_ORG == "AI-ModelScope"`（定义在 `cn_clip/clip/utils.py`，
**注意 `load_from_name` 不在 `clip/__init__.py`**）。

新增脚本：`backend/scripts/download_cn_clip_weights.py`（断点续传；若服务端忽略 `Range` 返回 200 则自动从零重下，避免拼接出损坏文件）。

---

## 2. 真实模型端到端验证（**首次达成「已用真实模型验证」档**）

`scripts/verify_real_clip.py` 实测（全部 PASS）：

```
【1】环境与后端契约
  CLIP_BACKEND=cn_clip | CLIP_CN_MODEL_NAME=ViT-H-14 | CLIP_CN_EMBED_DIM=1024
  backend class = ChineseClipBackend     backend.embed_dim = 1024
  struct "ViT-H-14@RoBERTa-wwm-ext-large-chinese" 与 cn_clip 官方声明精确匹配
  model_configs/ViT-H-14.json、RoBERTa-wwm-ext-large-chinese.json 均存在

【2】真实加载（零网络）
  权重加载 + 首次编码 = 16.2 s
  Model info: embed_dim=1024, vision_width=1280, text_hidden_size=1024（与文档口径一致）

【3】编码维度与归一化
  文本向量 shape=(1024,)  norm=1.000000
  图片向量 shape=(1024,)  norm=1.000000

【4】语义合理性（评测集真实正样本 P01 vs 跨类别负样本 N01）
  cos(查询文本, 正样本图) = +0.2713
  cos(查询文本, 跨类别图) = +0.2016
  差值 = +0.0698   → 正样本显著高于跨类别样本 ✅
```

同时 `RUN_REAL_CLIP=1` 运行 `tests/test_real_clip_smoke.py`：

```
test_real_image_embedding_dim_l2_normalized          PASSED
test_real_long_text_embedding_dim_l2_normalized      PASSED
```

> 这 2 条用例正是全套件**恒为 `skipped=2`** 的来源；设置 `RUN_REAL_CLIP=1` 后由 skip 转 passed。

**重要观察**：真实 Chinese-CLIP 的**跨模态余弦绝对值偏低**（正确 ≈0.27、错配 ≈0.20），
这与设计初值 `AUTO=0.55 / EMAIL=0.70` 的直觉严重不符 —— 初值对本模型而言**过高**。这一点直接触发了本次标定。

---

## 3. 标定过程中发现并修复的 **2 个真实缺陷**（重要）

真实权重首次可用后，标定脚本立刻暴露出两个**只在真实路径下才会出现**的缺陷。
二者都属本项目反复强调的「假绿」类：**假编码器定义了接口/掩盖了数据形态，真实实现从未被执行过**。

### 3.1 编码器接口漂移 —— 真实编码路径**从未被执行**

```
AttributeError: 'CLIPService' object has no attribute 'encode_text'
```

- **根因**：`_EncoderCache` 调用 `encoder.encode_text()` / `encode_image()`，
  而这两个名字**只有 `_FakeEncoder` 才有**；真实 `clip_service`（`CLIPService`）
  暴露的是 `get_text_feature()` / `get_image_feature()`。
  → **假编码器定义了接口，真实编码器从未被接上。**
- **为何长期未被发现**：`--fake-encoder` 冒烟一路绿灯；真实权重此前不可得，
  该分支从未执行 → 连「管线已跑通」的结论也只是**假路径**下的结论。
- **修法**：新增 `_ServiceEncoderAdapter`，**让脚本适配服务的冻结接口**
  （`clip_service` 公开方法名与签名是冻结契约，改名会让 conftest 打桩全面失效），
  而不是反过来改服务。

### 3.2 候选集重复计数 —— Recall@K 被严重低估（**曾误报「阻塞性发现」**）

修复 3.1 后首次真实标定给出 `Recall@1 = Recall@3 = 0.0`，并触发脚本的
`🚨 阻塞性发现：Recall@3 < 0.90`。**该结论是错的**，根因在候选集构造：

- `_candidates()` 原按 `item_ref or text` 去重，但**同一条物品在不同 pair 里表达方式不同**：
  `P01~P04` 给的是 `target.item_ref`（图片），`P21~P24` 给的是 `target.text`（`item_ref=null`）。
- 于是**同一条物品被拆成两个候选**：实测 **10 个候选 = 6 条物品 + 4 条幻影重复**。
- 幻影副本只有文字、没有图 → 可用通道不同 → 打分不同 → **正确目标被自己的幻影副本挤出 Top-3**。

**修法**：改为按**物品身份**（`item_id`）去重，并**合并**同一条物品在不同 pair 中出现的字段
（只有图的补文字、只有文字的补图），以还原生产里「一条真实物品同时有图与文」的形态
（这正是 `/match` 的真实打分对象）。`_recall_ranks` 的匹配键同步改为 `_candidate_key`。

**修复前后对照（同为真实模型、默认权重）**：

| | 候选数 | Recall@1 | Recall@3 |
|------|:--:|:--:|:--:|
| 修复前（重复计数） | 10 | **0.0** | **0.0** |
| 修复后 | 6 | **0.7917** | **1.0** |

**独立交叉验证**：用另一段独立实现的逐对排名诊断（按 `item_id` 去重、逐样本输出排名）
得到 `Recall@1 = 0.7917`、`Recall@3 = 1.0`、排名分布 `1=19 / 2=5 / 3+=0` —— 与修复后脚本**完全一致**。

> 教训（与 v0.1 的「假绿三层结构」同类）：**门控/桩化的路径必须被真实执行一次**才可信；
> 「管线跑通」若只在假编码器下成立，就不构成真实结论。

---

## 4. 真实标定结果（`cn_clip` + `ViT-H-14`，有效集 24 正 / 30 负）

### 4.1 Recall@K（真实模型，默认权重）

| 指标 | 值 |
|------|:--:|
| Recall@1 | **0.7917** |
| Recall@3 | **1.0** |
| Recall@5 | 1.0 |
| Recall@10 | 1.0 |

**逐样本排名分布**：`rank1 = 19`、`rank2 = 5`、`rank≥3 = 0`（n=24）。

**5 个 rank-2 样本全部是同类别近重复混淆**：

| 样本 | 正确目标 | 被谁挤到第 2 |
|:--:|:--:|------|
| P01–P04 | item **64**（蓝牙耳机 白色蓝牙耳机） | item **68**（蓝牙耳机 白色的） |
| P17 | item **77**（学生证） | item **67**（房卡 丢失一个宿舍钥匙） |

→ **跨类别检索零错误**；全部残差都发生在「同类别、外观/文本高度相似」的两条物品之间。

### 4.2 阶段5 跨模态一致性惩罚（对照）

| 配置 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |
|------|:--:|:--:|:--:|:--:|
| `with_penalty=True` | **0.7917** | 1.0 | 1.0 | 1.0 |
| `with_penalty=False` | 0.75 | 1.0 | 1.0 | 1.0 |

→ 惩罚开启时 Recall@1 更高（+0.0417），**满足** `Recall@3(on) >= Recall@3(off)` 断言，
**维持 `CROSS_PENALTY_ENABLED=true`**。

### 4.3 权重网格 Top-5（目标：`Precision≥0.90` 处最大化 Recall@3）

| # | W_IMG_IMG | W_CROSS | W_TEXT_TEXT | W_COLOR | auto 阈值 | Recall@1 | Recall@3 |
|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 1 | 0.05 | **0.0** | 0.05 | **0.9** | 0.5924 | 0.7917 | 1.0 |
| 2 | 0.05 | **0.0** | 0.10 | **0.85** | 0.5924 | 0.7917 | 1.0 |
| 3 | 0.05 | **0.0** | 0.15 | **0.80** | 0.5924 | 0.7917 | 1.0 |
| 4 | 0.05 | **0.0** | 0.20 | **0.75** | 0.5924 | 0.7917 | 1.0 |
| 5 | 0.05 | **0.0** | 0.25 | **0.70** | 0.5924 | 0.7917 | 1.0 |

> ⚠️ **这组结果不可用于回填 config** —— 理由见 §5.3。它反映的是**评测集缺陷**，不是算法洞察。

---

## 5. 为什么 `AUTO` / `EMAIL` 阈值仍标不出来

### 5.1 现象

真实 PR 曲线（默认权重）**Precision 上限仅 0.7692**（对应 Recall 0.8333），
**从未达到 0.90** → 脚本按取法返回：

| 阈值 | 口径 | 结果 |
|------|------|:--:|
| `MATCH_THRESHOLD_AUTO` | Precision ≥ 0.90 最低分位 | **None**（不可达） |
| `MATCH_THRESHOLD_EMAIL` | Precision ≥ 0.98 最低分位 | **None**（不可达） |
| `MATCH_THRESHOLD_MANUAL` | Recall ≥ 0.90 最高分位 | 0.297653（候选） |

### 5.2 根因：评测集的负样本**全部是跨类别错配**

评测集 `label_rule` 与 `notes` 明确：负样本为「跨类别错配（如 电子产品查询 × 证件卡片物品）」。
因此该评测集**只能测量「跨类别能否分开」，测不出「同类别近重复能否分开」** ——
而 §4.1 显示**后者恰恰是唯一的错误来源**。

### 5.3 网格 Top-5 的「颜色捷径」说明了同一件事

Top-5 全部把 `W_COLOR` 拉到 0.7~0.9、把 `W_CROSS` 压到 **0.0**。
这不是「颜色比跨模态更有效」的正确结论，而是：
**在全是跨类别负样本的集合上，颜色直方图是「类别」的代理特征**（电子产品偏暗、证件偏浅…），
于是它被网格搜索当成捷径利用了。

> 若据此回填 `W_COLOR=0.9 / W_CROSS=0.0`，等于**用一个即将被真实数据证伪的评测集缺陷，
> 换掉 v3.5.0 的核心能力（跨模态检索）** —— 这正是本项目一贯反对的「为指标而指标」。

### 5.4 因此的处置

1. **禁止**回填任何阈值/权重到 `.env`（`MATCH_THRESHOLD_MANUAL=0.2977` 亦不得使用）；
2. `config.py` 各项**保持设计初值**，但须注意 **`AUTO=0.55` / `EMAIL=0.70` 对本模型偏高**
   （真实正确对 ≈0.27），故灰度期**必须** `AUTO_MATCH_ENABLED=false`，仅手动匹配可用；
3. 解除路径见 §6.2。

---

## 6. 复现前提与下一步

### 6.1 ⚠️ 「缺失 0」**不具备可分发性**（v0.1 限定保留）

评测集**不是自包含的**：

| 依赖 | 位置 | 版本控制 |
|------|------|:--:|
| 6 张物品图片 | `backend/uploads/*.jpg` | **未跟踪** |
| 6 条物品记录 | `backend/lost_found.db` | **未跟踪**（隐私取舍） |

→ 本报告 §3–§5 的全部数值**只在持有生产数据的机器上可复现**；新克隆执行 `--stats` 会报「缺失 6」。
恢复方式见 `backend/eval/README.md` §1.1。

### 6.2 解除 `AUTO` / `EMAIL` 阻塞的唯一路径：补**同类别硬负样本**

要让 `Precision ≥ 0.90` 成为可达目标，评测集必须包含「同类别、难以区分」的负对。
当前 6 条物品可构造的同类别负对**有限**：

- item **64** ⟷ item **68**（同为电子产品、均为白色蓝牙耳机）—— 即 §4.1 全部 4 个错误的来源；
- item **64 / 68** ⟷ item **73**（电子产品内部）；
- item **67** ⟷ item **77**（均为卡片类）。

建议：**随真实数据增长持续补入同类别硬负对**，并重跑 `--grid`。在硬负样本到位前，
`AUTO` / `EMAIL` 阈值应**视为不可标定**，而非「用现有数据凑一个」。

### 6.3 复现命令

```bash
# 0) 下载权重（仅首次；约 42 分钟，可断点续传）
venv\Scripts\python.exe scripts\download_cn_clip_weights.py

# 1) 端到端真实验证
set CLIP_BACKEND=cn_clip
set CLIP_CN_CKPT_PATH=<abs>\backend\models\clip_cn_vit-h-14.pt
venv\Scripts\python.exe scripts\verify_real_clip.py

# 2) 真实冒烟（那 2 条 skip 应转为 passed）
set RUN_REAL_CLIP=1
venv\Scripts\python.exe -m pytest tests\test_real_clip_smoke.py -v

# 3) 真实标定
venv\Scripts\python.exe scripts\calibrate_thresholds.py --grid
```

---

## 7. 发布门禁影响（设计 §5.8）

| 步骤 | 状态 |
|:--:|------|
| 1–2 代码冻结 / 测试全绿 | ✅ 绿（`192 tests / 0 failed / 0 errors / 2 skipped`，`--junitxml` 为准） |
| 3 冷备 + 真实重嵌入 | ✅ **阻塞已解除**（权重就绪）｜⏸ **未执行**（会改写生产库，须单独批准） |
| 4 干跑 ETA | ⏸ 未执行（依赖 3 的批准） |
| 5 真实标定 | ⚠️ **部分完成**：Recall@K 已真实标定；**阈值仍不可用**（§5） |
| 6 灰度（`AUTO_MATCH_ENABLED=false`） | ⏸ 未开始 |
| 7 生成标定报告 | ✅ **本文件（v1.0，含真实数值）** |
| 8 回填阈值 + 开启自动推送 | 🚫 **禁止**（`AUTO`/`EMAIL` 为 None，§5.4） |

> **门禁结论**：v3.5.0 **仍不具备「以标定阈值全量开启自动推送」的发布条件**，
> 但阻塞原因已从「拿不到真实权重」**收敛**为「评测集缺同类别硬负样本」——
> 这是一个**可执行的、有明确终止条件**的工程问题（§6.2）。

---

## 8. 验证等级声明（诚实性要求）

| 档位 | 本轮是否达成 |
|------|:--:|
| **已打桩验证**（stub-verified） | ✅ 达成（结构校验 / 退化自检 / 管线冒烟 / 全套 192 用例） |
| **已用真实模型验证**（real-model-verified） | ✅ **本轮首次达成** —— 真实权重加载、1024 维 + L2 归一化、语义合理性、**真实 Recall@K**、阶段5 惩罚对照 |
| **未能验证**（附原因） | ① `AUTO`/`EMAIL` 阈值 —— 评测集缺同类别硬负样本（§5.2）；② 真实重嵌入后的全库一致性 —— 未执行会改写生产库（§7 步骤 3）；③ 真实 P95 时延 —— 未压测 |

> **可如实表述**：「v3.5.0 的跨模态检索已用真实 Chinese-CLIP 模型验证（Recall@3 = 1.0）」。
> **不可表述**：「阈值已标定」「自动推送已可开启」。

---

> **维护约定**：本文件为**发布前置产物**。同类别硬负样本补入后须重跑 `--grid` 并再次递增版本；
> 届时若 `AUTO`/`EMAIL` 可标定，方可解除 §7 步骤 8 的禁止。
