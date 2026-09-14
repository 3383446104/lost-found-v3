# 项目长期约定 — 校园失物检索平台（lost-found-v3）

> 只记录跨会话有价值的约定与坑位。日常进展写当日日志。**代码为唯一真相源**（文档历史上曾长期滞后）。

## 技术栈与规模（v3.3.3 / 2026-09-12 基线）

- 后端 FastAPI 0.115 + SQLite + CLIP ViT-B-32（`backend/app/`，6 路由模块 / **36 端点**）
- 前端 Vue 3 + Element Plus + Pinia + Vue Router（`lost-found-frontend/src/`，**9 个路由页面**）
- 数据层 5 张业务表（users / items / matches / notifications / announcements）+ `stats_counters` 计数器表
- 启动：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`（在 `backend` 下）

## 必须知道的坑位（踩过）

1. **`database.py:13` 的 `DB_PATH` 是 import 期绑定的模块级全局量**。要让代码连别的库，必须 monkeypatch `app.database.DB_PATH`；改 `settings.DATABASE` **无效**。
2. **`clip_service` 是单例 + 懒加载**，任何真实调用都会加载模型（cn_clip `ViT-H-14` ≈3.8GB / open_clip `ViT-B-32` ≈600MB）。测试/脚本里必须打桩 `get_image_feature` / `get_text_feature` / `get_color_histogram`。导入 torch/open_clip 本身约需 13s。
3. **`config.py` 的 `SECRET_KEY` 无默认值**，`.env` 必须存在，否则应用直接启动失败。测试里应在 import 应用前 `os.environ.setdefault("SECRET_KEY", ...)` 兜底。
4. **`items.py` 的路由顺序是隐性契约**：静态路径（`/categories`、`/uploads/{filename:path}`）与 `/{item_id}/mark-claimed` 必须排在 `/{item_id}` 之前，否则被参数化路由吞掉。历史上已复发两次（CHANGELOG Bug #4 / #7）。
5. **`users.role` 字段语义重载**：既表示授权角色（user/admin），又表示账号状态（disabled/deleted）。导致 `admin.py` 的 `toggle_status` 直接覆写 role，**管理员被禁用后再启用会降级为普通用户**。未修。
6. **时间口径**：SQLite `CURRENT_TIMESTAMP` 存 UTC、格式 `YYYY-MM-DD HH:MM:SS`（固定宽度，可安全做字符串字典序比较）；对外展示统一用 `utils/time_utils.py` 转 `Asia/Shanghai`。统计"今日"必须按北京时间当日反推 UTC 半开区间，**不要**用本地日期前缀 LIKE。
7. **鉴权双轨**：受保护接口走 `Depends(get_current_user)`；但 `GET /api/items/` 与 `GET /api/items/{id}` 是**公开接口**，内部手动 `verify_token` 解析 viewer，因此绕过统一鉴权的账号状态校验（已知残留，未修）。
8. **两代模型的文本上限（均为 2026-09-13 实测，非推断）**：
   - **旧 `open_clip ViT-B-32`（英文塔 + CLIP BPE，ctx=77，每个汉字 ≈2 token）→ 纯汉字串可用 **37 字，第 38 字起被截断**。测定法：**编码后 `decode` 回读、数字符存活数**（⚠️ 用「eot 位置」判断会假阳——截断后 eot 仍在末尾，我第一次就测错了）。PRD 长期写的「33 字即触顶」是**错的**，已更正。
   - **新 `cn_clip ViT-H-14`（RoBERTa 中文塔，`tokenize(..., context_length=52)`）→ 可用 50 汉字**；超长**静默截断、不抛异常**，只保留前 50 字。
   - 改善幅度：**37 → 50（约 +13 汉字）**，方向不变但数字务必用这两个实测值。
   - 连带影响生产：`items.py:126`（新建）与 `:392`（编辑）把 `f"{title} {description}".strip()` 整串喂给文本塔、`:508` 查询侧同理 → **描述超出上限的尾段对文本向量零贡献且不报错**。前端 `MatchView.vue:44` 的 `maxlength="300"` + `show-word-limit` 计数器与真实上限矛盾（已派修）。
9. **`pip install cn_clip` 必须加 `--no-deps`**：其 `requirements.txt` 硬钉 `lmdb==1.3.0`，Windows 无 wheel 会编译失败。PyPI 版 **1.6.0**（非 git 仓库 setup.py 的 1.5.1）实测 `--no-deps` 可装，且**包内资产齐全**（`cn_clip/clip/vocab.txt`、`model_configs/ViT-H-14.json`、`model_configs/RoBERTa-wwm-ext-large-chinese.json` 均在）——早先担心的 `data_files` 资产丢失（C4）**未发生**，无需 git 兜底。`tokenize` 只依赖包内 `vocab.txt`，**无需权重**即可自检。
10. **真实权重获取（2026-09-14 已打通，此前「不可行」结论作废）**：`ViT-H-14` 权重 3830.7MB。**ModelScope 仓库 ID 与 HF 不同** —— ModelScope 是 `AI-ModelScope/chinese-clip-vit-huge-patch14`（API 0.3s 可达），HF 是 `OFA-Sys/...`（本机不可达）。该仓库直接提供 `clip_cn_vit-h-14.pt`，**标准库 urllib + HTTP Range 即可下，不需要 `modelscope` 包**；实测 **~1.4MB/s → ETA ~40min，支持断点续传**。脚本 `backend/scripts/download_cn_clip_weights.py`，落 `backend/models/`（已 gitignore）。
    - **加载**：设 `CLIP_CN_CKPT_PATH=<abs .pt>` 即零网络加载；`CLIP_CN_MODEL_NAME` 必须是**架构串** `ViT-H-14`（不是 HF repo id）—— 它有**双重语义**：ckpt 路径当架构串、下载路径当 `load_from_name` 的 name（cn_clip 也吃架构串）。
    - **已核实**（定义在 `cn_clip/clip/utils.py:106`，**不在** `clip/__init__.py`）：`_MODELS["ViT-H-14"]=("chinese-clip-vit-huge-patch14","clip_cn_vit-h-14.pt")` ⇒ 下载文件与 cn_clip 自身目标一致；`_MODEL_INFO["ViT-H-14"]["struct"]=="ViT-H-14@RoBERTa-wwm-ext-large-chinese"` ⇒ 与 `clip_backend.py:278-283` 构造串精确匹配；`create_model` 用 `load_state_dict(strict=True)` + 两份 `model_configs/*.json` 的 `assert os.path.exists` ⇒ **配错是「响亮失败」，非静默降级**。
    - ⚠️ **耦合**：`clip_backend.py` 的 `_CN_TEXT_MODEL_NAME` 硬编码 `RoBERTa-wwm-ext-large-chinese`，**仅对 ViT-H-14 成立**（ViT-B-16 / ViT-L-14 的 struct 是 base）。换视觉塔必须同步改文本塔。
11. **【已修 R2】向量维度错配是「静默失败」**：`cn_clip ViT-H-14` 输出 **1024 维**（联合投影维度，不是 vision_width 1280），错配会被 `except→continue` 吞掉，返回 HTTP 200 + `matches:[]` 像正常未找到。**修复**：`config.py` 增 `CLIP_CN_EMBED_DIM=1024` / `CLIP_OPEN_EMBED_DIM=512`；`clip_backend.py:_assert_embed_dim` 编码后断言维度；`items.py:567` 加打分前预检 → `HTTPException(500)`；`match_service.py` 同预检。**教训保留**：任何「声明式契约常量」都必须有运行期断言。
12. **测试「镜像实现」反模式已出现两次**：`tests/test_config_rollback.py:24/:33` 直接断言 `backend.embed_dim == 512`；`tests/test_cross_modal_scoring.py:74/:92` 期望值同样照抄实现公式。**部分修复（T2）**：cross-modal 两个用例 de-mirror 为字面常量 + 公式注释（`expected = 10/17` / `0.7`），改 `MATCH_W_*` 会不一致地报错；config-rollback 仍待改。
13. **【已修 T1】`conftest.py` 桩函数原无区分度（假绿根源）**：旧 `_fake_image_feature`/`_fake_text_feature` 都返回 `np.ones(512)/norm` → 所有 cosine = 1.0 → /match 契约测试 false-green。现改为 `_derive_vector(seed, dim)`（sha256→`default_rng`→标准正态→L2），图/文**命名空间隔离**（`b"image:"` / `b"text:"`），维度由 `_active_embed_dim()` 从 config 取。实测同文本 cos=1.0、异文本 0.0047、文↔图 −0.0135。要真验跨模态仍须让**目标只有图片、无 text_vector** 把可用通道锁死为 `t2i`。
14. **【已修】`test_real_clip_smoke.py` 原硬编码 `shape==(512,)`**：真实 ViT-H-14 是 1024 维 → 跑 `RUN_REAL_CLIP=1` 必挂，而默认被门控 skip → **失败被 skip 藏住**，还制造「真实路径已覆盖」的错觉。现改用 `_active_embed_dim()` 从 config 取维度（已核实 :51/:65 不再硬编码）。**教训保留：门控 skip 的测试要单独审计断言是否仍成立**。
15. **【已修 T4】`items.py:25` `MATCH_THRESHOLD` 是 import 期快照**（旧），与 `resolve_legend()` 的实时读 `settings` 语义不一致 → 改 config 后 legend 与过滤阈值背离。**修复**：改为 `_match_threshold_default()` 函数调用时读 `settings.MATCH_THRESHOLD_MANUAL`，与 `resolve_legend()` 共享同一来源。
16. **【已修 T5】`scripts/reembed_all_vectors.py:200-213` 冷备在 `dry_run` 之前** → `--dry-run` 仍产 `<db>.bak-*`，与「只读干跑」语义不符。**修复**：冷备包裹在 `if not dry_run:` 内，仅 `backup_only=True` 仍走冷备。同步更新 `tests/test_qa_v350_reembed_safety.py::test_E_dry_run_still_creates_backup_side_effect` 与 `tests/test_reembed_script.py::test_dry_run_does_not_write_db_and_has_eta` 的契约断言（前者 docstring 明确写了「若未来改不备份则本用例同步更新」——是工程师/QA 自留的「现状记录」）。
17. **【2026-09-14 已达成】「已用真实模型验证」档**：真实权重已下载并端到端验证（见 #19）。`RUN_REAL_CLIP=1` 跑 `tests/test_real_clip_smoke.py` → 2 例**由 skip 转 passed**（即恒 `skipped=2` 的来源）。标定脚本已可用（**不加** `--fake-encoder` 才走真 `clip_service`）→ 产出真实 Recall@K。⚠️ 但**分层阈值仍不可标定**（见 #19）。
18. **测试所有权规则（v3.5.0 期间明确）**：作者维护自己的测试，**实现者不得越界编辑 QA 的断言**。曾有 `test_qa_v350_dimension.py` 中 2 条断言被实现者直接改动 → 待严过关 429 重置（2026-09-14 19:20）后**重新推导**。

19. **【2026-09-14 真实权重落地】真实模型验证结果 · 标定脚本两个真实缺陷 · 阈值仍不可标定**
    - **已达成「已用真实模型验证」**：`scripts/verify_real_clip.py` 四段全 PASS —— 真实加载 16.2s、图/文均 **1024 维 + L2 归一**、`cos(查询文,正样本图)=+0.2713 > cos(查询文,跨类别图)=+0.2016`。
    - ⚠️ **真实跨模态余弦绝对值很低**（正确 ≈0.27 / 错配 ≈0.20）→ 设计初值 `AUTO=0.55` / `EMAIL=0.70` **对本模型偏高**；灰度期必须 `AUTO_MATCH_ENABLED=false`。
    - **真实 Recall@K**：@1 **0.7917** / @3 **1.0** / @5 1.0（有效集 24 正 / 30 负）。5 个 rank-2 **全部**是同类别近重复混淆（item **64 vs 68** 白色蓝牙耳机、item **77 vs 67** 卡片类）→ **跨类别零错误**。
    - **阶段5 惩罚**：开启更优（@1 0.7917 vs 0.75）→ 维持 `CROSS_PENALTY_ENABLED=true`。
    - ❗**`AUTO`/`EMAIL` 仍标不出来**：默认配置下真实 PR 曲线 Precision 上限仅 **0.6129**（< 0.90）→ 两值均为 `None`。
      - ⚠️ **【2026-09-14 更正，先前的「颜色=类别代理捷径」结论是错的】**：当时看到「网格 Top-5 全是 `W_COLOR` 0.7~0.9 / `W_CROSS` 0.0」，我推断那是捷径 → **被证伪**：真实原因是**标定脚本根本没接颜色通道**（见下 ③），`W_COLOR` **数学上完全惰性**，那列数字是**并列时的任意代表**。补同类硬负样本后该「偏好」依旧出现，才促使查清真相。**教训：排序结果的「值」先怀疑是否被并列/惰性维度污染，再解释成因。**
      - 解除路径（已执行其一半）：补**同类别硬负样本**（素材 64⟷68、64/68⟷73、67⟷77）→ 已补 10 对（N31–N40）；结果 `Recall@K` **不变**（0.7917/1.0），Precision 上限**进一步降到 0.6129**（预期且正确）。
    - **三个真实缺陷（全属「桩路径掩盖真实路径」，真实权重下才暴露）**：① **编码器接口漂移** —— 脚本调 `encode_text/encode_image`，真实 `clip_service` 只有 `get_text_feature/get_image_feature`；**假编码器定义了接口、真实编码器从未被接上** → 加 `_ServiceEncoderAdapter`（**适配服务的冻结接口，不改服务**）。② **候选集重复计数** —— `_candidates` 按 `item_ref or text` 去重致**同一物品被拆成两个候选**（实测 **10 = 6 物品 + 4 幻影**），正确目标被自己的幻影副本挤出 Top-3 → Recall@1/@3 被算成 **0.0** 并**误报「🚨 阻塞性发现」** → 改按 `item_id` 去重 + **合并字段**。③ **标定未接颜色通道（2026-09-14）** —— `score_pair`/`score_pair_vs_target` 只传 `(q_img,q_text,t_img,t_text)`，**不传 `color1/color2`**；而线上两处都传（`match_service.py:104` / `items.py:614`）→ `has_col` 恒 False → **`W_COLOR` 惰性**（实测 `color_weight` 取 0.0/0.15/0.5/0.9 得分**完全相同**）→ **修法：与线上一致传入颜色直方图**（`_ServiceEncoderAdapter.encode_color` + `_EncoderCache.color`）。**接上后网格真实结论：`W_COLOR` 取值分布单调递减（`{0.0:56,0.05:22,0.1:12,0.15:8,0.2:4}`）⇒ **`W_COLOR≈0`**、文本主导。**
    - ★ **三条通用教训**：**(a)** 门控/桩化的路径**必须被真实实现执行过一次**才可信，否则「管线已跑通」只是假路径结论（本项目已因此踩 3 次）；**(b)** Recall@K 异常低时，**先查候选池去重**，再怀疑模型；**(c)** 网格/Top-N 结论必须附**合格集合分布**——`summarize_grid` 显示合格组合 **103** 个、其中 **102** 个并列 `Recall@3=1.0`，故 Top-N **顺序无意义**。
    - **基线**：全套件 **201 用例 / 0 failed / 0 errors / 2 skipped**（`RUN_REAL_CLIP=1` 时 2 skip 转 pass）；新增 `test_calibrate_candidates.py`(7) / `test_calibrate_color_channel.py`(5) / `test_calibrate_grid_summary.py`(4)；报告 `docs/review/threshold-calibration-v3.5.0.md` 已重生成（含 §5 合格集合分布）。

20. **⚠️【2026-09-14 实测】v3.5.0 处于「代码已切模型、数据未迁移」的悬挂态（回答"能否开新迭代"的关键事实）**
    - **`.env` 未覆盖任何 `CLIP_*` / `MATCH_*` / `AUTO_MATCH_ENABLED`**（实测仅含 `SECRET_KEY` 等）→ 全部走 `config.py` 默认。
    - **默认 `CLIP_BACKEND="cn_clip"`（1024 维），但 `lost_found.db` 实测 `image_vector`/`text_vector` 全为 512 维**（6 条 item，即旧 open_clip 遗留）→ R2 维度防线触发 → `POST /api/items/match` → **HTTP 500**；`match_service` 记 `ERROR` 并 `return`（自动匹配不推送）。**结论：cn_clip 尚未在生产生效，必须重嵌入（门禁步骤 3）后才算落地。**
    - **`AUTO_MATCH_ENABLED` 默认 `True`**（注释写明"灰度期置 false"，但未置）→ 一旦重嵌入完成，自动推送会**立刻开启**，而 `AUTO` 阈值尚未标定（config 初值 0.55）→ **重嵌入前必须先置 false**。
    - **权重加载不需要 `CLIP_CN_CKPT_PATH`**：不设时走 `load_from_name("ViT-H-14", download_root="models", use_modelscope=True)`；`download_root` 是**相对路径（依赖 cwd=backend）**，命中 `backend/models/clip_cn_vit-h-14.pt` 本地文件**不重新下载**（实测 16.2s 加载，日志 `source=ViT-H-14` 即证）。设 `CLIP_CN_CKPT_PATH` 更明确但非必需。
    - **库现状**：items 6 / matches 85 / users 54 / notifications 198 / announcements 1；`color_vector` 27 维 6 条全有（不受模型切换影响，无需重算）。
    - ★ **推论**：重嵌入是**昂贵且需授权**的一次性操作 → **应"先定模型、再做迁移"**，避免迁一次、换模型再迁一次。

21. **【2026-09-14 干跑暴露】**`reembed_all_vectors.py` 同样踩了「假编码器定义接口、真实编码器从未接上」的坑（**同型缺陷第 4 例**）
    - **症状**：用真实 `clip_service` 跑 `--dry-run` → 6 条物品 × 2 = 12 次全部 `AttributeError: 'CLIPService' object has no attribute 'encode_image'`，`ok=0` / `failed_encode=12`；更糟的是 `main()` 恒返回 0 ⇒ 真跑会**假绿迁移**：成功退出、库中向量**分毫未动**，运维以为已迁移。
    - **根因**：脚本按 `encoder.encode_image/encode_text` 调用；真实 `clip_service` 只有 `get_image_feature/get_text_feature`。测试注入的 `FakeEncoder` 定义了 `encode_*`，所以单测全绿。
    - **修法**（与 `calibrate_thresholds._ServiceEncoderAdapter` 同型）：脚本内加 `_ServiceEncoderAdapter` 适配冻结的服务接口；`main()` 用它包 `clip_service`。**关键**：`name`/`model_name` 委托给真实后端（写死会破坏 `model_fingerprint` 的断点指纹，导致换模型后续跑防护失效）。
    - **配套**：`main()` 原本恒返回 0 → 抽 `_exit_code(stats, dry_run)` 纯函数：真跑时 `failed_encode>0` → 2、 `ok==0 且 total>0` → 3、其他 → 0。`--dry-run` 失败仍返回 0（只读预览不判失败，避免吓到人）。
    - **守卫**：`tests/test_reembed_encoder_wiring.py`（8 例，纯测试不加载模型）：适配器 `encode_image/encode_text/get_backend/name/model_name` 接线 + `_exit_code` 四分支。
    - **修后真实干跑**：`ok=6 / failed_encode=0`，模型加载 ~17s + 6 条编码 ~13s（CPU），`DB_HASH` 前后一致（确证只读），**真正可执行步骤 3**。
    - ★ **第 4 次同型教训**（方法论升级）：**(a)** 凡是「脚本/函数」按「接口名」调用外部服务，**接口名必须与服务公开 API 完全一致**，否则只测得到 fake 路径；**(b)** **任何「成功退出」的可执行脚本都必须校验实际效果**（用 `failed==0 && ok>0`），否则静默退化时无法告警 —— 这是**「假绿迁移」**的根因。两条合起来：**「fail-loud」+ 「fake 必须与真实同型」**。

## 测试约定

- 套件在 `backend/tests/`（`conftest.py` + **22 个测试文件**），**209 用例 / 207 passed / 2 门控 skip**（2026-09-14 重嵌入缺陷修复后基线；`RUN_REAL_CLIP=1` 时 2 skip 转 pass）；用 FastAPI `TestClient`。
- **本机 shell 坑位**：bash `ls/find/tail/head/mkdir/sleep` 全 `command not found`（shim 坏）→ **改用 PowerShell 工具**，但它**不回传 stdout** → 必须 `... 2>&1 | Out-File -Encoding utf8 <log>` 再用 Read 读；**不要**用 here-string 传多行脚本给 `python -c`（引号会被剥掉），改写成临时 `.py` 文件再跑。venv 解释器：`backend\venv\Scripts\python.exe`（Glob 搜不到 .exe，用 `Test-Path` 确认）。
- 夹具已实现三重隔离：临时库（monkeypatch `DB_PATH`）、临时上传目录、CLIP 打桩、阻断真实 SMTP。
- 运行（在 `backend` 目录）：`venv\Scripts\python.exe -m pytest tests/ --junitxml=.junitxml/<name>.xml`
- **退出码不可信**（本机沙箱恒返回 1）→ **必须读 `--junitxml` 的 failures/errors 计数**下结论。
- `POST /api/items/` 落库为 `status='pending', review_status='pending'`，而 `/match` 只扫 `active + approved` → **契约类测试建完物品必须调用 `approve_item` 夹具**，否则拿到空 matches（已踩，`test_match_contract_v350.py`）。
- 首次需先装测试依赖：`venv\Scripts\python.exe -m pip install -r requirements-dev.txt`

## 算法口径（易与文档不一致）

- **v3.4.1 及以前**：相似度三通道加权 图 **0.50** / 文 **0.30** / 色 **0.20**，缺失维度按比例重归一化。
- **v3.5.0 起（四通道 + 跨模态）**：`CLIP_BACKEND="cn_clip"` + `CLIP_CN_MODEL_NAME="ViT-H-14"`；权重 `W_IMG_IMG=0.35 / W_CROSS=0.35 / W_TEXT_TEXT=0.15 / W_COLOR=0.15`，跨模态内部分 `W_CROSS_T2I=0.5 / W_CROSS_I2T=0.5`；阈值为初值 `MANUAL=0.35 / AUTO=0.55 / EMAIL=0.70`，`MATCH_LEGEND_HIGH/MID=None`（由阈值派生，不硬编码）。以上全部 **config 驱动、无硬编码**，切配置即可回滚到 `open_clip`。
- **阶段5 跨模态一致性惩罚**：`cc = min(cross_t2i, cross_i2t)`，仅当 `max(sim_ii, sim_tt) >= CROSS_PENALTY_SELF_HIGH(0.55)` 触发，**只降权不升权**（penalty ∈ [0.5,1.0]，单调），可由 `CROSS_PENALTY_ENABLED` 开关。
- 分层阈值（v3.4.1 版）：手动 **0.20** / 站内自动通知 **0.65** / 邮件 **0.75**；自动推送 Top-3。

## v3.5.0 关键结构（模型可回滚）

- `app/clip_backend.py`（新）：`ClipBackend` Protocol + `OpenClipBackend`（`ViT-B-32`，回滚用）+ `ChineseClipBackend`（`cn_clip`，**lazy import 仅在 `_ensure_loaded` 方法体内**，模块顶层无 `import cn_clip`）+ `get_backend(settings)` 工厂（未知后端名抛 `RuntimeError`）。
- `app/clip_service.py`：单例由「持有模型」改为「兼容壳委托 backend」；**公开方法名与签名冻结**（`_initialize` / `get_image_feature` / `get_text_feature` / `get_color_histogram` / `compute_color_similarity` / `compute_weighted_similarity`）——`conftest.py` 靠 monkeypatch 这些名字阻断真实模型，**改名即测试全红**。
- `scripts/reembed_all_vectors.py`（新）：换模型后重算全库向量；`sqlite3` online backup 冷备 + `.reembed_state.json` 断点（带模型指纹，指纹不符拒绝续跑）。
- `scripts/calibrate_thresholds.py`（新）：标定/PR 曲线/Recall@K/权重网格；`--fake-encoder` 为**仅 CLI 的**冒烟开关（`encoder = _FakeEncoder() if args.fake_encoder else clip_service`），其输出为确定性噪声，**不得用于任何阈值决策**。
- `eval/eval_set_v3.5.0.json`（新）：**70 对（30 正 / 40 负）**，基于库里 6 条真实物品（id64/67/68/73/77/80）；P21–P30 含 img→text 8 对 + img→img 12 对，其中 P25–P30 标记 `degenerate_self:true`（同图自比 → sim_ii≡1.0），**N31–N40 为 10 对同类硬负样本**（`hard_negative:true`，复用既有正样本查询文本、只换目标）；`calibrate_thresholds.py` 标定时排除退化对 → **有效标定 24 正 / 40 负（n=64）**。**n 仍小样本，阈值不可称「已可靠标定」**。

## 文档现状

- `PROJECT.md` / `README.md` / `CHANGELOG.md` 已于 v3.3.3 与代码对齐；评审与同步记录在 `docs/`。
- 已知未修项：R4 颜色特征未持久化（每次匹配重复磁盘 IO，`items.py:507` / `match_service.py:59`）、R5 同步邮件阻塞事件循环、R6 路由顺序契约、R7 裸 `except: pass`、C1 公开接口不校验账号状态、C2 role 语义重载。
