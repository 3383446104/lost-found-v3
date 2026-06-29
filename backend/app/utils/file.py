import os
import imghdr  # 或使用 python-magic
from ..config import settings

def allowed_file(filename: str, file_content: bytes = None) -> bool:
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext not in settings.ALLOWED_EXTENSIONS:
        return False
    # 如果提供了内容，验证文件头（仅图片示例）
    if file_content:
        # 使用 imghdr 检测图片类型
        detected_type = imghdr.what(None, h=file_content)
        if detected_type not in settings.ALLOWED_EXTENSIONS:
            return False
    return True