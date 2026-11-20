"""章回包数据模型与加载器。

章回包 = game-start.json（开局属性/背包）+ chapters/*.json（按文件名序）。
条件（requires）与效果（effects）在本层保持原始 dict，
由 contracts.evaluate / contracts.apply 原样消费。
"""
# @impl M02.F03.I01
# @impl M04.F01.I01
# @impl M04.F01.I02

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["Chapter", "Choice", "EndingDef", "LockDef", "Scene", "World", "load_world"]


@dataclass
class Choice:
    id: str
    text: str
    lock: str | None = None
    goto: str | None = None
    effects: list[dict] = field(default_factory=list)


@dataclass
class Scene:
    id: str
    text: str
    choices: list[Choice] = field(default_factory=list)


@dataclass
class LockDef:
    id: str
    requires: list[dict]
    denial: str
    effects: list[dict] = field(default_factory=list)
    chapter_id: str = ""


@dataclass
class EndingDef:
    id: str
    title: str
    requires: list[dict]
    mid_chapter: bool = False


@dataclass
class Chapter:
    id: str
    title: str
    entry_locks: list[str] = field(default_factory=list)
    locks: list[LockDef] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    endings: list[EndingDef] = field(default_factory=list)


@dataclass
class World:
    chapters: list[Chapter]
    start_attributes: dict[str, int]
    start_backpack: list[str]


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"数据文件缺失：{path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败：{path}：{exc}") from exc


def load_world(data_dir: Path) -> World:
    """读 game-start.json + chapters/*.json（按文件名序），映射为 World dataclass。

    目录整体缺失 → FileNotFoundError（信息点名 game-start.json）；
    目录在但 game-start.json 缺失 → 视为空开局（{} / []），chapters 照常加载。
    """
    if not data_dir.is_dir():
        raise FileNotFoundError(f"数据目录缺失：{data_dir}（找不到 game-start.json）")
    start_path = data_dir / "game-start.json"
    start = _read_json(start_path) if start_path.exists() else {}
    chapters_dir = data_dir / "chapters"
    packs = (
        sorted(chapters_dir.glob("*.json"), key=lambda p: p.name) if chapters_dir.is_dir() else []
    )
    chapters = [_load_chapter(p) for p in packs]
    return World(
        chapters=chapters,
        start_attributes=dict(start.get("attributes", {})),
        start_backpack=list(start.get("backpack", [])),
    )


def _load_chapter(path: Path) -> Chapter:
    pack = _read_json(path)
    chapter_id = pack["id"]
    locks = [
        LockDef(
            id=lk["id"],
            requires=list(lk["requires"]),
            denial=lk["denial"],
            effects=list(lk.get("effects", [])),
            chapter_id=chapter_id,
        )
        for lk in pack.get("locks", [])
    ]
    scenes = [
        Scene(
            id=sc["id"],
            text=sc["text"],
            choices=[
                Choice(
                    id=c["id"],
                    text=c["text"],
                    lock=c.get("lock"),
                    goto=c.get("goto"),
                    effects=list(c.get("effects", [])),
                )
                for c in sc.get("choices", [])
            ],
        )
        for sc in pack.get("scenes", [])
    ]
    endings = [
        EndingDef(
            id=e["id"],
            title=e["title"],
            requires=list(e["requires"]),
            mid_chapter=bool(e.get("mid_chapter", False)),
        )
        for e in pack.get("endings", [])
    ]
    return Chapter(
        id=chapter_id,
        title=pack["title"],
        entry_locks=list(pack.get("entry_locks", [])),
        locks=locks,
        scenes=scenes,
        endings=endings,
    )
