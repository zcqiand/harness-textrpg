"""Task M04.F03.I01：对手卡集资产（TDD 先红后绿）。

契约形状以 v2/v3 design spec §5.5 为准（data/opponents/*.json）：
对手卡 = 属性 + 策略表（数据驱动行动规约），策略表每行含 when+action+power，
且须有 default 行兜底。量口径：总数 ≥3、每回（ch01/ch02/ch03）≥1。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from text_rpg.chapters import load_world
from text_rpg.opponents import audit_opponents, load_opponents, opponent_from_dict

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_REQUIRED_KEYS = {"id", "name", "chapter", "base", "strategy_table"}


def _load_opponent_cards() -> list[dict]:
    cards_dir = _REPO_DATA / "opponents"
    assert cards_dir.is_dir(), "data/opponents/ 目录不存在（对手卡资产未落）"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cards_dir.glob("*.json"))]


# fn: M04.F03.I01
def test_opponent_contracts_exist_and_shape():
    cards = _load_opponent_cards()

    # 量口径一：对手卡总数 ≥3
    assert len(cards) >= 3, f"对手卡总数 {len(cards)} < 3"

    # 量口径二：每回 ≥1 张（章清单从 load_world 派生，不硬编码 ch01/ch02/ch03）
    world = load_world(_REPO_DATA)
    chapter_ids = {c.id for c in world.chapters}
    chapters = {c["chapter"] for c in cards}
    for cid in chapter_ids:
        assert cid in chapters, f"章 {cid} 名下零挂载对手卡"

    ids = [c["id"] for c in cards]
    assert len(set(ids)) == len(ids), f"对手卡 id 重复：{ids}"

    for card in cards:
        # 形状键齐：id/name/chapter/base/strategy_table
        missing = _REQUIRED_KEYS - set(card)
        assert not missing, f"{card.get('id', '<unknown>')} 缺形状键 {sorted(missing)}"

        assert isinstance(card["name"], str) and card["name"], f"{card['id']} name 为空"
        assert isinstance(card["base"], dict) and card["base"], (
            f"{card['id']} base 须为非空属性映射"
        )
        assert all(isinstance(v, int) for v in card["base"].values()), (
            f"{card['id']} base 属性值须为 int"
        )

        # 策略表：非空，每行含 when+action+power，且须有 default 行
        table = card["strategy_table"]
        assert isinstance(table, list) and table, f"{card['id']} strategy_table 为空"
        for i, row in enumerate(table):
            for key in ("when", "action", "power"):
                assert key in row, f"{card['id']} strategy_table[{i}] 缺键 {key}"
            assert isinstance(row["action"], str) and row["action"], (
                f"{card['id']} strategy_table[{i}] action 为空"
            )
            assert isinstance(row["power"], int), f"{card['id']} strategy_table[{i}] power 须为 int"
        assert any(row.get("when", {}).get("default") is True for row in table), (
            f"{card['id']} strategy_table 缺 default 行"
        )


def _valid_opponent_dict() -> dict:
    """契约合法的最小对手卡 dict（审计用工厂，不落盘）。"""
    return {
        "id": "opp_sample",
        "name": "巡山小妖",
        "chapter": "ch01",
        "base": {"might": 2, "deception": 1},
        "strategy_table": [
            {"when": {"player_flag": "foo"}, "action": "poke", "power": 1},
            {"when": {"default": True}, "action": "growl", "power": 2},
        ],
    }


# fn: M02.F06.I01
def test_load_opponents_missing_dir_fails_fast(tmp_path):
    """fail-fast 锚：data/opponents/ 目录缺失 → raise 点名目录路径（禁静默返 []）。"""
    with pytest.raises(FileNotFoundError) as excinfo:
        load_opponents(tmp_path)
    assert "目录缺失" in str(excinfo.value)


# fn: M02.F06.I01
def test_load_opponents_empty_dir_fails_fast(tmp_path):
    """fail-fast 锚：目录在但零契约文件 → raise（对手卡功能面全死不许 vacuous 过）。"""
    (tmp_path / "opponents").mkdir()
    with pytest.raises(ValueError) as excinfo:
        load_opponents(tmp_path)
    assert "零契约文件" in str(excinfo.value)


# fn: M02.F06.I01
def test_load_opponents_reads_repo_assets_sorted():
    opponents = load_opponents(_REPO_DATA)
    assert [o.id for o in opponents] == [
        "opp_bone_spirit",
        "opp_prince_dragon",
        "opp_princess_fan",
    ]


# fn: M02.F06.I01
def test_repo_opponent_assets_load_and_pass_audit():
    """干净世界锚：真 data/ + 真 world 加载 → audit errors == []（warnings 同空）。"""
    opponents = load_opponents(_REPO_DATA)
    world = load_world(_REPO_DATA)
    report = audit_opponents(opponents, world)
    assert report.errors == [] and report.warnings == []


# fn: M02.F06.I01
def test_audit_dangling_chapter_reference_is_error():
    bad = dict(_valid_opponent_dict(), chapter="ch99")
    world = load_world(_REPO_DATA)
    report = audit_opponents([opponent_from_dict(bad)], world)
    assert any("ch99" in msg and "悬空" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_empty_strategy_table_is_error():
    bad = dict(_valid_opponent_dict(), strategy_table=[])
    world = load_world(_REPO_DATA)
    report = audit_opponents([opponent_from_dict(bad)], world)
    assert any("opp_sample" in msg and "strategy_table" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_strategy_table_missing_default_row_is_error():
    bad = _valid_opponent_dict()
    bad["strategy_table"] = [r for r in bad["strategy_table"] if not r["when"].get("default")]
    world = load_world(_REPO_DATA)
    report = audit_opponents([opponent_from_dict(bad)], world)
    assert any("opp_sample" in msg and "default" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_below_min_opponent_count_is_error():
    """量口径入闸锚：对手卡总数 <3 → audit 红，报错点名缺口。"""
    two = [
        opponent_from_dict(_valid_opponent_dict()),
        opponent_from_dict(dict(_valid_opponent_dict(), id="opp_two", name="守门妖")),
    ]
    world = load_world(_REPO_DATA)
    report = audit_opponents(two, world)
    assert any("对手卡总数不足" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_chapter_without_mounted_opponent_is_error():
    """量口径入闸锚：world 章清单任一章名下零挂载对手卡（按契约 chapter 字段统计，
    不硬编码章清单）→ audit 红，报错点名缺口章 id。"""
    world = load_world(_REPO_DATA)
    three_same_chapter = [
        opponent_from_dict(dict(_valid_opponent_dict(), id=f"opp_{i}", name=f"小妖{i}"))
        for i in range(3)
    ]
    report = audit_opponents(three_same_chapter, world)
    mounted = {o.chapter for o in three_same_chapter}
    bare = [c.id for c in world.chapters if c.id not in mounted]
    assert bare  # 前提：真世界确有未挂载章，锚才有意义
    for cid in bare:
        assert any(f"章 {cid}" in msg and "无挂载" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_blank_name_is_error():
    """空白词面锚：name 为空串/纯空白 → audit 红。"""
    bad = dict(_valid_opponent_dict(), name="   ")
    world = load_world(_REPO_DATA)
    report = audit_opponents([opponent_from_dict(bad)], world)
    assert any("opp_sample" in msg and "name" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_blank_action_word_is_error():
    """空白词面锚：strategy_table 行 action 为空串/纯空白 → audit 红。"""
    bad = _valid_opponent_dict()
    bad["strategy_table"] = [
        {"when": {"default": True}, "action": "  ", "power": 1},
    ]
    world = load_world(_REPO_DATA)
    report = audit_opponents([opponent_from_dict(bad)], world)
    assert any("opp_sample" in msg and "action" in msg for msg in report.errors)


# ------------------------------------------------- 审查建议收口（base / 缺分支 / 启动闸）


# fn: M02.F06.I01
def test_audit_base_empty_dict_is_error():
    """base 校验（建议①）：base 空 dict → audit 红（结算属性面不得为空，T11 要消费 base）。"""
    card = opponent_from_dict(_valid_opponent_dict())
    bad = replace(card, base={})
    world = load_world(_REPO_DATA)
    report = audit_opponents([bad], world)
    assert any("opp_sample" in msg and "base" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_base_non_int_value_is_error():
    """base 校验（建议①）：base 值非 int → audit 红（bool 为 int 子类一并拒）。"""
    card = opponent_from_dict(_valid_opponent_dict())
    bad = replace(card, base={"might": "3"})
    world = load_world(_REPO_DATA)
    report = audit_opponents([bad], world)
    assert any("opp_sample" in msg and "base" in msg and "int" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_audit_strategy_table_non_list_is_error():
    """miss 侧：strategy_table 非 list 型 → audit 红。"""
    card = opponent_from_dict(_valid_opponent_dict())
    bad = replace(card, strategy_table="not-a-list")
    world = load_world(_REPO_DATA)
    report = audit_opponents([bad], world)
    assert any("opp_sample" in msg and "strategy_table" in msg for msg in report.errors)


# fn: M02.F06.I01
def test_opponent_from_dict_missing_required_key_raises():
    """miss 侧：对手卡缺必填键 → KeyError。"""
    d = _valid_opponent_dict()
    del d["strategy_table"]
    with pytest.raises(KeyError):
        opponent_from_dict(d)


# fn: M02.F06.I01
def test_opponent_from_dict_non_dict_raises():
    """miss 侧：非 dict 输入 → ValueError。"""
    with pytest.raises(ValueError):
        opponent_from_dict(["not", "a", "dict"])


# fn: M02.F06.I01
def test_create_app_rejects_bad_opponent_contract(tmp_path, monkeypatch):
    """启动闸变异自证：真 data/ 复制后篡改一张对手卡 chapter 为悬空章 →
    create_app RuntimeError（对手卡审计真挂闸，npcs/guard_anchors 同形）。"""
    from text_rpg import webserver

    staged = tmp_path / "data"
    shutil.copytree(_REPO_DATA, staged)
    target = staged / "opponents" / "opp_bone_spirit.json"
    card = json.loads(target.read_text(encoding="utf-8"))
    card["chapter"] = "ch99"
    target.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(webserver, "_data_dir", lambda: staged)

    with pytest.raises(RuntimeError) as excinfo:
        webserver.create_app()
    assert "opp_bone_spirit" in str(excinfo.value)
