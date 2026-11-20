"""Task 7：通用锁断言框架——锁从数据（ANCHORS 锚表）断言，不在测试里逐锁手写。

对 ANCHORS 里每把锁各跑正反两条参数化断言：
- pass：用条件满足构造器把 requires 全部满足 → 对应抉择 locked=False
- deny：用缺条件构造器把 requires 全部打破 → locked=True、missing 首条
  与 requires 首条同 type/key、denial 非空
- 锚覆盖：audit(world, registry, ANCHORS).errors == []（全量真数据）

新章包接入零测试代码：写章包 JSON + 在 lock_anchors.ANCHORS 补一条锚即自动展开。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from text_rpg.chapters import load_world
from text_rpg.contracts import evaluate
from text_rpg.engine import GameEngine
from text_rpg.lock_anchors import ANCHORS
from text_rpg.locks import audit, build_registry

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _real_engine() -> GameEngine:
    """真世界引擎：章包 JSON 走 load_world 真加载器，不手搓 stub。"""
    world = load_world(_DATA_DIR)
    return GameEngine(world, build_registry(world))


def _cond_type_key(cond: dict) -> tuple[str, str]:
    """条件 dict → (type, key)，与 contracts._eval_cond 的 missing 明细对齐。"""
    if "flag" in cond:
        return "flag", cond["flag"]
    if "attr" in cond:
        return "attr", cond["attr"]
    if "item" in cond:
        return "item", cond["item"]
    raise ValueError(f"未知条件形状：{cond!r}")


def _satisfy(requires: list[dict], state) -> None:
    """条件满足构造器：flag→加旗 / attr→置达标值 / item→塞背包。"""
    for cond in requires:
        ctype, key = _cond_type_key(cond)
        if ctype == "flag":
            state.flags.add(key)
        elif ctype == "attr":
            state.attributes[key] = cond["value"]
        else:
            state.backpack.append(key)


def _unsatisfy(requires: list[dict], state) -> None:
    """缺条件构造器：把每条 requires 强制打破（value-1 对 >= 与 == 都不达标）。"""
    for cond in requires:
        ctype, key = _cond_type_key(cond)
        if ctype == "flag":
            state.flags.discard(key)
        elif ctype == "attr":
            state.attributes[key] = cond["value"] - 1
        else:
            if key in state.backpack:
                state.backpack.remove(key)


def _lock_surface(engine: GameEngine, lock_id: str):
    """锁的断言面：抉择锁 → ("choice", scene_id, choice_id)；入口锁 → ("entry", chapter_id)。

    入口锁（chapter.entry_locks）没有任何抉择引用，走 chapters_view 断言
    （Task 8 起支持：ch02 entry_lock 首例）。
    两处皆无即锚表挂了假锁。
    """
    for chapter in engine.world.chapters:
        for scene in chapter.scenes:
            for choice in scene.choices:
                if choice.lock == lock_id:
                    return "choice", scene.id, choice.id
    for chapter in engine.world.chapters:
        if lock_id in chapter.entry_locks:
            return "entry", chapter.id
    raise AssertionError(f"锁「{lock_id}」无任何抉择/入口引用（锚表与章包失配）")


@pytest.mark.parametrize("lock_id", sorted(ANCHORS))
def test_lock_pass(lock_id):
    """锚 pass 侧：满足 requires → 抉择锁 choices_view locked=False / 入口锁章节 locked=False。"""
    engine = _real_engine()
    state = engine.new_game("锚测")
    lock = engine.registry[lock_id]
    _satisfy(lock.requires, state)
    surface = _lock_surface(engine, lock_id)
    if surface[0] == "choice":
        _, scene_id, choice_id = surface
        state.current_scene = scene_id
        view = {c["id"]: c for c in engine.choices_view(state)}
        assert view[choice_id]["locked"] is False
    else:
        _, chapter_id = surface
        row = next(r for r in engine.chapters_view(state) if r["id"] == chapter_id)
        assert row["locked"] is False


@pytest.mark.parametrize("lock_id", sorted(ANCHORS))
def test_lock_deny(lock_id):
    """锚 deny 侧：缺条件 → locked=True、missing 首条同 type/key、denial 非空。"""
    engine = _real_engine()
    state = engine.new_game("锚测")
    lock = engine.registry[lock_id]
    _unsatisfy(lock.requires, state)
    surface = _lock_surface(engine, lock_id)
    want_type, want_key = _cond_type_key(lock.requires[0])
    if surface[0] == "choice":
        _, scene_id, choice_id = surface
        state.current_scene = scene_id
        row = {c["id"]: c for c in engine.choices_view(state)}[choice_id]
        assert row["locked"] is True
        assert row["missing"][0]["type"] == want_type
        assert row["missing"][0]["key"] == want_key
        assert row["denial"]  # denial 非空
    else:
        _, chapter_id = surface
        row = next(r for r in engine.chapters_view(state) if r["id"] == chapter_id)
        assert row["locked"] is True
        result = evaluate(lock.requires, state)
        assert result.missing[0]["type"] == want_type
        assert result.missing[0]["key"] == want_key
        assert lock.denial  # denial 非空


def test_anchors_cover_registry():
    """全量真数据自审：每把注册锁都有 pass/deny 双侧锚，audit errors == []。"""
    world = load_world(_DATA_DIR)
    registry = build_registry(world)
    assert registry, "注册表为空——世界无锁可审，锚覆盖断言无对象"
    report = audit(world, registry, ANCHORS)
    assert report.errors == []
