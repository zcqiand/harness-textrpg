"""Task 7/8：章包真数据内容断言（走 load_world 真加载器，不手搓 stub）。

- ch01 在章序首位，5 场景 / 3 锁 / 1 结局
- long_way 线走通 → game_over 且 ending id == "turned_back"
- ch02：entry_lock 未过章时锁章；证据线（观→验→三打）现原形并推进 ch03；
  无证据强打 → 被逐早终
- ch03：跨回锁（tang_convinced 开借扇门）分叉全德/强抢两线；
  全德线 → 现形归真，强抢线 → 借扇西行；12 锁 12 锚全量自审绿
"""

from __future__ import annotations

from pathlib import Path

from text_rpg.chapters import load_world
from text_rpg.engine import GameEngine, GameState
from text_rpg.lock_anchors import ANCHORS
from text_rpg.locks import audit, build_registry

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_ch01():
    world = load_world(_DATA_DIR)
    assert world.chapters, "章包目录空——ch01 未入库"
    first = world.chapters[0]
    assert first.id == "ch01", f"章序首位应为 ch01，实得 {first.id}"
    return world, first


def test_ch01_loads_and_starts():
    world, ch01 = _load_ch01()
    assert [s.id for s in ch01.scenes] == [
        "s01_village",
        "s01_woodcutter_hut",
        "s01_temple",
        "s01_foothill",
        "s01_cliff",
    ]
    assert len(ch01.scenes) == 5
    assert {lk.id for lk in ch01.locks} == {
        "lock_ch01_rations_gate",
        "lock_ch01_temple_spot",
        "lock_ch01_shortcut",
    }
    assert [e.id for e in ch01.endings] == ["turned_back"]
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    assert state.current_chapter == "ch01"
    assert state.current_scene == "s01_village"


def test_turned_back_ending_fires():
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    # 取干粮 → 出村（挂 rations_gate，须先有干粮）→ 山脚走远路 → 崖前坚持
    steps = [
        ("s01_village", "c_take_rations"),
        ("s01_village", "c_leave"),
        ("s01_foothill", "c_long_way"),
        ("s01_cliff", "c_press_on"),
    ]
    for scene_id, choice_id in steps:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over or (scene_id, choice_id) == steps[-1], (
            f"{scene_id}/{choice_id} 提前终局"
        )
    assert state.game_over is True
    assert state.ending == {"id": "turned_back", "title": "半途折返"}
    assert "went_long_way" in state.flags


# ---------- Task 8：回 2 三打白骨精 ----------

_SHORTCUT_TO_CH02 = [
    # 走 ch01 捷径线入 ch02：攀谈→听指点（insight 1→3）→化斋→出村→取捷径
    # （helped_woodcutter + chapter_ch01_complete → 推进 ch02）
    ("s01_village", "c_talk_woodcutter"),
    ("s01_woodcutter_hut", "c_listen"),
    ("s01_village", "c_take_rations"),
    ("s01_village", "c_leave"),
    ("s01_foothill", "c_shortcut"),
]


def _engine_in_ch02() -> tuple[GameEngine, GameState]:
    """shortcut 线走通 ch01 → 引擎停进 ch02 首场景 s02_first_meet。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    for scene_id, choice_id in _SHORTCUT_TO_CH02:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over, f"{scene_id}/{choice_id} 提前终局"
    assert state.current_chapter == "ch02"
    assert state.current_scene == "s02_first_meet"
    return engine, state


def test_ch02_entry_lock_blocks_until_ch01_complete():
    """直接构造 ch02 为当前章、无任何旗标 → chapters_view 里 ch02 locked=True。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    state.current_chapter = "ch02"
    state.current_scene = "s02_first_meet"
    rows = {r["id"]: r for r in engine.chapters_view(state)}
    assert rows["ch02"]["locked"] is True


