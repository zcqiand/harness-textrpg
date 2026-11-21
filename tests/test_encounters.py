"""Task M04.F03.I02（T13 资产）+ M02.F07.I01（T14 加载与自审）：TDD 先红后绿。

奇遇模板形状以 v2/v3 design spec §5.6 为准（data/encounter-templates/*.json）：
模板 = 题材骨架 + 参数化槽位（场景文本模板/锁条件槽/效果槽）+ 难度规约
difficulty {attr_min, locks_max}。量口径：模板总数 ≥2。
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest
from text_rpg.encounters import (
    audit_encounter_templates,
    encounter_template_from_dict,
    load_encounter_templates,
)

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_REQUIRED_KEYS = {
    "id",
    "name",
    "params",
    "scene_template",
    "lock_slots",
    "effect_slots",
    "difficulty",
}
_EFFECT_KEYS = {"attr", "item_add", "item_remove", "flag"}


def _load_template_assets() -> list[dict]:
    templates_dir = _REPO_DATA / "encounter-templates"
    assert templates_dir.is_dir(), "data/encounter-templates/ 目录不存在（奇遇模板资产未落）"
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(templates_dir.glob("*.json"))]


def _valid_template_dict() -> dict:
    """契约合法的最小奇遇模板 dict（审计用工厂，不落盘）。"""
    return {
        "id": "enc_sample",
        "name": "山中奇遇",
        "params": ["place"],
        "scene_template": "行至{place}，忽有异象扑面。",
        "lock_slots": [
            {
                "id": "enc_sample_lock",
                "requires": [{"attr": "insight", "op": ">=", "value": 1}],
                "denial": "机缘未至，不可强求。",
            }
        ],
        "effect_slots": [{"flag": "enc_sample_done"}],
        "difficulty": {"attr_min": 1, "locks_max": 2},
    }


# fn: M04.F03.I02
def test_encounter_templates_exist_and_shape():
    templates = _load_template_assets()

    # 量口径：奇遇模板总数 ≥2（spec §6：含留书稿练习新增 1 个的空间）
    assert len(templates) >= 2, f"奇遇模板总数 {len(templates)} < 2"

    ids = [t["id"] for t in templates]
    assert len(set(ids)) == len(ids), f"奇遇模板 id 重复：{ids}"
    assert {"enc_lost_sutra", "enc_fruit_grove"} <= set(ids), f"两件指定模板缺失：{ids}"

    for t in templates:
        # 形状键齐：id/name/params/scene_template/lock_slots/effect_slots/difficulty
        missing = _REQUIRED_KEYS - set(t)
        assert not missing, f"{t.get('id', '<unknown>')} 缺形状键 {sorted(missing)}"

        assert isinstance(t["name"], str) and t["name"].strip(), f"{t['id']} name 为空白词面"
        assert isinstance(t["scene_template"], str) and t["scene_template"].strip(), (
            f"{t['id']} scene_template 为空白"
        )

        # 参数化槽位：场景文本模板中的 {param} 占位必须都在 params 里声明（无悬空）
        declared = set(t["params"])
        used = set(re.findall(r"\{(\w+)\}", t["scene_template"]))
        assert used <= declared, f"{t['id']} 场景文本模板悬空占位 {sorted(used - declared)}"

        # 锁条件槽：非空，每行含 id/requires/denial，denial 非空白（空 denial 红）
        lock_slots = t["lock_slots"]
        assert isinstance(lock_slots, list) and lock_slots, f"{t['id']} lock_slots 为空"
        for i, slot in enumerate(lock_slots):
            for key in ("id", "requires", "denial"):
                assert key in slot, f"{t['id']} lock_slots[{i}] 缺键 {key}"
            assert isinstance(slot["requires"], list) and slot["requires"], (
                f"{t['id']} lock_slots[{i}] requires 为空"
            )
            assert isinstance(slot["denial"], str) and slot["denial"].strip(), (
                f"{t['id']} lock_slots[{i}] denial 为空白词面"
            )

        # 效果槽：非空，每条为 v1 效果四类之一（attr/item_add/item_remove/flag）
        effect_slots = t["effect_slots"]
        assert isinstance(effect_slots, list) and effect_slots, f"{t['id']} effect_slots 为空"
        for i, eff in enumerate(effect_slots):
            assert set(eff) == {sorted(set(eff))[0]}, f"{t['id']} effect_slots[{i}] 形状不符：{eff}"
            assert set(eff) <= _EFFECT_KEYS, (
                f"{t['id']} effect_slots[{i}] 非法效果类型：{sorted(eff)}"
            )

        # 难度规约：attr_min / locks_max 齐且为非负 int
        diff = t["difficulty"]
        for key in ("attr_min", "locks_max"):
            assert key in diff, f"{t['id']} difficulty 缺键 {key}"
            value = diff[key]
            assert isinstance(value, int) and not isinstance(value, bool) and value >= 0, (
                f"{t['id']} difficulty.{key} 须为非负 int，实得 {value!r}"
            )


# ------------------------------------------------- T14：加载与自审（M02.F07.I01）


# fn: M02.F07.I01
def test_load_encounter_templates_missing_dir_fails_fast(tmp_path):
    """fail-fast 锚：data/encounter-templates/ 目录缺失 → raise 点名目录路径（禁静默返 []）。"""
    with pytest.raises(FileNotFoundError) as excinfo:
        load_encounter_templates(tmp_path)
    assert "目录缺失" in str(excinfo.value)


# fn: M02.F07.I01
def test_load_encounter_templates_empty_dir_fails_fast(tmp_path):
    """fail-fast 锚：目录在但零模板文件 → raise（奇遇功能面全死不许 vacuous 过）。"""
    (tmp_path / "encounter-templates").mkdir()
    with pytest.raises(ValueError) as excinfo:
        load_encounter_templates(tmp_path)
    assert "零模板文件" in str(excinfo.value)


# fn: M02.F07.I01
def test_load_encounter_templates_reads_repo_assets_sorted():
    templates = load_encounter_templates(_REPO_DATA)
    assert [t.id for t in templates] == ["enc_fruit_grove", "enc_lost_sutra"]


# fn: M02.F07.I01
def test_repo_template_assets_load_and_pass_audit():
    """干净世界锚：真 data/ 加载 → audit errors == []（warnings 同空）。"""
    templates = load_encounter_templates(_REPO_DATA)
    report = audit_encounter_templates(templates)
    assert report.errors == [] and report.warnings == []


# fn: M02.F07.I01
def test_audit_below_min_template_count_is_error():
    """量口径入闸锚：奇遇模板总数 <2 → audit 红，报错点名缺口。"""
    one = [encounter_template_from_dict(_valid_template_dict())]
    report = audit_encounter_templates(one)
    assert any("奇遇模板总数不足" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_dangling_scene_placeholder_is_error():
    """悬空引用锚：场景文本模板占位 {ghost} 未在 params 声明 → audit 红。"""
    bad = _valid_template_dict()
    bad["scene_template"] = "行至{place}，{ghost}拦路。"
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "悬空" in msg and "ghost" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_blank_denial_is_error():
    """空 denial 锚：锁条件槽 denial 为空串/纯空白 → audit 红。"""
    bad = _valid_template_dict()
    bad["lock_slots"] = [
        {"id": "enc_sample_lock", "requires": [{"flag": "foo"}], "denial": "   "},
    ]
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "denial" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_blank_scene_template_is_error():
    """空槽位锚：场景文本模板为空串/纯空白 → audit 红。"""
    bad = _valid_template_dict()
    bad["scene_template"] = "  "
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "scene_template" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_empty_lock_slots_is_error():
    """空槽位锚：lock_slots 空 → audit 红（锁条件槽不得为空）。"""
    bad = _valid_template_dict()
    bad["lock_slots"] = []
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "lock_slots" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_empty_effect_slots_is_error():
    """空槽位锚：effect_slots 空 → audit 红（效果槽不得为空）。"""
    bad = _valid_template_dict()
    bad["effect_slots"] = []
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "effect_slots" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_audit_difficulty_missing_key_is_error():
    """难度规约锚：difficulty 缺 attr_min / locks_max → audit 红。"""
    bad = _valid_template_dict()
    del bad["difficulty"]["locks_max"]
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any(
        "enc_sample" in msg and "difficulty" in msg and "locks_max" in msg for msg in report.errors
    )


# fn: M02.F07.I01
def test_audit_difficulty_negative_value_is_error():
    """难度规约锚：difficulty 值为负数 → audit 红。"""
    bad = _valid_template_dict()
    bad["difficulty"] = {"attr_min": 1, "locks_max": -1}
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any(
        "enc_sample" in msg and "difficulty" in msg and "locks_max" in msg for msg in report.errors
    )


# fn: M02.F07.I01
def test_audit_difficulty_non_int_value_is_error():
    """难度规约锚：difficulty 值非 int → audit 红（bool 为 int 子类一并拒）。
    经 from_dict 的 int() 收编后无法直达 audit，故照 opponents 同款用
    dataclasses.replace 绕过收编直构（opponents test_audit_base_non_int 同形）。"""
    card = encounter_template_from_dict(_valid_template_dict())
    bad = replace(card, difficulty={"attr_min": "2", "locks_max": 2})
    report = audit_encounter_templates([bad, encounter_template_from_dict(_valid_template_dict())])
    assert any(
        "enc_sample" in msg and "difficulty" in msg and "int" in msg for msg in report.errors
    )


# fn: M02.F07.I01
def test_audit_blank_name_is_error():
    """空白词面锚：name 为空串/纯空白 → audit 红。"""
    bad = _valid_template_dict()
    bad["name"] = "  "
    report = audit_encounter_templates(
        [encounter_template_from_dict(bad), encounter_template_from_dict(_valid_template_dict())]
    )
    assert any("enc_sample" in msg and "name" in msg for msg in report.errors)


# fn: M02.F07.I01
def test_encounter_template_from_dict_missing_required_key_raises():
    """miss 侧：奇遇模板缺必填键 → KeyError。"""
    d = _valid_template_dict()
    del d["difficulty"]
    with pytest.raises(KeyError):
        encounter_template_from_dict(d)


# fn: M02.F07.I01
def test_encounter_template_from_dict_non_dict_raises():
    """miss 侧：非 dict 输入 → ValueError。"""
    with pytest.raises(ValueError):
        encounter_template_from_dict(["not", "a", "dict"])
