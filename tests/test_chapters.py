"""Task 3：chapters.py 章回包 dataclass + load_world 加载器（TDD 先红后绿）。"""

import json

import pytest
from text_rpg.chapters import load_world


def test_load_start_state(tmp_path):
    # tmp_path 里放最小 game-start.json：{"attributes": {"insight": 1}, "backpack": []}
    (tmp_path / "game-start.json").write_text(
        json.dumps({"attributes": {"insight": 1}, "backpack": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    world = load_world(tmp_path)
    assert world.start_attributes == {"insight": 1} and world.start_backpack == []


def test_missing_data_dir_readable_error(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_world(tmp_path / "nope")
    assert "game-start.json" in str(e.value)  # 可读错误，不含 traceback 路径


def test_empty_chapters_dir_ok(tmp_path):
    world = load_world(tmp_path)
    assert world.chapters == []


def test_chapter_pack_maps_to_dataclasses(tmp_path):
    (tmp_path / "game-start.json").write_text(
        json.dumps({"attributes": {"insight": 1}, "backpack": ["干粮"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    cdir = tmp_path / "chapters"
    cdir.mkdir()
    (cdir / "ch02.json").write_text(
        json.dumps(
            {
                "id": "ch02",
                "title": "第二章",
                "entry_locks": ["gate2"],
                "locks": [
                    {
                        "id": "gate2",
                        "requires": [{"type": "attr", "name": "insight", "op": ">=", "value": 2}],
                        "denial": "悟性不足",
                        "effects": [{"type": "flag", "name": "gate2_open"}],
                    }
                ],
                "scenes": [
                    {
                        "id": "s1",
                        "text": "山门在前。",
                        "choices": [
                            {"id": "c1", "text": "叩门", "lock": "gate2", "goto": "s2"},
                            {
                                "id": "c2",
                                "text": "绕行",
                                "effects": [{"type": "flag", "name": "detour"}],
                            },
                        ],
                    },
                    {"id": "s2", "text": "门开了。", "choices": []},
                ],
                "endings": [
                    {
                        "id": "ch02-e1",
                        "title": "入门",
                        "requires": [{"type": "flag", "name": "gate2_open"}],
                    },
                    {"id": "ch02-e2", "title": "流落", "requires": [], "mid_chapter": True},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (cdir / "ch01.json").write_text(
        json.dumps(
            {
                "id": "ch01",
                "title": "第一章",
                "entry_locks": [],
                "locks": [],
                "scenes": [{"id": "s1", "text": "开局。", "choices": []}],
                "endings": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    world = load_world(tmp_path)
    # 按文件名序：ch01 在前
    assert [c.id for c in world.chapters] == ["ch01", "ch02"]
    ch02 = world.chapters[1]
    assert ch02.title == "第二章"
    assert ch02.entry_locks == ["gate2"]
    # LockDef.chapter_id 装载期回填父章 id
    assert ch02.locks[0].chapter_id == "ch02"
    assert ch02.locks[0].denial == "悟性不足"
    # Choice.lock / goto 可选；effects 保持原始 dict
    c1, c2 = ch02.scenes[0].choices
    assert c1.lock == "gate2" and c1.goto == "s2" and c1.effects == []
    assert c2.lock is None and c2.goto is None
    assert c2.effects == [{"type": "flag", "name": "detour"}]
    # EndingDef：chapter_id=父章 id（装载期填，非计算）；mid_chapter 缺省 False
    e1, e2 = ch02.endings
    assert e1.chapter_id == "ch02" and e1.mid_chapter is False
    assert e2.mid_chapter is True


def test_bad_game_start_json_names_file(tmp_path):
    (tmp_path / "game-start.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError) as e:
        load_world(tmp_path)
    assert "game-start.json" in str(e.value)
