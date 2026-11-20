"""Task 4：locks.py 注册表并集 + 启动自审三查（TDD 先红后绿）。

三失败方向：悬空 choice.lock / 空 denial / 缺锚；
一绿向：干净世界 errors == []。
"""

from text_rpg.chapters import Chapter, Choice, LockDef, Scene, World
from text_rpg.lock_anchors import ANCHORS
from text_rpg.locks import AuditReport, audit, build_registry


def _world_with(chapter_dict: dict) -> World:
    """测试工厂：单章 World，按章回包 dict 形状构造（不落盘）。"""
    locks = [
        LockDef(
            id=lk["id"],
            requires=list(lk.get("requires", [])),
            denial=lk.get("denial", "默认拒绝文案"),
            effects=list(lk.get("effects", [])),
            chapter_id=chapter_dict["id"],
        )
        for lk in chapter_dict.get("locks", [])
    ]
    scenes = [
        Scene(
            id=sc["id"],
            text=sc.get("text", ""),
            choices=[
                Choice(
                    id=c["id"],
                    text=c.get("text", ""),
                    lock=c.get("lock"),
                    goto=c.get("goto"),
                    effects=list(c.get("effects", [])),
                )
                for c in sc.get("choices", [])
            ],
        )
        for sc in chapter_dict.get("scenes", [])
    ]
    chapter = Chapter(
        id=chapter_dict["id"],
        title=chapter_dict.get("title", ""),
        entry_locks=list(chapter_dict.get("entry_locks", [])),
        locks=locks,
        scenes=scenes,
    )
    return World(chapters=[chapter], start_attributes={"insight": 1}, start_backpack=[])


def _full_anchors(world: World) -> dict:
    """按 registry 全覆盖构造合法锚表（pass/deny 双键）。"""
    reg = build_registry(world)
    return {k: {"pass": f"t::{k}::pass", "deny": f"t::{k}::deny"} for k in reg}


def test_audit_clean_world_has_no_errors():
    world = _world_with(
        {
            "id": "ch01",
            "locks": [
                {
                    "id": "gate1",
                    "requires": [{"type": "attr", "name": "insight", "op": ">=", "value": 2}],
                    "denial": "悟性不足，不得入内",
                }
            ],
            "scenes": [{"id": "s1", "choices": [{"id": "c1", "text": "叩门", "lock": "gate1"}]}],
        }
    )
    report = audit(world, build_registry(world), _full_anchors(world))
    assert isinstance(report, AuditReport)
    assert report.errors == [] and report.warnings == []


def test_audit_dangling_choice_lock_reference_is_error():
    world = _world_with(
        {
            "id": "ch01",
            "locks": [],
            "scenes": [
                {"id": "s1", "choices": [{"id": "c1", "text": "推门", "lock": "ghost_lock"}]}
            ],
        }
    )
    report = audit(world, build_registry(world), {})
    assert any("ghost_lock" in msg and "悬空" in msg for msg in report.errors)


def test_audit_empty_denial_is_error():
    world = _world_with(
        {
            "id": "ch01",
            "locks": [{"id": "gate1", "requires": [], "denial": "   "}],
            "scenes": [{"id": "s1", "choices": []}],
        }
    )
    report = audit(world, build_registry(world), _full_anchors(world))
    assert any("gate1" in msg for msg in report.errors)


def test_audit_missing_anchor_is_error():
    world = _world_with(
        {
            "id": "ch01",
            "locks": [{"id": "gate1", "requires": [], "denial": "拒之门外"}],
            "scenes": [{"id": "s1", "choices": []}],
        }
    )
    # 锚表缺 gate1 条目 → 报缺锚
    report = audit(world, build_registry(world), {})
    assert any("gate1" in msg and ("锚" in msg or "anchor" in msg) for msg in report.errors)
    # 补齐后即消
    ok = audit(world, build_registry(world), _full_anchors(world))
    assert ok.errors == []


def test_registry_is_union_of_chapter_locks():
    ch1 = _world_with(
        {
            "id": "ch01",
            "locks": [{"id": "gate1", "requires": [], "denial": "一"}],
        }
    )
    ch2 = _world_with(
        {
            "id": "ch02",
            "locks": [
                {"id": "gate2", "requires": [], "denial": "二"},
                {"id": "gate1", "requires": [], "denial": "重名同 id"},
            ],
        }
    )
    world = World(
        chapters=ch1.chapters + ch2.chapters,
        start_attributes={"insight": 1},
        start_backpack=[],
    )
    registry = build_registry(world)
    assert set(registry) == {"gate1", "gate2"}
    assert registry["gate1"].chapter_id == "ch01"  # 首章先登记
    assert registry["gate2"].chapter_id == "ch02"


def test_anchors_skeleton_is_empty_dict():
    # 骨架契约：本任务只交付空表，逐章条目 Task 7 起补
    assert ANCHORS == {}
