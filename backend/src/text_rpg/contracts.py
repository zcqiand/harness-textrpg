"""锁条件求值与效果执行契约。

条件三类：flag / attr / item；效果四类：attr / item_add / item_remove / flag。
条件列表全 AND 语义。形状不符 raise ValueError（可读中文信息）。
"""
# @impl M02.F02.I01

from __future__ import annotations

from dataclasses import dataclass, field

_ATTR_OPS = {
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
}


@dataclass
class EvalResult:
    satisfied: bool
    missing: list = field(default_factory=list)


def _flags(state):
    return getattr(state, "flags", set())


def _backpack(state):
    return getattr(state, "backpack", [])


def _attributes(state):
    return getattr(state, "attributes", {})


def _eval_cond(cond, state):
    """单条件求值：满足返回 None，不满足返回 missing 明细 dict。"""
    if not isinstance(cond, dict):
        raise ValueError(f"条件须为 dict，实得 {type(cond).__name__}：{cond!r}")
    keys = set(cond)
    if keys == {"flag"}:
        key = cond["flag"]
        if not isinstance(key, str):
            raise ValueError(f"flag 条件值须为字符串，实得 {type(key).__name__}")
        if key in _flags(state):
            return None
        return {"type": "flag", "key": key, "have": False, "need": True}
    if keys == {"attr", "op", "value"}:
        key = cond["attr"]
        op = cond["op"]
        value = cond["value"]
        if op not in _ATTR_OPS:
            raise ValueError(f"attr 条件算子只支持 >= 与 ==，实得 {op!r}")
        if not isinstance(key, str):
            raise ValueError(f"attr 条件键须为字符串，实得 {type(key).__name__}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"attr 条件 value 须为整数，实得 {type(value).__name__}")
        attrs = _attributes(state)
        have = attrs.get(key, 0)
        if _ATTR_OPS[op](have, value):
            return None
        return {"type": "attr", "key": key, "have": have, "need": value}
    if keys == {"item"}:
        key = cond["item"]
        if not isinstance(key, str):
            raise ValueError(f"item 条件值须为字符串，实得 {type(key).__name__}")
        if key in _backpack(state):
            return None
        return {"type": "item", "key": key, "have": False, "need": True}
    raise ValueError(f"条件形状不符，只支持 flag / attr(+op+value) / item：{sorted(cond)}")


def evaluate(conditions, state) -> EvalResult:
    """条件列表全 AND 求值。形状不符 raise ValueError。"""
    missing: list = []
    for cond in conditions:
        m = _eval_cond(cond, state)
        if m is not None:
            missing.append(m)
    return EvalResult(satisfied=not missing, missing=missing)


def _apply_one(eff, state) -> str:
    """单效果执行，返回人读消息。形状不符 raise ValueError。"""
    if not isinstance(eff, dict):
        raise ValueError(f"效果须为 dict，实得 {type(eff).__name__}：{eff!r}")
    keys = set(eff)
    if keys == {"attr"}:
        delta = eff["attr"]
        if not isinstance(delta, dict):
            raise ValueError(f"attr 效果值须为 dict，实得 {type(delta).__name__}")
        for key, d in delta.items():
            if not isinstance(d, (int, float)):
                raise ValueError(f"attr 效果增量须为数值：{key}={d!r}")
            _attributes(state)[key] = _attributes(state).get(key, 0) + d
        return f"属性变化：{delta}"
    if keys == {"item_add"}:
        key = eff["item_add"]
        if not isinstance(key, str):
            raise ValueError(f"item_add 效果值须为字符串，实得 {type(key).__name__}")
        _backpack(state).append(key)
        return f"获得物品：{key}"
    if keys == {"item_remove"}:
        key = eff["item_remove"]
        if not isinstance(key, str):
            raise ValueError(f"item_remove 效果值须为字符串，实得 {type(key).__name__}")
        bp = _backpack(state)
        if key not in bp:
            raise ValueError(f"背包中无此物品，无法移除：{key}")
        bp.remove(key)
        return f"失去物品：{key}"
    if keys == {"flag"}:
        key = eff["flag"]
        if not isinstance(key, str):
            raise ValueError(f"flag 效果值须为字符串，实得 {type(key).__name__}")
        _flags(state).add(key)
        return f"标记：{key}"
    raise ValueError(f"效果形状不符，只支持 attr / item_add / item_remove / flag：{sorted(eff)}")


def apply(effects, state) -> list[str]:
    """效果四类依序执行，返回人读消息列表。形状不符 raise ValueError。"""
    messages: list[str] = []
    for eff in effects:
        messages.append(_apply_one(eff, state))
    return messages
