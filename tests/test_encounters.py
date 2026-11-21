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
    EncounterRejectedError,
    audit_encounter_templates,
    encounter_template_from_dict,
    generate_encounter,
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


# ------------------------------------------- T15：种子化生成器与无效过滤（M02.F07.I02）
# 生成器流程：random.Random(seed) 实例化（禁全局 random）→ params 填充场景模板占位符
# → 锁槽逐一自检（缺锚/空 denial）→ 种子化实例化锁（生成带 [1, BAND] 内种子定数）
# → 无效过滤五查（悬空/缺锚/空 denial/超锁上限/难度越界）→ 候选奇遇
# （形状对齐 v1 章包：scene{id,text,npc_ids,choices} / locks v1 锁形状+锚注记 / effects 四类）。
# 锚纪律裁定（spec §5.6）：生成锁不进 lock_anchors 静态锚表，锚由生成器派生标注，
# 由本文件模板级双向断言（test_template_level_bidirectional_*）承担。

_PARAM_VALUES = {"place": "两界山下", "fruit": "青皮仙果", "elder": "老比丘"}


def _template_by_id(template_id):
    by_id = {t.id: t for t in load_encounter_templates(_REPO_DATA)}
    assert template_id in by_id, f"真模板缺失：{template_id}"
    return by_id[template_id]


def _params_for(template):
    return {p: _PARAM_VALUES.get(p, f"「{p}」所在处") for p in template.params}


def _with_lock_slot(template, index, **mutations):
    """构造模板变体：深拷贝锁槽列后改第 index 槽（不回灌真模板）。"""
    slots = [dict(s) for s in template.lock_slots]
    slots[index] = dict(slots[index], **mutations)
    return replace(template, lock_slots=slots)


def _with_difficulty(template, **mutations):
    return replace(template, difficulty=dict(template.difficulty, **mutations))


def _first_admitted_seed(template, params):
    for seed in range(2000):
        try:
            generate_encounter(template, params, seed)
        except EncounterRejectedError:
            continue
        return seed
    raise AssertionError("2000 个种子内无一种子可过五类无效过滤")


def _seed_rejected_with(template, params, keyword):
    """扫描出第一个拒收报因含 keyword 的种子（生成器确定性 → 扫描结果稳定）。"""
    for seed in range(2000):
        try:
            generate_encounter(template, params, seed)
        except EncounterRejectedError as exc:
            if keyword in str(exc):
                return seed
    raise AssertionError(f"2000 个种子内未见报因含「{keyword}」的种子")


# fn: M02.F07.I02
def test_generate_encounter_seeded_replay_identical():
    """同种子+同模板+同参数两次生成结果全等（禁全局 random，只吃 random.Random(seed)）。"""
    template = _template_by_id("enc_fruit_grove")
    params = _params_for(template)
    seed = _first_admitted_seed(template, params)
    first = generate_encounter(template, params, seed)
    second = generate_encounter(template, params, seed)
    assert first == second
    assert first.scene == second.scene
    assert first.locks == second.locks
    assert first.effects == second.effects


# fn: M02.F07.I02
def test_generate_encounter_valid_seed_produces_v1_shape():
    """有效种子准入：候选奇遇形状对齐 v1 章包的场景/锁/效果。"""
    template = _template_by_id("enc_lost_sutra")
    params = _params_for(template)
    seed = _first_admitted_seed(template, params)
    candidate = generate_encounter(template, params, seed)
    # 场景面：id/text/npc_ids/choices 四键齐（v1 Scene 形状）
    assert set(candidate.scene) >= {"id", "text", "npc_ids", "choices"}
    assert candidate.scene["npc_ids"] == []
    # 锁面：非空，每把锁 v1 锁形状 + 生成器派生的断言锚注记（正反两侧齐）
    assert candidate.locks
    assert len(candidate.locks) <= template.difficulty["locks_max"]
    for lock in candidate.locks:
        assert set(lock) >= {"id", "requires", "denial", "effects"}
        anchor = lock["assertion_anchor"]
        assert anchor["pass"].strip() and anchor["deny"].strip()
    # 效果面：v1 效果四类（attr/item_add/item_remove/flag）
    for eff in candidate.effects:
        assert set(eff) <= {"attr", "item_add", "item_remove", "flag"}
    # 场景抉择挂第一把锁（v1 choice.lock 形状），效果面挂抉择
    assert candidate.scene["choices"]
    assert candidate.scene["choices"][0]["lock"] == candidate.locks[0]["id"]


