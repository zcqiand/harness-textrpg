"""NPC contract loader & startup audit (spec 5.2, data/npcs/*.json).

Audit checks (errors block startup, same shape as locks.audit):
1. dangling chapter ref (chapter id not in world chapters) -> error
2. empty red_lines -> error
3. empty outside -> error
4. memory_spec.event_tags not a mapping (tag -> trigger word list) -> error
5. event_tags vocab value not a str list / empty list -> error
"""
# @impl M02.F05.I01
# @impl M04.F02.I01

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from text_rpg.chapters import World, _read_json
from text_rpg.locks import AuditReport

__all__ = ["NpcDef", "audit_npcs", "load_npcs", "npc_from_dict"]


@dataclass
class NpcDef:
    id: str
    name: str
    chapter: str
    persona: str
    red_lines: list[str]
    outside: list[str]
    inside: list[str]
    memory_window: int
    memory_event_tags: dict[str, list[str]] = field(default_factory=dict)


def npc_from_dict(d: dict) -> NpcDef:
    dict_ok = isinstance(d, dict)
    if not dict_ok:
        raise ValueError("NPC 契约必须是 dict")
    missing = [
        k
        for k in (
            "id",
            "name",
            "chapter",
            "persona",
            "red_lines",
            "outside",
            "inside",
            "memory_spec",
        )
        if k not in d
    ]
    if missing:
        raise KeyError(f"NPC 契约缺必填字段：{missing}")
    spec = d["memory_spec"]
    window = int(spec["window"])
    tags = spec["event_tags"]  # 契约词表映射（tag → 触发词表），形状由 audit 校验
    return NpcDef(
        id=str(d["id"]),
        name=str(d["name"]),
        chapter=str(d["chapter"]),
        persona=str(d["persona"]),
        red_lines=[str(w) for w in d["red_lines"]],
        outside=[str(w) for w in d["outside"]],
        inside=[str(w) for w in d["inside"]],
        memory_window=window,
        memory_event_tags=tags,
    )


def load_npcs(data_dir: Path) -> list[NpcDef]:
    npcs_path = Path(data_dir) / "npcs"
    if not npcs_path.is_dir():
        return []
    packs = sorted(npcs_path.glob("*.json"), key=lambda p: p.name)
    return [npc_from_dict(_read_json(p)) for p in packs]


def audit_npcs(npcs: list, world: World) -> AuditReport:
    errors = []
    warnings = []
    chapter_ids = {c.id for c in world.chapters}
    for n in npcs:
        if n.chapter not in chapter_ids:
            errors.append(f"NPC「{n.id}」悬空 chapter 引用：{n.chapter}")
        if not n.red_lines:
            errors.append(f"NPC「{n.id}」red_lines 为空（前置红线拦截面不得为空）")
        if not n.outside:
            errors.append(f"NPC「{n.id}」outside 为空（知识边界黑名单不得为空）")
        if not isinstance(n.memory_window, int) or n.memory_window <= 0:
            errors.append(f"NPC「{n.id}」memory_window 必须为正整数，实为 {n.memory_window!r}")
        tags = n.memory_event_tags
        if not isinstance(tags, dict):
            errors.append(
                f"NPC「{n.id}」event_tags 必须是映射（tag → 触发词表），实为 {type(tags).__name__}"
            )
        elif not tags:
            errors.append(f"NPC「{n.id}」event_tags 词表映射为空（至少声明一个事件标签）")
        else:
            for tag, words in tags.items():
                if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
                    errors.append(f"NPC「{n.id}」event_tags「{tag}」词表必须是 str 列表")
                elif any(not w.strip() for w in words):
                    errors.append(f"NPC「{n.id}」event_tags「{tag}」词表含空串/纯空白触发词")
                elif not words:
                    errors.append(
                        f"NPC「{n.id}」event_tags「{tag}」词表为空表（至少声明一个触发词）"
                    )
    return AuditReport(errors=errors, warnings=warnings)
