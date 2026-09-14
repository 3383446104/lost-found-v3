# app/models/match.py
from pydantic import BaseModel
from typing import Optional


class MatchRequest(BaseModel):
    """智能匹配请求参数（v3.5.0 起**不扩展字段**，仅明确语义以保持契约稳定）。

    - ``image_path``：临时上传图片文件名/path（可选）；与 ``text`` 至少一项。
    - ``text``：自然语言描述（可选）。Chinese-CLIP 文本塔实际可用 **≤50 汉字**
      （context_length=52，含 [CLS]/[SEP]）；超长静默截断，建议关键特征前置。
    - ``target_type``：匹配目标类型，``lost`` 或 ``found``（默认 ``found``）。
    - ``threshold``：相似度阈值；``None`` → 回落 ``settings.MATCH_THRESHOLD_MANUAL``（默认 0.35）。
    - ``category`` / ``location``：可选的类别/位置增强信号（阶段1）。
    """

    image_path: Optional[str] = None
    text: Optional[str] = None
    target_type: str = "found"          # 匹配目标类型：lost 或 found
    threshold: Optional[float] = None   # 相似度阈值；None → MATCH_THRESHOLD_MANUAL
    category: Optional[str] = None      # 查询物品类别（用于类别增强匹配）
    location: Optional[str] = None      # 查询物品位置（用于位置增强匹配）
