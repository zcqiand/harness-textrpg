"""Encounter template loader & audit (spec 5.6, data/encounter-templates/*.json).

Audit checks (same shape as opponents.audit_opponents):
1. quantity gate (total templates < 2) -> error
2. dangling placeholder in scene_template (not declared in params) -> error
3. blank denial in any lock slot -> error
4. empty slots: blank scene_template / empty lock_slots / empty effect_slots -> error
5. difficulty broken: missing key / non-int (bool rejected) / negative value -> error
6. blank word surface: name blank -> error
"""
# @impl M04.F03.I02
# @impl M02.F07.I01

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from text_rpg.chapters import _read_json
from text_rpg.locks import AuditReport

__all__ = [
    "EncounterTemplate",
    "audit_encounter_templates",
    "encounter_template_from_dict",
    "load_encounter_templates",
]


@dataclass
class EncounterTemplate:
    id: str
    name: str
    params: list[str]
    scene_template: str
    lock_slots: list[dict]
    effect_slots: list[dict]
    difficulty: dict[str, int]


def _params_list(params) -> list[str]:
    """params 非 list 早炸（str 会按字符静默拆散，报错须近根因）。"""
    if not isinstance(params, list):
        raise ValueError(f"params 必须是 list，得到 {type(params).__name__}")
    return [str(p) for p in params]


def _lock_slot(slot: dict) -> dict:
    """锁槽深一层复制；缺 requires 带模板槽位上下文（裸 KeyError 丢上下文）。"""
    if not isinstance(slot.get("requires"), list):
        raise KeyError(f"锁槽缺 requires 列表（slot={slot.get('id', '?')}）")
    return dict(slot, requires=[dict(r) for r in slot["requires"]])


def _effect_slot(eff: dict) -> dict:
    """效果槽含内层 delta dict 复制一层（注释宣称的隔离须真隔离）。"""
    copied = dict(eff)
    for key, value in eff.items():
        if isinstance(value, dict):
            copied[key] = dict(value)
    return copied


def encounter_template_from_dict(d: dict) -> EncounterTemplate:
    if not isinstance(d, dict):
        raise ValueError("奇遇模板契约必须是 dict")
    missing = [
        k
        for k in (
            "id",
            "name",
            "params",
            "scene_template",
            "lock_slots",
            "effect_slots",
            "difficulty",
        )
        if k not in d
    ]
    if missing:
        raise KeyError(f"奇遇模板契约缺必填字段：{missing}")
    return EncounterTemplate(
        id=str(d["id"]),
        name=str(d["name"]),
        params=_params_list(d["params"]),
        scene_template=str(d["scene_template"]),
        # 槽位列表逐行 dict 复制一层（v2 深拷贝教训对齐）：嵌套 dict 不复制会与
        # 调用方源 dict 共享引用，运行期改写回灌契约源。
        lock_slots=[_lock_slot(slot) for slot in d["lock_slots"]],
        effect_slots=[_effect_slot(eff) for eff in d["effect_slots"]],
        difficulty={str(k): int(v) for k, v in dict(d["difficulty"]).items()},
    )


def load_encounter_templates(data_dir: Path) -> list[EncounterTemplate]:
    templates_path = Path(data_dir) / "encounter-templates"
    if not templates_path.is_dir():
        raise FileNotFoundError(f"奇遇模板目录缺失：{templates_path}（fail-fast，禁静默返空集）")
    packs = sorted(templates_path.glob("*.json"), key=lambda p: p.name)
    if not packs:
        raise ValueError(f"奇遇模板目录空（零模板文件）：{templates_path}（奇遇功能面不得静默死）")
    return [encounter_template_from_dict(_read_json(p)) for p in packs]


def audit_encounter_templates(templates: list) -> AuditReport:
    errors = []
    warnings = []
    # 量口径入闸（M02.F07.I01 契约：奇遇模板总数 ≥2，spec §6 留书稿练习新增空间）：
    # 总数 <2 红。
    if len(templates) < 2:
        errors.append(f"奇遇模板总数不足：{len(templates)} < 2（M02.F07.I01：至少 2 个模板）")
    for t in templates:
        # 空白词面：name 空串/纯空白红。
        if not t.name.strip():
            errors.append(f"奇遇模板「{t.id}」name 为空串/纯空白词面（M02.F07.I01）")
        # 空槽位：场景文本模板空白红。
        if not t.scene_template.strip():
            errors.append(
                f"奇遇模板「{t.id}」scene_template 为空串/纯空白（场景骨架面不得为空）"
                f"（M02.F07.I01）"
            )
        # 悬空引用：场景文本模板 {param} 占位未在 params 声明 → 红。
        declared = set(t.params)
        used = set(re.findall(r"\{(\w+)\}", t.scene_template))
        dangling = sorted(used - declared)
        if dangling:
            errors.append(
                f"奇遇模板「{t.id}」scene_template 悬空占位 {dangling}（未在 params 声明）"
                f"（M02.F07.I01）"
            )
        # 空槽位：锁条件槽空红。
        if not isinstance(t.lock_slots, list) or not t.lock_slots:
            errors.append(f"奇遇模板「{t.id}」lock_slots 为空（锁条件槽不得为空）（M02.F07.I01）")
        else:
            for i, slot in enumerate(t.lock_slots):
                slot_id = slot.get("id") if isinstance(slot, dict) else None
                if not isinstance(slot_id, str) or not slot_id.strip():
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] id 为空串/纯空白词面（M02.F07.I01）"
                    )
                requires = slot.get("requires") if isinstance(slot, dict) else None
                if not isinstance(requires, list) or not requires:
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] requires 为空"
                        f"（锁条件面不得为空）（M02.F07.I01）"
                    )
                denial = slot.get("denial") if isinstance(slot, dict) else None
                if not isinstance(denial, str) or not denial.strip():
                    errors.append(
                        f"奇遇模板「{t.id}」lock_slots[{i}] denial 为空串/纯空白（空 denial 红）"
                        f"（M02.F07.I01）"
                    )
        # 空槽位：效果槽空红；行形状校验（v1 效果四类）。
        if not isinstance(t.effect_slots, list) or not t.effect_slots:
            errors.append(f"奇遇模板「{t.id}」effect_slots 为空（效果槽不得为空）（M02.F07.I01）")
        else:
            allowed = {"attr", "item_add", "item_remove", "flag"}
            for i, eff in enumerate(t.effect_slots):
                keys = set(eff) if isinstance(eff, dict) else set()
                if len(keys) != 1 or not keys <= allowed:
                    errors.append(
                        f"奇遇模板「{t.id}」effect_slots[{i}] 形状不符（须为 v1 效果四类单键）"
                        f"（M02.F07.I01）"
                    )
        # 难度规约：键缺失红；值非 int（bool 拒）/负数红。
        difficulty = t.difficulty
        for key in ("attr_min", "locks_max"):
            if key not in difficulty:
                errors.append(
                    f"奇遇模板「{t.id}」difficulty 缺键 {key}（难度规约键必须齐）（M02.F07.I01）"
                )
        for key, value in difficulty.items():
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(
                    f"奇遇模板「{t.id}」difficulty.{key} 须为非负 int，实得非 int 值（M02.F07.I01）"
                )
            elif value < 0:
                errors.append(
                    f"奇遇模板「{t.id}」difficulty.{key} 为负数（难度规约禁负值）（M02.F07.I01）"
                )
    return AuditReport(errors=errors, warnings=warnings)
