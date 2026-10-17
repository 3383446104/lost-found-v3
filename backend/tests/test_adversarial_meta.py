"""对抗性验证 C：依赖声明一致性 + 统计口径残留扫描。

这些是「防回归」的静态守护：确保修复不被其它位置的旧写法重新引入。
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND_DIR / "app"
REQUIREMENTS = BACKEND_DIR / "requirements.txt"


def test_requirements_bcrypt_version_matches_installed():
    """requirements.txt 必须直接声明 bcrypt==<version>，且与实际安装版本一致。"""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    match = re.search(r"^bcrypt==(\S+)\s*$", text, re.MULTILINE)
    assert match, "requirements.txt 未直接声明 bcrypt==<version>（R3 未修复）"

    pinned = match.group(1)
    import bcrypt

    assert pinned == bcrypt.__version__, (
        f"requirements.txt 声明 bcrypt=={pinned}，实际安装 {bcrypt.__version__}"
    )


def test_no_local_date_prefix_today_filter_remains():
    """全仓扫描 app/：确认不存在「本地日期字符串前缀 + LIKE」的今日统计口径残留。"""
    offenders = []
    for py in APP_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "created_at LIKE" in text:
            offenders.append(f"{py.name}: 仍存在 'created_at LIKE'")
        if re.search(r"datetime\.now\(\)\s*\.strftime\(\s*['\"]%Y-%m-%d", text):
            offenders.append(f"{py.name}: 仍存在 datetime.now().strftime('%Y-%m-%d')（本地日期前缀）")
    assert not offenders, f"仍存在本地日期前缀统计口径: {offenders}"
