"""锁注册表与启动自审。

注册表 = 各章包 locks 的并集（key=lock id）。
启动自审三查：
1. 悬空 choice.lock 引用 → error（含锁 id 与「悬空」）
2. 空 denial（denial.strip() == ""）→ error
3. 缺锚（lock_id not in anchors）→ error

errors 非空 → 拒绝启动；warnings 仅记录，不拦启动。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from text_rpg.chapters import LockDef, World

__all__ = ["AuditReport", "audit", "build_registry"]


@dataclass
class AuditReport:
    """启动自审回执：errors 拦启动，warnings 仅记录。"""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def build_registry(world: World) -> dict[str, LockDef]:
    """各章包 locks 并集，key=lock id。重复 id 首章先登记。"""
    registry: dict[str, LockDef] = {}
    for chapter in world.chapters:
        for lk in chapter.locks:
            registry.setdefault(lk.id, lk)
    return registry


def _iter_choices(world: World):
    """收集全部 choice，附所属章与场景，供悬空引用检查。"""
    for chapter in world.chapters:
        for scene in chapter.scenes:
            for choice in scene.choices:
                yield chapter, scene, choice


def audit(world: World, registry: dict[str, LockDef], anchors: dict) -> AuditReport:
    """启动自审三查：悬空 / 空 denial / 缺锚。errors 非空即拒绝启动。"""
    errors: list[str] = []
    warnings: list[str] = []

    # 一查：悬空 choice.lock 引用
    for chapter, scene, choice in _iter_choices(world):
        if choice.lock is not None and choice.lock not in registry:
            errors.append(
                f"悬空锁引用：choice {chapter.id}/{scene.id}/{choice.id}"
                f" 引用未注册锁「{choice.lock}」"
            )

    # 二查：空 denial
    for lk in registry.values():
        if lk.denial.strip() == "":
            errors.append(f"锁「{lk.id}」denial 为空白（章 {lk.chapter_id}）")

    # 三查：缺锚（含锚条目缺 pass/deny 侧）
    for lock_id in registry:
        entry = anchors.get(lock_id)
        if entry is None:
            errors.append(f"锁「{lock_id}」缺测试锚：ANCHORS 无条目")
        else:
            for side in ("pass", "deny"):
                if side not in entry:
                    errors.append(f"锁「{lock_id}」缺测试锚：锚条目缺 {side} 侧")

    return AuditReport(errors=errors, warnings=warnings)
