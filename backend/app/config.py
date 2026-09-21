# app/config.py
from pydantic_settings import BaseSettings
from typing import Optional, Set


class Settings(BaseSettings):
    APP_NAME: str = "校园失物检索平台"
    APP_VERSION: str = "3.5.0"
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
    # 打分权重 —— **三通道等权**（2026-09-16 修订，取代 v3.5.0 四通道）
    #   - 通道① 文-文      （查询文字 · 目标文字）
    #   - 通道② 图文跨模态  （双向合并：q文·t图 与 q图·t文 各半）
    #   - 通道③ 图-图      （查询图片 · 目标图片）
    #   - 三通道**各自独立、等权**（权重均为 1，互不牵制）；缺通道按可用集合
    #     动态归一化 —— 等权时等价于「可用通道的算术平均」。
    #   - 颜色通道**已废弃**（权重恒 0，不参与打分；键位保留仅为兼容旧配置）。
    # ===================================================================== #
    MATCH_W_TEXT_TEXT: float = 1.0          # 通道① 文-文
    MATCH_W_CROSS: float = 1.0              # 通道② 图文跨模态（双向合并）
    MATCH_W_IMG_IMG: float = 1.0            # 通道③ 图-图
    MATCH_W_COLOR: float = 0.0              # 【已废弃】恒 0：颜色不参与打分
    MATCH_W_CROSS_T2I: float = 0.5          # 通道② 内：查询文字 × 目标图片
    MATCH_W_CROSS_I2T: float = 0.5          # 通道② 内：查询图片 × 目标文字

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
    MATCH_THRESHOLD_MANUAL: float = 0.35    # 手动匹配：宽松（原 0.20）
    MATCH_THRESHOLD_AUTO: float = 0.55      # 自动匹配通知：严格（原 0.65）
    MATCH_THRESHOLD_EMAIL: float = 0.70     # 邮件通知：最严格（原 0.75）
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
