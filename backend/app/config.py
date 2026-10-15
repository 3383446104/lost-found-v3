# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, Set


class Settings(BaseSettings):
    APP_NAME: str = "校园失物检索平台"
    APP_VERSION: str = "3.6.0"
    API_V1_STR: str = "/api"

    # 安全配置
    SECRET_KEY: str
    JWT_EXPIRATION: int = 7

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
