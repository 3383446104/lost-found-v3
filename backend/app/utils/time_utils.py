import datetime
import pytz
import logging
logger = logging.getLogger(__name__)

def format_beijing_time(time_str: str) -> str:
    if not time_str:
        return None
    try:
        # 尝试解析常见格式（含微秒）
        if '.' in time_str:
            dt = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S.%f')
        else:
            dt = datetime.datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError as e:
        logger.warning(f"时间解析失败: {time_str}, 错误: {e}")
        return None
    dt_utc = pytz.utc.localize(dt)
    dt_beijing = dt_utc.astimezone(pytz.timezone('Asia/Shanghai'))
    return dt_beijing.strftime('%Y-%m-%d %H:%M:%S')