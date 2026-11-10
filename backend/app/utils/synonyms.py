# backend/app/utils/synonyms.py
"""校园失物招领的**同义词/别名词典**（v3.7.0）。

解决什么问题
------------
``V2_TITLE_GATE="literal"`` 要求「字面命中 ≥ 0.8」才允许标题向量参与打分。
字面判断是**子串匹配**，于是同义表达会被判成 0：

    查询「校园卡」 × 标题「一卡通」    → 无字面重合 → 标题通道关闭 → 只剩全文向量
    查询「课本」   × 标题「高等数学教材」→ 同上

用户明明知道那东西叫什么，系统却不认 —— 这是门控的已知盲区（见
``eval/README.md`` §10 / PROJECT §9.2）。本词典把**同一实物的不同叫法**归为一组，
命中不同组员即视为同义命中，强度等同「标题包含」。

设计取舍
--------
1. **只收「同一实物的不同叫法」**，不收上下位关系。
   「耳机」与「蓝牙耳机」是包含关系，子串匹配已能处理，重复收录只会放大误报；
   而「学生证」与「学生卡」在多数学校是**两张不同的卡**，坚决不收。
2. **不改写文本，只做同组交叉判断**。
   若把「校园卡」全局替换成「一卡通」，那「校园卡套」会被改成「一卡通套」——
   卡套不是卡，错得更离谱。故本模块只提供 :func:`alias_hit`：
   查询里出现组员 A、目标里出现组员 B（A≠B）才算同义命中。
3. **每个词 ≥ 2 字**。单字（"伞"、"卡"）会把大量无关项卷进来。
4. **组内任意两词互不相含** —— 否则「A 包含 B」会被子串逻辑先命中，
   词典规则形同虚设，还会掩盖数据错误（导入时断言）。
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

#: 同义词组：组内任意两个词视为「同一实物的不同叫法」。
#: 新增词条前请先确认：它们指向的是**同一件东西**，还是只是相关？
SYNONYM_GROUPS: Tuple[Tuple[str, ...], ...] = (
    # 校园里同一张卡：充值、吃饭、开门常常是同一张
    ("校园卡", "一卡通", "饭卡"),
    # 门禁卡（与"校园卡"分开：不少学校确实是两张）
    ("门禁卡", "门卡", "出入卡"),
    ("充电宝", "移动电源"),
    ("数据线", "充电线"),
    ("耳机盒", "充电盒", "耳机仓"),
    # 教材 = 课本 = 教科书（查询常写"课本"，标题常写"教材"）
    ("教材", "课本", "教科书"),
    ("双肩包", "书包", "背包"),
    ("钱包", "钱夹", "皮夹"),
    ("雨伞", "折叠伞", "遮阳伞", "太阳伞"),
    ("伞套", "伞袋"),
    ("U盘", "优盘", "闪存盘"),
    ("保温杯", "水杯", "茶杯"),
    ("笔记本", "记事本"),
)


def _validate(groups: Iterable[Tuple[str, ...]]) -> None:
    """导入即校验：单字、跨组重复、组内包含 —— 三者都会让词典静默失效。"""
    seen: Dict[str, int] = {}
    for gi, group in enumerate(groups):
        if len(group) < 2:
            raise ValueError(f"同义词组至少需要 2 个词: {group}")
        for t in group:
            if len(t) < 2:
                raise ValueError(f"同义词不得是单字（会把无关项卷进来）: {t!r}")
            if t in seen and seen[t] != gi:
                raise ValueError(f"词条 {t!r} 同时出现在多个同义词组")
            seen[t] = gi
        for a in group:
            for b in group:
                if a != b and a in b:
                    raise ValueError(
                        f"同组内 {a!r} 是 {b!r} 的子串 —— 子串逻辑会先命中，词典规则失效"
                    )


_validate(SYNONYM_GROUPS)

#: 词 → 规范名（组内首词）
ALIAS_INDEX: Dict[str, str] = {t: g[0] for g in SYNONYM_GROUPS for t in g}

#: 规范名 → 同组全部词
GROUP_MEMBERS: Dict[str, Tuple[str, ...]] = {g[0]: tuple(g) for g in SYNONYM_GROUPS}


def canonical(term: str) -> str:
    """把一个词映射到所属组的规范名；不在词典中则原样返回。"""
    return ALIAS_INDEX.get(term, term)


def alias_hit(query: str, target: str) -> bool:
    """查询与目标是否通过**同义组**构成命中（要求组员不同）。

    Args:
        query: 已归一化的查询文本（也允许是一整句，如"我的校园卡丢了"）。
        target: 已归一化的标题或描述。

    Returns:
        True 表示「查询里出现了某组员，且目标里出现了同组的另一个组员」。
        同组同一个词不算 —— 那是子串/完全匹配该处理的事。
    """
    hit, _ = hit_detail(query, target)
    return hit


def hit_detail(query: str, target: str) -> Tuple[bool, str]:
    """调试/可解释性用：返回 ``(是否命中, 触发命中的词对说明)``。"""
    if not query or not target:
        return False, ""
    for group in SYNONYM_GROUPS:
        for term in group:
            if term not in query or term in target:
                continue
            for other in group:
                if other != term and other in target:
                    return True, f"{term} ≡ {other}"
    return False, ""


def all_terms() -> List[str]:
    """全部词条（文档/测试用）。"""
    return sorted(ALIAS_INDEX)
