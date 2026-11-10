# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, Set


class Settings(BaseSettings):
    APP_NAME: str = "校园失物检索平台"
    APP_VERSION: str = "3.7.0"
    API_V1_STR: str = "/api"

    # 安全配置
    SECRET_KEY: str
    # ---- 会话（v3.6.1）----
    # 滑动会话：令牌有效期 ACCESS_TOKEN_MINUTES，剩余不足 RENEW_MINUTES 时由后端
    # 静默下发新令牌。效果 =「离开超过 ACCESS_TOKEN_MINUTES 才需要重新登录」。
    ACCESS_TOKEN_MINUTES: int = 30
    # None → 派生为「有效期 - 1 分钟」，即每次鉴权请求都把令牌续到满期，
    # 保证离开后正好撑满 ACCESS_TOKEN_MINUTES 才失效；显式配置可降低下发频率。
    ACCESS_TOKEN_RENEW_MINUTES: Optional[int] = None

    # 数据库
    DATABASE: str = "lost_found.db"

    # 上传配置
    UPLOAD_FOLDER: str = "uploads"
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024
    ALLOWED_EXTENSIONS: Set[str] = {"png", "jpg", "jpeg", "gif", "webp"}

    # 日志
    LOG_LEVEL: str = "INFO"

    # ===================================================================== #
    # v3.5.0 新增：模型后端（D1）
    # ===================================================================== #
    CLIP_BACKEND: str = "cn_clip"           # "cn_clip" | "open_clip"；未知值 → RuntimeError
    CLIP_DEVICE: str = "auto"               # "auto" | "cpu" | "cuda"；auto=有 CUDA 用 cuda 否则 cpu
    #   Chinese-CLIP（默认）
    CLIP_CN_MODEL_NAME: str = "ViT-H-14"    # OFA-Sys 模型名
    CLIP_CN_EMBED_DIM: int = 1024           # 联合投影维度（= 两个 encode_* 的输出维度）；
                                            # ViT-H-14 配置 embed_dim=1024、vision_width=1280，
                                            # 二者不等 → embed_dim 是**联合投影维度**而非视觉宽度。
    CLIP_CN_CONTEXT_LENGTH: int = 52        # 文本塔上下文长度；实际可用内容 token = 50（52 - [CLS] - [SEP]）
    CLIP_CN_DOWNLOAD_ROOT: str = "models"   # 权重下载/缓存目录（.gitignore，不入库）
    CLIP_CN_USE_MODELSCOPE: bool = True     # True 走 ModelScope（国内直连，需 pip install modelscope）；False 走 HF Hub
    CLIP_CN_CKPT_PATH: str = ""             # 非空则直接加载本地 .pt（运行期零网络，优先级最高）
    # ---- v3.6.3：启动预热 ----
    # 为 True 时，应用启动后在**后台线程**加载模型（8~18s，CPU/3.6GB 权重），
    # 使「启动后第一个请求」不再承担冷启动开销（原先会撞前端 10s 超时）。
    # 端口监听不阻塞：预热期间进来的请求会等锁，预热完成后立即返回。
    # 置 False 可恢复 v3.6.2 的纯懒加载行为（测试/极简环境）。
    CLIP_WARMUP_ENABLED: bool = True
    #   open_clip（回滚用，默认值与现网一致）
    CLIP_OPEN_MODEL_NAME: str = "ViT-B-32"
    CLIP_OPEN_PRETRAINED: str = "laion2b_s34b_b79k"
    CLIP_OPEN_EMBED_DIM: int = 512          # ViT-B-32 输出维度（回滚路径，与 v3.4.1 一致）

    # ===================================================================== #
    # 打分权重 —— **按查询形态分三种检索模式**（2026-09-21 修订）
    #
    #   ① 文字检索（查询只有文字）→ 可用通道 = 文-文(主) + 文→图(辅)
    #   ② 图片检索（查询只有图片）→ 可用通道 = 图-图(主) + 图→文(辅)
    #   ③ 图文混合检索           → 可用通道 = 图-图 + 文-文 + 跨模态(双向)
    #
    #   实现要点：**同模态通道为「主证据」、跨模态为「辅助证据」**；
    #   三种模式由「缺通道动态归一化」自动适配 —— 无需任何分支代码。
    #   例：文字检索时只剩 文-文 与 跨模态 → 归一化后自然成为 0.75 / 0.25。
    # ===================================================================== #
    MATCH_W_TEXT_TEXT: float = 0.75         # 主证据：文-文（同模态，判别力强）
    MATCH_W_IMG_IMG: float = 0.75           # 主证据：图-图（同模态，判别力强）
    MATCH_W_CROSS: float = 0.25             # 辅助：跨模态（保留「仅有图片/仅有描述」的召回能力）
    MATCH_W_CROSS_T2I: float = 0.5          # 跨模态内：查询文字 × 目标图片
    MATCH_W_CROSS_I2T: float = 0.5          # 跨模态内：查询图片 × 目标文字

    # ===================================================================== #
    # 跨模态通道「尺度映射」（2026-09-21）—— 实测标定值
    #   跨模态余弦天生只落在 0.15~0.35（CLIP 图文对齐的固有特性），
    #   即使完美命中也只有 ~0.27。若不映射，它在任何加权里都被系统性低估。
    #   映射：ref = clip((x - LO) / (HI - LO), 0, 1)
    #   LO/HI 取自评测集实测：负样本均值 → 0、正样本均值 → 1。
    #   注意：**仅用于外层加权与对外展示**；阶段5 惩罚仍用原始余弦（其阈值按原始尺度设计）。
    # ===================================================================== #
    MATCH_CROSS_REF_LO: float = 0.194
    MATCH_CROSS_REF_HI: float = 0.298

    # ===================================================================== #
    # 证据链判定阈值（2026-09-21，评测集实测初值）
    #   用于把「分数」翻译成用户能懂的结论：确定为同一物品 / 高度疑似 / 相关 / 参考
    # ===================================================================== #
    MATCH_EVIDENCE_CONFIRM_SELF: float = 0.95   # 同模态（图-图 或 文-文）≥ 此值 → 确定为同一物品
    MATCH_EVIDENCE_TEXT_MIN: float = 0.606      # 文-文 ≥ 此值 → 高度疑似（实测：召回 100% / 误报 33%）
    MATCH_EVIDENCE_IMG_MIN: float = 0.606       # 图-图 ≥ 此值 → 计入「高度疑似」命中依据（同模态余弦与文-文同尺度；初值与 TEXT_MIN 对齐，待图像通道标定后复核）
    MATCH_EVIDENCE_CROSS_MIN: float = 0.513     # 跨模态（映射后）≥ 此值 → 高度疑似（对应原始余弦 0.247）
    MATCH_EVIDENCE_CROSS_WEAK: float = 0.15     # 跨模态（映射后）≥ 此值 → 相关（仅召回）

    # ===================================================================== #
    # v3.5.0 新增：阶段1 类别/位置（沿用现值，外露以便调参）
    # ===================================================================== #
    MATCH_CAT_SAME_BONUS: float = 0.05
    MATCH_CAT_DIFF_PENALTY: float = 0.08
    MATCH_LOC_SAME_BONUS: float = 0.03
    MATCH_LOC_DIFF_PENALTY: float = 0.04

    # 阶段2 时间衰减（2026-09-21 调参：原 90 天 / 下限 0.2 过激——
    # 老物品分数被打到地板上，配合 0.35 手动阈值会让结果集体消失）
    MATCH_DECAY_DAYS: int = 240
    MATCH_DECAY_FLOOR: float = 0.6

    # ===================================================================== #
    # v3.5.0 新增：阶段5 跨模态一致性惩罚（D3）——「初值，需评测收敛」
    # ===================================================================== #
    CROSS_PENALTY_ENABLED: bool = True      # 总开关；若致 Recall@3 下降则关闭
    CROSS_PENALTY_SELF_HIGH: float = 0.55   # 触发前提：同模态自相似 ≥ 此值
    CROSS_PENALTY_CC_LOW: float = 0.10      # cc ≤ 此值 → 触底惩罚
    CROSS_PENALTY_CC_HIGH: float = 0.30     # cc ≥ 此值 → 不惩罚
    CROSS_PENALTY_FLOOR: float = 0.50       # 惩罚下限（腰斩上限，≤×0.5）

    # ===================================================================== #
    # 匹配阈值（D6）——「初值，需评测收敛」
    # ===================================================================== #
    MATCH_THRESHOLD_MANUAL: float = 0.624956  # 手动匹配：Recall ≥ 0.90 最高分位（2026-09-21 标定）
    MATCH_THRESHOLD_AUTO: float = 0.733952    # 自动匹配：Precision ≥ 0.90 最低分位（实测 P=91.7% / R=61.1%）
    MATCH_THRESHOLD_EMAIL: float = 0.832069   # 邮件通知：Precision ≥ 0.98 最低分位（实测 P=100% / R=19.4%，样本少需灰度）
    MAX_AUTO_MATCH_NOTIFICATIONS: int = 3

    # ===================================================================== #
    # v3.5.0 新增：自动推送总开关（Q2/D9，灰度期置 false）
    # ===================================================================== #
    AUTO_MATCH_ENABLED: bool = True

    # ===================================================================== #
    # v3.5.0 新增：前端图例（D4，随 /match 响应 legend 下发）
    #   None → 由 MATCH_THRESHOLD_AUTO / MATCH_THRESHOLD_MANUAL 派生（消除两套魔数）
    # ===================================================================== #
    MATCH_LEGEND_HIGH: Optional[float] = None   # None → 派生为 MATCH_THRESHOLD_AUTO
    MATCH_LEGEND_MID: Optional[float] = None    # None → 派生为 MATCH_THRESHOLD_MANUAL

    # ===================================================================== #
    # v3.7.0 打分口径 v2：单分数融合（P1）
    # ===================================================================== #
    # 设计动机（2026-11-09 实测）：
    #   旧口径在**纯文字查询**下，跨模态通道的原始余弦恒为 0.107~0.191，
    #   经 [0.194, 0.298] 线性映射后**一律为 0**，于是
    #       content_score = 0.75×tt + 0.25×0 = 0.75×tt
    #   等效门槛被抬到 tt ≥ 0.8333，正解（房卡 0.7569）被挡、错解（眼镜 0.8599）漏过。
    #
    # v2 相对 v1 的四处改动：
    #   1. **去掉跨模态的 clip 截断**，直接把原始余弦送入加权 —— 截断会把
    #      「低于负样本均值」的信息整段抹成 0，这是通道失效的元凶；
    #   2. **标题独立向量**优先于全文向量（max 聚合）：全文向量会把
    #      「房卡 + 丢失一个宿舍钥匙」编码成一个嵌合体，标题才是「是什么」；
    #      但仅在字面命中时启用（见 V2_TITLE_GATE）—— 短标题余弦不可信；
    #   3. **字面命中**作为独立加分项（短文本各向异性下，字面是最强确定性证据）；
    #   4. **单一分数**：判定、排序、展示同源；时间只影响排序，不影响判定。
    # 置 "legacy" 可整口径回滚（消融对比 / 线上回退）。
    MATCH_SCORING_MODE: str = "v2"          # "v2" | "legacy"

    V2_W_TEXT: float = 0.80                 # 文本通道（标题/全文取更优者）
    V2_W_IMG: float = 0.80                  # 图像通道（图-图）
    V2_W_CROSS: float = 0.20                # 跨模态通道（原始余弦，不截断）

    # 字面命中：短文本下 CLIP 余弦区分度低（「学生证」对「笔记本」竟有 0.84），
    # 字面是唯一确定性证据。取值由 _literal_hit 给出 0~1，再乘该系数加分。
    V2_LITERAL_BONUS: float = 0.15

    # 标题通道的**信任门槛**："literal" | "always"
    # WHY（2026-11-09 真实库实测）：标题向量把「房卡」从全文 0.7569 抬到 1.0000，
    # 但同一通道也把「一个手机」对查询「房卡」的余弦抬到 0.7783（其全文仅 0.4571），
    # 直接越过手动阈值 → 搜「房卡」会带出「一个手机」。
    # 根因是短标题的余弦各向异性（两字词普遍 0.75~0.85），此时**唯一可信的是字面**。
    # "literal"：仅当字面命中（≥0.8，即标题含查询或反向包含）时才让标题通道生效，
    # 否则退回全文向量 —— 标题是「同义词」时帮不上忙，但至少不再制造虚高。
    #
    # 定标依据（2026-11-09，真实库 7 条 approved 条目、42 对非字面配对）：
    #   scripts/eval_literal_pairs.py
    #     常开     FP@手动阈值 26/42 = 61.9%（眼镜→一个手机 0.8500、房卡→学生证 0.8059）
    #     字面门控  FP@手动阈值  8/42 = 19.0%
    # 评测集（literal-free）上代价仅 P@手动 0.8250→0.8049（1 个样本），
    # 因为它刻意排除了字面查询 —— 正是门控要保护的那一类，故不以其为准。
    V2_TITLE_GATE: str = "literal"

    # 同义词/别名词典开关（app/utils/synonyms.py）。
    # WHY：门控要求字面命中，而「校园卡 × 一卡通」「课本 × 教材」是同一东西的不同叫法，
    # 子串匹配不到 → 标题通道被误关。词典命中记为 literal=0.8（等同"标题包含"），
    # 因而同样能放行标题向量。置 false 可做消融对比。
    V2_SYNONYM_ENABLED: bool = True

    # v2 业务阈值（内容尺度，已扣除时间影响）。
    # 标定：scripts/calibrate_v2.py，评测集 eval/eval_set_v3.5.0.json（有效 n=78）
    #   口径 = v2 + V2_TITLE_GATE="literal"
    #   manual = Recall≥0.90 的最高门槛 → 0.6763（该点 P=0.8049）
    #   auto   = Precision≥0.90 的最低门槛 → 0.7685（该点 R=0.5833）
    #   email  = 本样本下无 P≥0.98 解，取 auto + 0.05 的保守值，需随数据复标
    # 报告：docs/review/scoring-v2-ablation.md
    V2_THRESHOLD_MANUAL: float = 0.6763
    V2_THRESHOLD_AUTO: float = 0.7685
    V2_THRESHOLD_EMAIL: float = 0.8500
    V2_TIME_DECAY_DAYS: int = 240           # 仅作用于 ranking_score
    V2_TIME_DECAY_FLOOR: float = 0.60

    # 前端基础URL（用于邮件链接）
    BASE_URL: str = "http://localhost:5173"

    # 邮件配置
    MAIL_SERVER: str = "smtp.qq.com"
    MAIL_PORT: int = 465
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


