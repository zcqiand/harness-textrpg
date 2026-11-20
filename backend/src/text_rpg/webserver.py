"""uvicorn 入口：装配真世界（repo data/）成 FastAPI app + APP_PORT fail-fast。

数据目录 = 仓库根 data/（可编辑安装指向本仓 src，parents[3] 即仓库根）。
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from text_rpg.chapters import load_world
from text_rpg.engine import GameEngine
from text_rpg.lock_anchors import ANCHORS
from text_rpg.locks import audit, build_registry
from text_rpg.npcs import audit_npcs, load_npcs
from text_rpg.persistence import SessionStore
from text_rpg.routes import build_router

__all__ = ["app", "create_app", "main"]


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data"


def _audit_gate(world, registry, anchors, npcs=None) -> None:
    """启动自审闸：errors 非空 → 拒绝启动（spec §5.1）。

    NPC 契约审计与锁审计并账：NPC errors 并入同一闸（spec §5.2 挂进同一路径）。
    npcs=None 时跳过 NPC 面（v1 三参调用形状保持兼容）。
    """
    report = audit(world, registry, anchors)
    if npcs is not None:
        report.errors.extend(audit_npcs(npcs, world).errors)
    if report.errors:
        raise RuntimeError("启动自审未通过，拒绝启动：\n- " + "\n- ".join(report.errors))


def create_app() -> FastAPI:
    world = load_world(_data_dir())
    registry = build_registry(world)
    npcs = load_npcs(data_dir=_data_dir())
    _audit_gate(world, registry, ANCHORS, npcs)
    engine = GameEngine(world, registry)
    application = FastAPI(title="harness-textrpg")
    application.include_router(build_router(engine, SessionStore()))
    return application


app = create_app()


def main() -> None:
    port_raw = os.environ.get("APP_PORT")
    if port_raw is None:
        raise RuntimeError("缺少环境变量 APP_PORT")
    # uvicorn 0.54 Windows proactor accept 崩溃指纹：显式 SelectorEventLoop（Linux 无感）。
    uvicorn.run(app, host="127.0.0.1", port=int(port_raw), loop="asyncio:SelectorEventLoop")
