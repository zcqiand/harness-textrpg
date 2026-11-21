"""Opponent contract loader & startup audit (spec 5.5, data/opponents/*.json).

Audit checks (errors block startup, same shape as npcs.audit_npcs):
1. quantity gate (total opponents < 3, or any world chapter with zero
   mounted opponent by contract chapter field) -> error
2. dangling chapter ref (chapter id not in world chapters) -> error
3. empty strategy_table -> error
4. strategy_table missing default row (when.default is True) -> error
5. blank word surface: name blank / strategy row action blank -> error
"""
# @impl M02.F06.I01

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from text_rpg.chapters import World, _read_json
from text_rpg.locks import AuditReport

__all__ = ["OpponentDef", "audit_opponents", "load_opponents", "opponent_from_dict"]


@dataclass
class OpponentDef:
    id: str
    name: str
    chapter: str
    base: dict[str, int]
    strategy_table: list[dict]


def opponent_from_dict(d: dict) -> OpponentDef:
    if not isinstance(d, dict):
        raise ValueError("对手卡契约必须是 dict")
    missing = [k for k in ("id", "name", "chapter", "base", "strategy_table") if k not in d]
    if missing:
        raise KeyError(f"对手卡契约缺必填字段：{missing}")
    return OpponentDef(
        id=str(d["id"]),
        name=str(d["name"]),
        chapter=str(d["chapter"]),
        base={str(k): int(v) for k, v in dict(d["base"]).items()},
        strategy_table=[
            # 行内 when dict 复制一层（v2 深拷贝教训对齐）：嵌套 dict 不复制会与
            # 调用方源 dict 共享引用，运行期改写回灌契约源。
            dict(row, when=dict(row["when"])) if isinstance(row.get("when"), dict) else dict(row)
            for row in d["strategy_table"]
        ],
    )


def load_opponents(data_dir: Path) -> list[OpponentDef]:
    opponents_path = Path(data_dir) / "opponents"
    if not opponents_path.is_dir():
        raise FileNotFoundError(f"对手卡契约目录缺失：{opponents_path}（fail-fast，禁静默返空集）")
    packs = sorted(opponents_path.glob("*.json"), key=lambda p: p.name)
    if not packs:
        raise ValueError(
            f"对手卡契约目录为空（零契约文件）：{opponents_path}（对手卡功能面不得静默死）"
        )
    return [opponent_from_dict(_read_json(p)) for p in packs]


def audit_opponents(opponents: list, world: World) -> AuditReport:
    errors = []
    warnings = []
    chapter_ids = {c.id for c in world.chapters}
    # 量口径入闸（M02.F06.I01 契约：≥3 张对手卡，每回 ≥1）：
    # 总数 <3 红；world 章清单任一章名下零挂载（按契约 chapter 字段统计）红。
    if len(opponents) < 3:
        errors.append(f"对手卡总数不足：{len(opponents)} < 3（M02.F06.I01：至少 3 张对手卡）")
    mounted_chapters = {o.chapter for o in opponents}
    for chapter in world.chapters:
        if chapter.id not in mounted_chapters:
            errors.append(f"章 {chapter.id} 无挂载对手卡（M02.F06.I01：每回 ≥1 张对手卡）")
    for o in opponents:
        if o.chapter not in chapter_ids:
            errors.append(f"对手卡「{o.id}」悬空 chapter 引用：{o.chapter}（M02.F06.I01）")
        # base 逐项校验（T11 结算消费面，npcs 同族逐项形状）：
        # 空 dict 红（结算无属性可依）；值非 int 红（bool 是 int 子类，一并拒）。
        if not isinstance(o.base, dict) or not o.base:
            errors.append(f"对手卡「{o.id}」base 为空属性映射（结算属性面不得为空）（M02.F06.I01）")
        elif any(isinstance(v, bool) or not isinstance(v, int) for v in o.base.values()):
            errors.append(
                f"对手卡「{o.id}」base 属性值必须为 int（T11 结算消费面，实含非 int 值）"
                f"（M02.F06.I01）"
            )
        table = o.strategy_table
        if not isinstance(table, list) or not table:
            errors.append(
                f"对手卡「{o.id}」strategy_table 为空（行动规约面不得为空）（M02.F06.I01）"
            )
            continue
        if not any(
            isinstance(row, dict)
            and isinstance(row.get("when"), dict)
            and row["when"].get("default") is True
            for row in table
        ):
            errors.append(
                f"对手卡「{o.id}」strategy_table 缺 default 行"
                f"（when.default is True 兜底行必填）（M02.F06.I01）"
            )
        for i, row in enumerate(table):
            action = row.get("action") if isinstance(row, dict) else None
            if not isinstance(action, str) or not action.strip():
                errors.append(
                    f"对手卡「{o.id}」strategy_table[{i}] action 为空串/纯空白词面（M02.F06.I01）"
                )
        if not o.name.strip():
            errors.append(f"对手卡「{o.id}」name 为空串/纯空白词面（M02.F06.I01）")
    return AuditReport(errors=errors, warnings=warnings)
