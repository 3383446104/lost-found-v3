# app/models/match.py
from pydantic import BaseModel, field_validator
from typing import Optional, List


class MatchRequest(BaseModel):
    """智能匹配请求参数。

    - ``image_path``：临时上传图片文件名/path（可选）；与 ``text`` 至少一项。
      （v3.6.0 起推荐改用 ``image_paths`` 多图，本字段保留兼容。）
    - ``image_paths``：多图查询（可选，最多 3 张，v3.6.0）。服务端对多张图的
      特征向量做「L2 归一化 → 均值 → 再归一化」聚合为单一查询向量，
      不改变三检索模式/打分口径/阈值尺度（查询侧向量层面的聚合）。
    - ``text``：自然语言描述（可选）。Chinese-CLIP 文本塔实际可用 **≤50 汉字**
      （context_length=52，含 [CLS]/[SEP]）；超长静默截断，建议关键特征前置。
    - ``target_type``：匹配目标类型，``lost`` 或 ``found``（默认 ``found``）。
    - ``threshold``：相似度阈值；``None`` → 回落 ``settings.MATCH_THRESHOLD_MANUAL``。
    - ``category`` / ``location``：可选的类别/位置增强信号（阶段1）。
    """

    image_path: Optional[str] = None
    image_paths: Optional[List[str]] = None   # 多图（最多 3 张），与 image_path 至少提供其一
    text: Optional[str] = None
    target_type: str = "found"          # 匹配目标类型：lost 或 found
    threshold: Optional[float] = None   # 相似度阈值；None → MATCH_THRESHOLD_MANUAL
    category: Optional[str] = None      # 查询物品类别（用于类别增强匹配）
    location: Optional[str] = None      # 查询物品位置（用于位置增强匹配）

    @field_validator("image_paths")
    @classmethod
    def _limit_image_paths(cls, v):
        if v is not None and len(v) > 3:
            raise ValueError("image_paths 最多 3 张图片")
        return v
