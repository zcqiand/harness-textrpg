"""Task 5：engine.py 状态机——门控/效果/goto/章推进/结局判定（TDD 先红后绿）。

用两个内存小章包构造，不依赖真实 data/。
章完成旗约定：chapter_<章id>_complete（如 ch01 → chapter_ch01_complete）。
"""

import pytest
from text_rpg.chapters import Chapter, Choice, EndingDef, LockDef, Scene, World
from text_rpg.engine import GameEngine


def make_world() -> World:
    """两章小世界：ch01 无门（推门链）+ ch02 挂 entry_lock（要路引）。"""
    ch01 = Chapter(
        id="ch01",
        title="第一章",
        locks=[
            LockDef(
                id="key_gate",
                requires=[{"flag": "has_key"}],
                denial="没有钥匙，门纹丝不动",
            ),
            LockDef(id="post_lock", requires=[{"flag": "door_opened"}], denial="门未开"),
        ],
        scenes=[
            Scene(
                id="s1",
                text="山门前",
                choices=[
                    Choice(id="look", text="打量山门"),
                    Choice(
                        id="open",
                        text="推门",
                        lock="key_gate",
                        goto="s2",
                        effects=[{"flag": "door_opened"}],
                    ),
                ],
            ),
            Scene(
                id="s2",
                text="门内",
                choices=[
                    Choice(
                        id="west",
                        text="西行",
                        effects=[{"flag": "chapter_ch01_complete"}],
                    ),
                ],
            ),
        ],
        endings=[
            EndingDef(
                id="end_good",
                title="善终",
                requires=[{"flag": "good_end"}],
                mid_chapter=True,
            ),
            EndingDef(id="end_bad", title="困死山中", requires=[{"flag": "bad_end"}]),
        ],
    )
    ch02 = Chapter(
        id="ch02",
        title="第二章",
        entry_locks=["entry_gate"],
        locks=[
            LockDef(
                id="entry_gate",
                requires=[{"item": "passport"}],
                denial="无路引，过不得边界",
            )
        ],
        scenes=[Scene(id="s3", text="边界", choices=[Choice(id="go", text="赶路")])],
        endings=[EndingDef(id="end_west", title="西去", requires=[{"flag": "arrived"}])],
    )
    return World(
        chapters=[ch01, ch02],
        start_attributes={"courage": 2},
        start_backpack=["dry_rations"],
    )


def make_engine() -> GameEngine:
    from text_rpg.locks import build_registry

    world = make_world()
    return GameEngine(world, build_registry(world))


def test_new_game_uses_start_state():
    eng = make_engine()
    st = eng.new_game("悟空")
    assert st.player_name == "悟空"
    assert st.attributes == {"courage": 2}
    assert st.backpack == ["dry_rations"]
    assert st.current_chapter == "ch01"
    assert st.current_scene == "s1"
    assert st.flags == set()
    assert st.game_over is False
    assert st.ending is None


def test_locked_choice_rejected_with_denial():
    eng = make_engine()
    st = eng.new_game("悟空")
    res = eng.submit_choice(st, "s1", "open")
    assert "没有钥匙，门纹丝不动" in res.messages
    assert res.unlocked_locks == []
    assert res.game_over is False
    assert res.ending is None
    # 状态不变：没进门、没写旗
    assert st.current_scene == "s1"
    assert st.flags == set()


def test_choice_effects_and_goto_applied():
    eng = make_engine()
    st = eng.new_game("悟空")
    st.flags.add("has_key")
    # view 时：key_gate 已满足（不锁），post_lock 未满足（锁）
    view = {c["id"]: c for c in eng.choices_view(st)}
    assert view["open"]["locked"] is False
    assert view["open"]["missing"] == []
    assert "post_lock" not in _satisfied_ids(eng, st)
    res = eng.submit_choice(st, "s1", "open")
    # effects 生效 + goto 换场景
    assert "door_opened" in st.flags
    assert st.current_scene == "s2"
    # unlocked_locks：view 时未满足、效果后满足的锁
    assert res.unlocked_locks == ["post_lock"]
    assert any("door_opened" in m for m in res.messages)
    assert res.game_over is False


def _satisfied_ids(eng, st):
    from text_rpg.contracts import evaluate

    return [lock_id for lock_id, lk in eng.registry.items() if evaluate(lk.requires, st).satisfied]


def test_chapter_advance_on_complete_flag():
    eng = make_engine()
    st = eng.new_game("悟空")
    st.flags.add("has_key")
    st.backpack.append("passport")  # ch02 entry_lock 条件备齐
    eng.submit_choice(st, "s1", "open")
    res = eng.submit_choice(st, "s2", "west")
    assert st.current_chapter == "ch02"
    assert st.current_scene == "s3"  # 下一章首个场景
    assert any("第二章" in m for m in res.messages)


def test_chapter_advance_blocked_by_entry_lock():
    eng = make_engine()
    st = eng.new_game("悟空")
    st.flags.add("has_key")  # 不给 passport
    eng.submit_choice(st, "s1", "open")
    res = eng.submit_choice(st, "s2", "west")
    assert st.current_chapter == "ch01"
    assert st.current_scene == "s2"
    assert any("无路引，过不得边界" in m for m in res.messages)


def test_mid_chapter_ending_fires_and_locks_input():
    eng = make_engine()
    st = eng.new_game("悟空")
    st.flags.add("good_end")
    res = eng.submit_choice(st, "s1", "look")  # 无效果抉择也触发结局扫描
    assert res.game_over is True
    assert res.ending == {"id": "end_good", "title": "善终"}
    assert st.game_over is True
    with pytest.raises(ValueError, match="游戏已结束"):
        eng.submit_choice(st, "s1", "open")


def test_choices_view_reports_missing_detail():
    eng = make_engine()
    st = eng.new_game("悟空")
    rows = eng.choices_view(st)
    assert [r["id"] for r in rows] == ["look", "open"]
    assert rows[0] == {
        "id": "look",
        "text": "打量山门",
        "locked": False,
        "missing": [],
        "denial": None,
    }
    assert rows[1]["locked"] is True
    assert rows[1]["missing"] == [{"type": "flag", "key": "has_key", "have": False, "need": True}]
    assert rows[1]["denial"] == "没有钥匙，门纹丝不动"


def test_endings_view_satisfied_and_missing():
    eng = make_engine()
    st = eng.new_game("悟空")
    rows = eng.endings_view(st)
    # 按章声明序拼接：ch01 两条在前，ch02 一条在后
    assert [r["id"] for r in rows] == ["end_good", "end_bad", "end_west"]
    assert all(r["satisfied"] is False for r in rows)
    assert rows[0]["missing"] == [{"type": "flag", "key": "good_end", "have": False, "need": True}]
    st.flags.add("good_end")
    rows2 = eng.endings_view(st)
    assert rows2[0]["satisfied"] is True
    assert rows2[0]["title"] == "善终"
    assert rows2[1]["satisfied"] is False


def test_chapters_view_locked_flags():
    eng = make_engine()
    st = eng.new_game("悟空")
    rows = eng.chapters_view(st)
    assert [r["id"] for r in rows] == ["ch01", "ch02"]
    assert rows[0]["locked"] is False  # 无 entry_locks
    assert rows[1]["locked"] is True  # entry_gate 要 passport
    st.backpack.append("passport")
    assert eng.chapters_view(st)[1]["locked"] is False