# fn: M02.F07.I02
def test_generate_encounter_fills_params_into_scene_text():
    """params 填充 scene_template 占位符：填充后场景文本无残留占位、含参数词面。"""
    template = _template_by_id("enc_fruit_grove")
    candidate = generate_encounter(
        template, _params_for(template), _first_admitted_seed(template, _params_for(template))
    )
    text = candidate.scene["text"]
    assert "{" not in text and "}" not in text, f"场景文本残留占位：{text}"
    assert "两界山下" in text and "青皮仙果" in text


# fn: M02.F07.I02
def test_generate_encounter_seed_drives_lock_count():
    """种子真驱动生成：不同种子 → 生成锁数可不同（生成带内种子定数）。"""
    template = _template_by_id("enc_lost_sutra")
    params = _params_for(template)
    counts = set()
    for seed in range(200):
        try:
            candidate = generate_encounter(template, params, seed)
        except EncounterRejectedError:
            continue
        counts.add(len(candidate.locks))
    assert len(counts) > 1, f"200 种子内生成锁数无变化：{sorted(counts)}"


# fn: M02.F07.I02
def test_generate_encounter_rejects_dangling_param():
    """引用悬空：params 缺 declared 键 → 场景文本残留 {占位} 即拒收并报因（v1 audit
    悬空占位同机制；世界面悬空由 T16 锁注册表自审兜底）。"""
    template = _template_by_id("enc_fruit_grove")
    params = _params_for(template)
    partial = dict(params)
    partial.pop(sorted(partial)[0])
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, partial, 1)
    assert "悬空" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_lock_count_over_max():
    """超锁上限：种子使生成锁数 > difficulty.locks_max → 拒收并报因。"""
    template = _template_by_id("enc_fruit_grove")
    params = _params_for(template)
    seed = _seed_rejected_with(template, params, "超锁上限")
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, params, seed)
    assert "超锁上限" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_attr_below_difficulty_min():
    """难度越界：attr 所需值 < difficulty.attr_min → 拒收并报因
    （构造模板变体：attr_min 抬到所需值之上；真模板不可变，变体不落盘）。"""
    template = _with_difficulty(
        _template_by_id("enc_fruit_grove"), attr_min=4
    )  # requires insight>=3 < 4
    params = _params_for(template)
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, params, 1)
    assert "难度越界" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_blank_denial():
    """空 denial：锁槽 denial 为空白 → 拒收并报因（玩家必须读得懂缺什么）。"""
    template = _with_lock_slot(_template_by_id("enc_fruit_grove"), 0, denial="   ")
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, _params_for(template), 1)
    assert "denial" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_missing_anchor():
    """缺锚：锁槽 id 为空 → 拒收并报因（真触发=锁槽 id 为空；_derive_anchor 恒产
    非空串，「锚派生为空」支已删——生成锁锚由生成器派生标注，不进 lock_anchors）。"""
    template = _with_lock_slot(_template_by_id("enc_fruit_grove"), 0, id="")
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, _params_for(template), 1)
    assert "锁槽 id 为空" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_params_must_be_dict():
    """fail-fast：params 非 dict → ValueError（str 会按字符静默拆散，报错须近根因）。"""
    template = _template_by_id("enc_fruit_grove")
    with pytest.raises(ValueError) as excinfo:
        generate_encounter(template, "两界山下", 1)
    assert "dict" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_empty_lock_slots():
    """入闸拒收：lock_slots 空 → EncounterRejectedError 报因「锁条件槽为空」
    （与 audit 同口径；修复前此处 ZeroDivisionError 崩）。"""
    template = replace(_template_by_id("enc_fruit_grove"), lock_slots=[])
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, _params_for(template), 1)
    assert "锁条件槽为空" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_difficulty_missing_locks_max():
    """难度缺键：difficulty 缺 locks_max → 拒收并报因
    （T15 审查裁定禁软兜底——缺难度规约不许静默放行）。"""
    template = replace(_template_by_id("enc_fruit_grove"), difficulty={"attr_min": 1})
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, _params_for(template), 1)
    assert "难度缺键" in str(excinfo.value) and "locks_max" in str(excinfo.value)


