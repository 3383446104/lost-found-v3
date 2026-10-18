# app/utils/privacy.py
"""隐私脱敏工具。

集中放置「对外可见但需打码」的字段处理，避免各 API 各写一份口径不一致。
"""
from typing import Optional


def mask_phone(phone: Optional[str]) -> Optional[str]:
    """手机号脱敏：中间四位打码（138****1234）；过短则整体打码。"""
    if not phone:
        return None
    phone = phone.strip()
    if len(phone) >= 7:
        return f"{phone[:3]}****{phone[-4:]}"
    return "****"
