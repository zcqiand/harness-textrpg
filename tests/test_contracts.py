"""Task 2：contracts.py 锁条件三类求值 + 效果四类执行（TDD 先红后绿）。"""

from types import SimpleNamespace

import pytest
from text_rpg.contracts import apply, evaluate


def make_state(flags=None, backpack=None, attributes=None):
    """轻量 GameState 占位：字段名与核心签名一致。"""
    return SimpleNamespace(
        flags=set(flags or []),
        backpack=list(backpack or []),
        attributes=dict(attributes or {}),
    )


def test_flag_condition_true_and_missing():
    st = make_state(flags={"helped_woodcutter"})
    r = evaluate([{"flag": "helped_woodcutter"}], st)
    assert r.satisfied and r.missing == []
    r2 = evaluate([{"flag": "nope"}], st)
    assert not r2.satisfied
    assert r2.missing == [{"type": "flag", "key": "nope", "have": False, "need": True}]


def test_attr_threshold_and_missing_detail():
    st = make_state(attributes={"insight": 1})
    r = evaluate([{"attr": "insight", "op": ">=", "value": 3}], st)
    assert not r.satisfied
    assert r.missing == [{"type": "attr", "key": "insight", "have": 1, "need": 3}]


def test_item_and_multi_condition_and_semantics():
    st = make_state(backpack=["dry_rations"])
    r = evaluate([{"item": "dry_rations"}, {"item": "fan"}], st)
    assert not r.satisfied and r.missing[0]["type"] == "item"


def test_attr_condition_value_must_be_int():
    st = make_state(attributes={"insight": 1})
    for op in (">=", "=="):
        with pytest.raises(ValueError):
            evaluate([{"attr": "insight", "op": op, "value": "3"}], st)
        with pytest.raises(ValueError):
            evaluate([{"attr": "insight", "op": op, "value": None}], st)
    with pytest.raises(ValueError):
        evaluate([{"attr": "insight", "op": "==", "value": True}], st)


def test_effects_order_and_negative_delta():
    st = make_state(attributes={"insight": 3}, backpack=["dry_rations"])
    msgs = apply(
        [
            {"attr": {"insight": -1}},
            {"item_remove": "dry_rations"},
            {"flag": "done"},
            {"item_add": "fan"},
        ],
        st,
    )
    assert st.attributes["insight"] == 2 and st.backpack == ["fan"] and "done" in st.flags
    assert len(msgs) == 4
