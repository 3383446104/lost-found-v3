import datetime
import pytz
import logging
logger = logging.getLogger(__name__)

def days_since_utc(time_value, *, now: datetime.datetime = None) -> int:
    """把数据库时间戳换算为「距今 UTC 天数」（时间衰减用）。

    为什么单独抽成公共函数（2026-09-21 修复）
    ------------------------------------------
    SQLite 的 ``CURRENT_TIMESTAMP`` 存 UTC 但**不带时区标记**，形如
    ``2026-07-02 01:06:44``。``datetime.fromisoformat`` 能解析它，返回的却是
    **naive** datetime；naive 与 ``datetime.now(timezone.utc)``（aware）相减会抛
    ``TypeError: can't subtract offset-naive and offset-aware datetimes``。

    此前两处调用点（``api/items.py``、``services/match_service.py``）各自用
    ``try/except Exception`` 兜底 → 异常被吞 → ``days_old`` 恒为 0 →
    **时间衰减完全失效且无任何日志**（老物品分数不降）。本函数统一处理：

    - ISO 8601（含 ``Z`` / ``+08:00`` 偏移）；
    - SQLite 空格格式（含可选微秒）；
    - naive → 显式补 UTC；aware → 归一化到 UTC；
    - 解析失败 → 返回 0（按不衰减处理）并记 warning，**绝不静默**。

    Args:
        time_value: 数据库时间戳（str / datetime / None）。
        now: 注入的当前时间（测试用），默认 ``datetime.now(timezone.utc)``。

    Returns:
        非负天数；无法解析时 0。
    """
    if time_value is None or time_value == "":
        return 0

    now = now or datetime.datetime.now(datetime.timezone.utc)
    ts = str(time_value).strip()
    dt = None

    # 1) ISO 8601（"2026-07-02T01:06:44Z" / 带偏移 / 也兼容空格分隔）
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        dt = None

    # 2) SQLite "YYYY-MM-DD HH:MM:SS[.ffffff]"
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.datetime.strptime(ts[:26], fmt)
                break
            except ValueError:
                continue

    if dt is None:
        logger.warning(f"时间戳解析失败，按「不衰减」处理: {time_value!r}")
        return 0

    # 关键修复：naive 时间戳按 UTC 解释（SQLite CURRENT_TIMESTAMP 即 UTC），
    # 否则与 aware 的 now 相减会抛 TypeError 并被兜底吞掉。
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)

    return max(0, (now - dt).days)


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