# fn: M02.F07.I02
def test_generate_encounter_rejects_difficulty_missing_attr_min():
    """难度缺键：difficulty 缺 attr_min → 拒收并报因
    （locks_max=4 顶满生成带，保证走到 attr 查而不被超锁上限先拦）。"""
    template = replace(_template_by_id("enc_fruit_grove"), difficulty={"locks_max": 4})
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, _params_for(template), 1)
    assert "难度缺键" in str(excinfo.value) and "attr_min" in str(excinfo.value)


# fn: M02.F07.I02
def test_admit_choice_effects_not_aliased_to_candidate_effects():
    """别名断言：admit_choice["effects"] 与 candidate.effects 必须是两个独立容器
    （is 判异；修复前共享同一 list，运行期改写其一回灌另一）。"""
    template = _template_by_id("enc_fruit_grove")
    params = _params_for(template)
    seed = _first_admitted_seed(template, params)
    candidate = generate_encounter(template, params, seed)
    choice_effects = candidate.scene["choices"][0]["effects"]
    assert choice_effects is not candidate.effects


_TEMPLATE_IDS = [t.id for t in load_encounter_templates(_REPO_DATA)]


@pytest.mark.parametrize("template_id", _TEMPLATE_IDS)
# fn: M02.F07.I02
def test_template_level_bidirectional_assertion(template_id):
    """模板级双向断言（spec §5.6 锚纪律裁定，数据驱动遍历 load_encounter_templates
    全量真模板——新模板入 data/encounter-templates/ 即自动纳入，不须改测试名单）：
    正向=有效参数+种子 → 生成+过滤通过；反向=构造的五类无效种子/参数/模板变体
    → 各自拒收并报因。真模板不可变：反向变体均经 replace 构造、不落盘。"""
    template = _template_by_id(template_id)
    params = _params_for(template)
    seed = _first_admitted_seed(template, params)

    # 正向：生成+过滤通过
    candidate = generate_encounter(template, params, seed)
    assert candidate.template_id == template_id
    assert 1 <= len(candidate.locks) <= template.difficulty["locks_max"]
    for lock in candidate.locks:
        assert lock["assertion_anchor"]["pass"] and lock["assertion_anchor"]["deny"]

    # 反向一：难度越界（attr 所需值 < 抬高后的 attr_min）
    harder = _with_difficulty(template, attr_min=template.difficulty["attr_min"] + 1)
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(harder, params, seed)
    assert "难度越界" in str(excinfo.value)

    # 反向二：引用悬空（params 缺 declared 键 → 占位残留）
    partial = dict(params)
    partial.pop(sorted(partial)[0])
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, partial, seed)
    assert "悬空" in str(excinfo.value)

    # 反向三：空 denial
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(_with_lock_slot(template, 0, denial="  "), params, seed)
    assert "denial" in str(excinfo.value)

    # 反向四：缺锚（锁槽 id 清空 → 锁槽 id 为空即拒收）
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(_with_lock_slot(template, 0, id=""), params, seed)
    assert "锁槽 id 为空" in str(excinfo.value)

    # 反向五：超锁上限（种子扫描出锁数超 locks_max 的无效种子）
    bad_seed = _seed_rejected_with(template, params, "超锁上限")
    with pytest.raises(EncounterRejectedError) as excinfo:
        generate_encounter(template, params, bad_seed)
    assert "超锁上限" in str(excinfo.value)