def test_full_evidence_line_exposes_spirit():
    """观→验→三打证据线：白骨现原形（bone_spirit_exposed）且章推进到 ch03。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    steps = _SHORTCUT_TO_CH02 + [
        ("s02_first_meet", "c_observe"),
        ("s02_after_first", "c_move_on"),
        ("s02_second_meet", "c_verify"),
        ("s02_after_second", "c_proceed"),
        ("s02_third_meet", "c_strike_3"),
    ]
    for scene_id, choice_id in steps:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over, f"{scene_id}/{choice_id} 提前终局"
    assert "bone_spirit_exposed" in state.flags
    assert "chapter_ch02_complete" in state.flags
    # 未走 report 线 → 跨回旗标种子未种下（Task 9 的 ch03 门据此分叉）
    assert "tang_convinced" not in state.flags
    assert state.current_chapter == "ch03"
    assert state.current_scene == "s03_approach"
    assert state.game_over is False


def test_force_strike_ends_banished():
    """强打线（全程未证妖形）→ banished_early「被逐早终」即终局。"""
    engine, state = _engine_in_ch02()
    steps = [
        ("s02_first_meet", "c_strike_1"),
        ("s02_after_first", "c_move_on"),
        ("s02_second_meet", "c_verify"),
        ("s02_after_second", "c_proceed"),
        ("s02_third_meet", "c_force_strike"),
    ]
    for scene_id, choice_id in steps[:-1]:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over, f"{scene_id}/{choice_id} 提前终局"
    result = engine.submit_choice(state, *steps[-1])
    assert result.game_over is True
    assert state.game_over is True
    assert state.ending == {"id": "banished_early", "title": "被逐早终"}


# ---------- Task 9：回 3 火焰山（跨回锁收官） ----------


def test_cross_chapter_lock_needs_ch02_flag():
    """跨回锁：回 2 的 tang_convinced 缺 → 回 3 借扇相请之门锁死。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    state.current_chapter = "ch03"
    state.current_scene = "s03_cave_door"
    rows = {r["id"]: r for r in engine.choices_view(state)}
    assert rows["c_request"]["locked"] is True
    assert rows["c_request"]["missing"] == [
        {"type": "flag", "key": "tang_convinced", "have": False, "need": True}
    ]
    assert rows["c_request"]["denial"] is not None
    assert "师父未曾信你" in rows["c_request"]["denial"]


_SMART_TO_CH03 = _SHORTCUT_TO_CH02 + [
    # 全德线：观→验→报（tang_convinced）→三打 → 入回 3 → 相请→智取→辨真扇
    ("s02_first_meet", "c_observe"),
    ("s02_after_first", "c_move_on"),
    ("s02_second_meet", "c_verify"),
    ("s02_after_second", "c_report"),
    ("s02_third_meet", "c_strike_3"),
    ("s03_approach", "c_to_cave"),
    ("s03_cave_door", "c_request"),
    ("s03_plea", "c_appeal"),
    ("s03_pass_gate", "c_discern"),
]


def test_smart_line_reaches_true_form():
    """全德线（证据+服师+智取+辨真扇）→ 结局 true_form「现形归真」。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    for scene_id, choice_id in _SMART_TO_CH03[:-1]:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over, f"{scene_id}/{choice_id} 提前终局"
    result = engine.submit_choice(state, *_SMART_TO_CH03[-1])
    assert result.game_over is True
    assert state.game_over is True
    assert state.ending == {"id": "true_form", "title": "现形归真"}
    # 跨回拼接：bone_spirit_exposed（回 2）+ true_fan（回 3）两旗齐备
    assert {"bone_spirit_exposed", "true_fan", "tang_convinced"} <= state.flags
    assert "banana_leaf_fan" in state.backpack


_SNATCH_TO_CH03 = _SHORTCUT_TO_CH02 + [
    # 强抢线：未细观（insight 停在 3）→ 三打仍需二验 → 入回 3 → 强抢→挥扇过山
    ("s02_first_meet", "c_strike_1"),
    ("s02_after_first", "c_move_on"),
    ("s02_second_meet", "c_verify"),
    ("s02_after_second", "c_proceed"),
    ("s02_third_meet", "c_strike_3"),
    ("s03_approach", "c_to_cave"),
    ("s03_cave_door", "c_snatch"),
    ("s03_snatch", "c_grab_forced"),
    ("s03_pass_gate", "c_cross"),
]


def test_snatch_line_reaches_west_won():
    """强抢线（无 true_fan）→ 结局 west_won「借扇西行」，辨真之门对其锁死。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    for scene_id, choice_id in _SNATCH_TO_CH03[:-1]:
        result = engine.submit_choice(state, scene_id, choice_id)
        assert not result.state.game_over, f"{scene_id}/{choice_id} 提前终局"
    # insight 未足 4：辨真扇对其锁死（missing 首条指 insight）
    rows = {r["id"]: r for r in engine.choices_view(state)}
    assert rows["c_discern"]["locked"] is True
    result = engine.submit_choice(state, *_SNATCH_TO_CH03[-1])
    assert result.game_over is True
    assert state.game_over is True
    assert state.ending == {"id": "west_won", "title": "借扇西行"}
    assert "crossed_mountain" in state.flags
    assert "suspect_fake" in state.flags
    assert "banana_leaf_fan" in state.backpack
    assert state.current_scene == "s03_summit"


def test_registry_audit_full_green():
    """全量真数据收官自审：3 章共 12 锁、12 锚双侧齐备，audit errors == []。"""
    world = load_world(_DATA_DIR)
    registry = build_registry(world)
    assert len(registry) == 12
    assert set(ANCHORS) == set(registry), "锚表与注册表失配"
    report = audit(world, registry, ANCHORS)
    assert report.errors == []