#: 业务阈值种类 → 配置字段名。两套口径各自独立，避免「改了公式忘了改阈值」。
_V2_THRESHOLD_FIELDS = {
    "manual": "V2_THRESHOLD_MANUAL",
    "auto": "V2_THRESHOLD_AUTO",
    "email": "V2_THRESHOLD_EMAIL",
}
_LEGACY_THRESHOLD_FIELDS = {
    "manual": "MATCH_THRESHOLD_MANUAL",
    "auto": "MATCH_THRESHOLD_AUTO",
    "email": "MATCH_THRESHOLD_EMAIL",
}


def match_threshold(kind: str = "manual") -> float:
    """按**当前打分口径**返回业务阈值（单一数据源）。

    WHY：阈值与打分公式必须同代。旧代码里阈值直接读 ``settings.MATCH_THRESHOLD_*``，
    一旦切到 v2 而阈值仍是 v1 标定值，就会出现「公式换了、门槛没换」的静默错配
    —— 这正是 v3.6.x 之前「改了权重却忘了重标」的同类问题。

    Args:
        kind: ``"manual"``（手动检索）| ``"auto"``（自动推送）| ``"email"``（邮件）。

    Raises:
        KeyError: ``kind`` 非法（显式失败，避免静默回落成 0 而放行全部结果）。
    """
    if kind not in _LEGACY_THRESHOLD_FIELDS:
        raise KeyError(f"未知阈值类型: {kind!r}（可选 manual/auto/email）")
    mode = str(getattr(settings, "MATCH_SCORING_MODE", "legacy")).strip().lower()
    fields = _V2_THRESHOLD_FIELDS if mode == "v2" else _LEGACY_THRESHOLD_FIELDS
    return float(getattr(settings, fields[kind]))
