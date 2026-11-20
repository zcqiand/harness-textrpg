"""Task 7：回 1 章包真数据内容断言（走 load_world 真加载器，不手搓 stub）。

- ch01 在章序首位，5 场景 / 3 锁 / 1 结局
- long_way 线走通 → game_over 且 ending id == "turned_back"
"""

from __future__ import annotations

from pathlib import Path

from text_rpg.chapters import load_world
from text_rpg.engine import GameEngine
from text_rpg.locks import build_registry

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
