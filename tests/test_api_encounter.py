"""T16（M02.F07.I03）奇遇准入通道——API 面 TDD 先红后绿。

形状真源 = v2/v3 design spec §5.6 准入通道架构裁定：
- POST /api/games/{id}/encounters：种子服务端从局状态派生（客户端传种子即 400）；
  生成 → 无效过滤（EncounterRejectedError → 400 报因）→ 过锁注册表自审
  （生成锁并入临时注册表跑 v1 audit 三查：悬空/空 denial/锚）→ 作临时场景
  并入当前章（内存态，不落盘，不迁移玩家）。
- GET /api/games/{id}/scenes/{sid}：并入后的临时场景 GET 局面可见。
- 装配面：encounters / lock_anchors 显式传参（None fail-fast，oppose T11 先例）；
  webserver 启动闸并账 audit_encounter_templates（T10 同形）。
- 同局重复准入同种子 → 全等（重放钉，spec §5.6 语义硬约束同 oppose）。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from text_rpg.chapters import load_world
from text_rpg.encounters import load_encounter_templates
from text_rpg.engine import GameEngine
from text_rpg.llm import MockLLMClient
from text_rpg.locks import build_registry
from text_rpg.memory import MemoryStore
from text_rpg.persistence import SessionStore
from text_rpg.routes import build_router

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _real_app(encounters: list | None = None):
    """真仓 data/ 装配 app：真章包 + 真模板 + 真 NPC + 真锁锚表（准入通道正路夹具）。

    返回 (client, engine, store)：engine 供幂等面/撞车面注册表直查（建议②，
    黑盒响应照不进引擎内存态），store 供终局构造（game_over 守卫 miss 用例）。"""
    from text_rpg.lock_anchors import ANCHORS
    from text_rpg.npcs import load_npcs

    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    npcs = load_npcs(data_dir=_DATA_DIR)
    store = SessionStore()
    app = FastAPI()
    app.include_router(
        build_router(
            engine,
            store,
            npcs=npcs,
            llm_client=MockLLMClient(),
            memory=MemoryStore(npcs),
            llm_mode="mock",
            opponents=[],  # 显式空对手注册表（build_router 禁 None 兜底，T11 先例）
            encounters=(load_encounter_templates(_DATA_DIR) if encounters is None else encounters),
            lock_anchors=ANCHORS,
        )
    )
    return TestClient(app), engine, store


def _real_client(encounters: list | None = None) -> TestClient:
    return _real_app(encounters)[0]


def _new_game(client: TestClient) -> str:
    resp = client.post("/api/games", json={"player_name": "悟空"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _bad_template():
    """坏模板变体（replace 构造，不落盘）：首个锁槽 denial 清成空白。"""
    template = load_encounter_templates(_DATA_DIR)[0]
    slots = [dict(s) for s in template.lock_slots]
    slots[0] = dict(slots[0], denial="   ")
    return replace(template, lock_slots=slots)


# fn: M02.F07.I03
def test_admit_encounter_200_temp_scene_merged_and_visible():
    """准入 200：生成过审后临时场景并入当前章，GET 局面可见；玩家不迁移。"""
    client = _real_client()
    game_id = _new_game(client)
    resp = client.post(f"/api/games/{game_id}/encounters", json={"template_id": "enc_fruit_grove"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["template_id"] == "enc_fruit_grove"
    assert body["name"] == "野果林止渴"
    scene_id = body["scene_id"]
    assert scene_id == "enc_fruit_grove_enc"
    # 场景面：v1 Scene 形状（id/text/npc_ids/choices），抉择挂首把生成锁
    assert set(body["scene"]) >= {"id", "text", "npc_ids", "choices"}
    assert body["scene"]["npc_ids"] == []
    assert body["lock_ids"], "生成锁清单不得为空"
    assert body["scene"]["choices"][0]["lock"] == body["lock_ids"][0]
    for lock in body["locks"]:
        assert lock["denial"].strip(), "生成锁 denial 不得空白"
    assert body["effects"], "效果槽不得为空"
    # GET 局面可见：临时场景经读场景端点可见，抉择带锁评估行
    got = client.get(f"/api/games/{game_id}/scenes/{scene_id}")
    assert got.status_code == 200
    view = got.json()
    assert view["scene"]["id"] == scene_id
    assert "果" in view["scene"]["text"]
    rows = view["choices"]
    assert rows and set(rows[0]) >= {"id", "text", "locked", "missing", "denial"}
    # 锁语义值断言（T16 审查建议⑤）：新局 insight=1 < 3 且无完成旗 → 首把生成锁
    # （patience 槽，requires insight>=3）必未满足 → locked=True 且 denial 文本透出
    assert rows[0]["locked"] is True
    assert rows[0]["missing"], "未满足行须透出 missing 清单"
    assert rows[0]["denial"] is not None and "果林禁令" in rows[0]["denial"]
    # 准入不迁移玩家：当前场景原位（临时场景只在章清单，不夺局）
    state = client.get(f"/api/games/{game_id}").json()["state"]
    assert state["current_scene"] == "s01_village"


# fn: M02.F07.I03
def test_admit_unknown_game_404():
    client = _real_client()
    assert (
        client.post(
            "/api/games/no-such-id/encounters", json={"template_id": "enc_fruit_grove"}
        ).status_code
        == 404
    )


# fn: M02.F07.I03
def test_admit_rejects_client_seed_400():
    """硬约束：种子服务端从局状态派生，客户端传种子即 400（禁收）。"""
    client = _real_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/encounters",
        json={"template_id": "enc_fruit_grove", "seed": "hacker-seed"},
    )
    assert resp.status_code == 400
    assert "种子" in resp.json()["detail"]


# fn: M02.F07.I03
def test_admit_unknown_template_400():
    client = _real_client()
    game_id = _new_game(client)
    resp = client.post(f"/api/games/{game_id}/encounters", json={"template_id": "ghost_enc"})
    assert resp.status_code == 400
    assert "ghost_enc" in resp.json()["detail"]


# fn: M02.F07.I03
def test_admit_invalid_template_variant_400_reports_reason():
    """无效模板变体 → 400 报因：坏模板经 replace 构造注入装配面（不落盘）。"""
    templates = load_encounter_templates(_DATA_DIR)
    client = _real_client(encounters=[_bad_template(), templates[1]])
    game_id = _new_game(client)
    resp = client.post(f"/api/games/{game_id}/encounters", json={"template_id": "enc_fruit_grove"})
    assert resp.status_code == 400
    assert "denial" in resp.json()["detail"]


# fn: M02.F07.I03
def test_admit_same_game_replay_identical():
    """重放钉：同局重复准入（同局状态 → 同派生种子）→ 响应全等；幂等分支引擎
    直查（T16 审查建议②）：章场景清单/场景索引/锁注册表两次准入后零增长。"""
    client, engine, _store = _real_app()
    game_id = _new_game(client)
    payload = {"template_id": "enc_fruit_grove"}
    first = client.post(f"/api/games/{game_id}/encounters", json=payload)
    assert first.status_code == 200
    chapter = next(c for c in engine.world.chapters if c.id == "ch01")
    scenes_after_first = len(chapter.scenes)
    scenes_index_after_first = len(engine._scenes)
    registry_after_first = len(engine.registry)
    second = client.post(f"/api/games/{game_id}/encounters", json=payload)
    assert second.status_code == 200
    assert first.json() == second.json()
    # 幂等可观测（引擎直查，非仅响应面）：重复准入不重挂场景/不重登记锁
    assert len(chapter.scenes) == scenes_after_first
    assert len(engine._scenes) == scenes_index_after_first
    assert len(engine.registry) == registry_after_first
    scene_id = first.json()["scene_id"]
    got_a = client.get(f"/api/games/{game_id}/scenes/{scene_id}")
    got_b = client.get(f"/api/games/{game_id}/scenes/{scene_id}")
    assert got_a.json() == got_b.json()


# fn: M02.F07.I03
def test_admit_collision_with_registered_scene_400():
    """异源撞车 400（T16 审查阻断）：场景 id 撞车但候选内容已变（局状态漂移 →
    参数面重填 → 生成物非已登记版）→ 准入拒绝报因带 id，禁静默留旧版还回 200
    （旧形状：200+scene_id 但玩家读不到本候选场景）。"""
    client, engine, store = _real_app()
    game_id = _new_game(client)
    payload = {"template_id": "enc_fruit_grove"}
    first = client.post(f"/api/games/{game_id}/encounters", json=payload)
    assert first.status_code == 200
    scene_id = first.json()["scene_id"]
    registered_text = engine._scenes[scene_id].text
    # 局状态漂移（玩家移步别景）：参数面 {place}/{fruit} 重填为另一场景 id 词面，
    # 同模板同 scene_id 再生成 → 生成物内容 ≠ 已登记版 → 撞车。
    state = store.get(game_id)
    state.current_scene = "s01_woodcutter_hut"
    store.put(game_id, state)
    resp = client.post(f"/api/games/{game_id}/encounters", json=payload)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "撞车" in detail
    assert scene_id in detail, "报因必须带撞车场景 id"
    # 已登记版原样保留：撞车候选零写入（章清单与场景索引都不被污染）
    assert engine._scenes[scene_id].text == registered_text
    got = client.get(f"/api/games/{game_id}/scenes/{scene_id}")
    assert got.json()["scene"]["text"] == registered_text


# fn: M02.F07.I03
def test_admit_game_over_400():
    """终局守卫（T16 审查建议③，oppose 终局跳过先例同语义）：游戏已结束后
    准入通道拒绝并入奇遇场景——终局局不得再长出新的可读场景面。"""
    client, _engine, store = _real_app()
    game_id = _new_game(client)
    state = store.get(game_id)
    state.game_over = True
    state.ending = {"id": "turned_back", "title": "回头是岸"}
    store.put(game_id, state)
    resp = client.post(f"/api/games/{game_id}/encounters", json={"template_id": "enc_fruit_grove"})
    assert resp.status_code == 400
    assert "已结束" in resp.json()["detail"]


# fn: M02.F07.I03
def test_read_unknown_scene_404():
    client = _real_client()
    game_id = _new_game(client)
    assert client.get(f"/api/games/{game_id}/scenes/nope").status_code == 404


# fn: M02.F07.I03
def test_build_router_encounters_and_anchors_fail_fast():
    """装配面 fail-fast（oppose T11 先例同形）：encounters / lock_anchors 缺失拒装配。"""
    from text_rpg.lock_anchors import ANCHORS

    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    templates = load_encounter_templates(_DATA_DIR)
    common = dict(
        store=SessionStore(),
        npcs=[],
        llm_client=MockLLMClient(),
        memory=MemoryStore([]),
        llm_mode="mock",
        opponents=[],
    )
    with pytest.raises(ValueError, match="encounters"):
        build_router(engine, lock_anchors=ANCHORS, **common)
    with pytest.raises(ValueError, match="lock_anchors"):
        build_router(engine, encounters=templates, **common)


# fn: M02.F07.I03
def test_webserver_audit_gate_accounts_encounter_templates():
    """webserver 启动闸并账（T10 同形）：坏模板 errors 并入同一闸拒绝启动。"""
    from text_rpg import webserver
    from text_rpg.lock_anchors import ANCHORS

    world = load_world(_DATA_DIR)
    registry = build_registry(world)
    templates = load_encounter_templates(_DATA_DIR)
    # 真模板干净 → 闸静默通过（不抛即过）
    webserver._audit_gate(world, registry, ANCHORS, encounters=templates)
    # 坏模板（空 denial）→ RuntimeError 点名报因
    with pytest.raises(RuntimeError, match="denial"):
        webserver._audit_gate(world, registry, ANCHORS, encounters=[_bad_template()])
