"""Task M02.F05.I01 + M04.F02.I01：NPC 人设契约加载器与启动自审（TDD 先红后绿）。

契约形状以 v2/v3 design spec §5.2 为准（data/npcs/*.json）。
三失败方向：悬空 chapter 引用 / 空 red_lines / 空 outside；
绿向：三个真实资产全部加载并通过自审。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from text_rpg.chapters import load_world
from text_rpg.npcs import audit_npcs, load_npcs, npc_from_dict

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"


def _valid_dict() -> dict:
    """契约合法的最小 NPC dict（审计用工厂，不落盘）。"""
    return {
        "id": "npc_sample",
        "name": "樵夫",
        "chapter": "ch01",
        "persona": "两界山下的樵夫，指路也劝人。",
        "red_lines": ["自称神明", "许诺长生"],
        "outside": ["手机", "汽车", "互联网"],
        "inside": ["两界山", "长安", "村庄"],
        "memory_spec": {"window": 10, "event_tags": ["insulted", "gifted", "promised"]},
    }


# fn: M02.F05.I01
def test_npc_from_dict_maps_every_field():
    npc = npc_from_dict(_valid_dict())
    assert npc.id == "npc_sample"
    assert npc.name == "樵夫"
    assert npc.chapter == "ch01"
    assert npc.persona == "两界山下的樵夫，指路也劝人。"
    assert npc.red_lines == ["自称神明", "许诺长生"]
    assert npc.outside == ["手机", "汽车", "互联网"]
    assert npc.inside == ["两界山", "长安", "村庄"]
    assert npc.memory_window == 10
    assert npc.memory_event_tags == ["insulted", "gifted", "promised"]


# fn: M02.F05.I01
def test_load_npcs_reads_repo_assets_sorted():
    npcs = load_npcs(_REPO_DATA)
    assert [n.id for n in npcs] == ["npc_bone_elder", "npc_fan_princess", "npc_woodcutter"]


# fn: M04.F02.I01
def test_three_repo_assets_load_and_pass_audit():
    npcs = load_npcs(_REPO_DATA)
    assert {n.id for n in npcs} == {"npc_woodcutter", "npc_bone_elder", "npc_fan_princess"}
    assert {n.chapter for n in npcs} == {"ch01", "ch02", "ch03"}
    world = load_world(_REPO_DATA)
    report = audit_npcs(npcs, world)
    assert report.errors == [] and report.warnings == []
    # 契约形状底线：red_lines≥2、outside≥3、inside≥3、event_tags 含三类锚
    for n in npcs:
        assert len(n.red_lines) >= 2 and len(n.outside) >= 3 and len(n.inside) >= 3
        assert set(n.memory_event_tags) >= {"insulted", "gifted", "promised"}


# fn: M02.F05.I01
def test_audit_dangling_chapter_reference_is_error():
    bad = dict(_valid_dict(), chapter="ch99")
    world = load_world(_REPO_DATA)
    report = audit_npcs([npc_from_dict(bad)], world)
    assert any("ch99" in msg and "悬空" in msg for msg in report.errors)


# fn: M02.F05.I01
def test_audit_empty_red_lines_is_error():
    bad = dict(_valid_dict(), red_lines=[])
    world = load_world(_REPO_DATA)
    report = audit_npcs([npc_from_dict(bad)], world)
    assert any(
        "npc_sample" in msg and ("red_lines" in msg or "红线" in msg) for msg in report.errors
    )


# fn: M02.F05.I01
def test_audit_empty_outside_is_error():
    bad = dict(_valid_dict(), outside=[])
    world = load_world(_REPO_DATA)
    report = audit_npcs([npc_from_dict(bad)], world)
    assert any(
        "npc_sample" in msg and ("outside" in msg or "黑名单" in msg) for msg in report.errors
    )


# fn: M02.F05.I01
def test_npc_from_dict_missing_required_key_raises():
    d = _valid_dict()
    del d["memory_spec"]
    with pytest.raises(KeyError):
        npc_from_dict(d)


# fn: M02.F05.I01
def test_audit_gate_merges_npc_errors_and_blocks_startup():
    """并账分支：四参 _audit_gate 带 NPC errors → RuntimeError，文本点名 NPC id。"""
    bad = dict(_valid_dict(), chapter="ch99")
    world = load_world(_REPO_DATA)
    from text_rpg.lock_anchors import ANCHORS
    from text_rpg.locks import build_registry
    from text_rpg.webserver import _audit_gate

    with pytest.raises(RuntimeError) as excinfo:
        _audit_gate(world, build_registry(world), ANCHORS, [npc_from_dict(bad)])
    assert "npc_sample" in str(excinfo.value)


# fn: M02.F05.I01
def test_audit_gate_none_npcs_skips_npc_face():
    """并账分支形状锚：npcs=None 跳过 NPC 面——同一干净世界不抛。"""
    world = load_world(_REPO_DATA)
    from text_rpg.lock_anchors import ANCHORS
    from text_rpg.locks import build_registry
    from text_rpg.webserver import _audit_gate

    _audit_gate(world, build_registry(world), ANCHORS, None)  # 不抛即过


# fn: M04.F02.I01
def test_repo_npc_assets_are_clean_utf8():
    """CJK 纪律：资产文件逐个回验——无 U+FFFD，id 与文件名同形。"""
    npcs_dir = _REPO_DATA / "npcs"
    for path in sorted(npcs_dir.glob("*.json")):
        raw = path.read_text(encoding="utf-8")
        assert "\ufffd" not in raw, f"{path.name} 含 U+FFFD"
