"""Task 6：API 面——五端点 + 内存会话库 + APP_PORT fail-fast（TDD 先红后绿）。

用内存小章包构造 app（不依赖真实 data/，真实目录只有 game-start.json）。
形状真源 = spec §5.3。
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from text_rpg.chapters import Chapter, Choice, EndingDef, LockDef, Scene, World
from text_rpg.engine import GameEngine


def make_world() -> World:
    """两章小世界：s1 四抉择（空效/解锁/挂锁/触发结局）+ ch02 挂 entry_lock。"""
    ch01 = Chapter(
        id="ch01",
        title="第一章",
        locks=[
            LockDef(
                id="key_gate",
                requires=[{"flag": "has_key"}],
                denial="没有钥匙，门纹丝不动",
            )
        ],
        scenes=[
            Scene(
                id="s1",
                text="山门前",
                choices=[
                    Choice(id="look", text="打量山门"),
                    Choice(id="pray", text="拜求钥匙", effects=[{"flag": "has_key"}]),
                    Choice(
                        id="open",
                        text="推门",
                        lock="key_gate",
                        goto="s2",
                        effects=[{"flag": "door_opened"}],
                    ),
                    Choice(id="fall", text="折返下山", effects=[{"flag": "good_end"}]),
                ],
            ),
            Scene(
                id="s2",
                text="门内",
                choices=[
                    Choice(
                        id="west",
                        text="西行",
                        effects=[{"flag": "chapter_ch01_complete"}],
                    ),
                ],
            ),
        ],
        endings=[
            EndingDef(
                id="end_good",
                title="善终",
                requires=[{"flag": "good_end"}],
                mid_chapter=True,
            )
        ],
    )
    ch02 = Chapter(
        id="ch02",
        title="第二章",
        entry_locks=["entry_gate"],
        locks=[
            LockDef(
                id="entry_gate",
                requires=[{"item": "passport"}],
                denial="无路引，过不得边界",
            )
        ],
        scenes=[Scene(id="s3", text="边界", choices=[Choice(id="go", text="赶路")])],
        endings=[EndingDef(id="end_west", title="西去", requires=[{"flag": "arrived"}])],
    )
    return World(
        chapters=[ch01, ch02],
        start_attributes={"courage": 2},
        start_backpack=["dry_rations"],
    )


def make_client() -> tuple[TestClient, object]:
    """构造测试 app：内存 world + SessionStore，返回 (client, store)。"""
    from text_rpg.locks import build_registry
    from text_rpg.persistence import SessionStore
    from text_rpg.routes import build_router

    world = make_world()
    engine = GameEngine(world, build_registry(world))
    store = SessionStore()
    app = FastAPI()
    app.include_router(build_router(engine, store))
    return TestClient(app), store


def new_game(client: TestClient, player_name: str = "悟空") -> str:
    resp = client.post("/api/games", json={"player_name": player_name})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_health():
    client, _ = make_client()
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "mode": "local"}


def test_chapters_catalog_static():
    client, _ = make_client()
    resp = client.get("/api/chapters")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "chapters": [
            {"id": "ch01", "title": "第一章", "order": 1},
            {"id": "ch02", "title": "第二章", "order": 2},
        ]
    }
    for row in body["chapters"]:
        assert "locked" not in row  # 静态目录不带局上下文


def test_create_game_201_and_empty_name_400():
    client, _ = make_client()
    resp = client.post("/api/games", json={"player_name": "悟空"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"]
    state = body["state"]
    assert state["player_name"] == "悟空"
    assert state["flags"] == []  # set 序列化为 sorted list
    assert state["attributes"] == {"courage": 2}
    assert state["backpack"] == ["dry_rations"]
    assert state["current_chapter"] == "ch01"
    assert state["current_scene"] == "s1"
    assert state["game_over"] is False
    assert state["ending"] is None
    # 空 / 纯空白 / 缺失 → 400
    assert client.post("/api/games", json={"player_name": ""}).status_code == 400
    assert client.post("/api/games", json={"player_name": "   "}).status_code == 400
    assert client.post("/api/games", json={}).status_code == 400


def test_get_game_embeds_choices_endings_chapters_views():
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.get(f"/api/games/{game_id}")
    assert resp.status_code == 200
    body = resp.json()
    # state + scene + 三视图五件
    assert set(body) == {"state", "scene", "choices", "endings", "chapters"}
    assert body["state"]["current_scene"] == "s1"
    assert body["scene"] == {"id": "s1", "text": "山门前"}
    # choices_view：逐 choice 锁评估
    by_id = {c["id"]: c for c in body["choices"]}
    assert set(by_id) == {"look", "pray", "open", "fall"}
    assert by_id["look"]["locked"] is False
    assert by_id["open"]["locked"] is True
    assert by_id["open"]["missing"] == [
        {"type": "flag", "key": "has_key", "have": False, "need": True}
    ]
    assert by_id["open"]["denial"] == "没有钥匙，门纹丝不动"
    # endings_view：结局条件链摘要
    assert [e["id"] for e in body["endings"]] == ["end_good", "end_west"]
    assert all(e["satisfied"] is False for e in body["endings"])
    # chapters_view：章锁定态
    assert [c["id"] for c in body["chapters"]] == ["ch01", "ch02"]
    assert body["chapters"][0]["locked"] is False
    assert body["chapters"][1]["locked"] is True  # entry_gate 要 passport


def test_submit_choice_messages_state_unlocked():
    client, _ = make_client()
    game_id = new_game(client)
    # 挂锁抉择被拒：denial 进 messages，状态不变
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "open"})
    assert resp.status_code == 200
    body = resp.json()
    assert "没有钥匙，门纹丝不动" in body["messages"]
    assert body["state"]["current_scene"] == "s1"
    assert body["unlocked_locks"] == []
    assert body["game_over"] is False
    assert body["ending"] is None
    # 先 pray 写 has_key → 再 open：状态推进 + unlocked_locks 报本次推开的门
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "pray"})
    assert resp.status_code == 200
    assert resp.json()["unlocked_locks"] == ["key_gate"]
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "open"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"]["current_scene"] == "s2"
    assert "door_opened" in body["state"]["flags"]
    assert body["game_over"] is False


def test_unknown_game_404():
    client, _ = make_client()
    assert client.get("/api/games/no-such-id").status_code == 404
    resp = client.post("/api/games/no-such-id/choice", json={"scene_id": "s1", "choice_id": "look"})
    assert resp.status_code == 404


def test_unknown_scene_or_choice_400():
    client, _ = make_client()
    game_id = new_game(client)
    assert (
        client.post(
            f"/api/games/{game_id}/choice", json={"scene_id": "nope", "choice_id": "look"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "nope"}
        ).status_code
        == 400
    )


def test_choice_after_game_over_400():
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "fall"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_over"] is True
    assert body["ending"] == {"id": "end_good", "title": "善终"}
    # 终局后再提交 → 400
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "look"})
    assert resp.status_code == 400


def test_session_gone_after_store_reset():
    client, store = make_client()
    game_id = new_game(client)
    assert client.get(f"/api/games/{game_id}").status_code == 200
    store.delete_all()  # 模拟服务重启：内存会话清空
    resp = client.get(f"/api/games/{game_id}")
    assert resp.status_code == 404
    assert (
        client.post(
            f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "look"}
        ).status_code
        == 404
    )


def test_main_missing_app_port_raises(monkeypatch):
    from text_rpg import webserver

    # 双保险：清场 APP_PORT + uvicorn.run 空转（即使 env 泄漏也不会起真服）
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.setattr(webserver.uvicorn, "run", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="缺少环境变量 APP_PORT"):
        webserver.main()


def test_main_uses_app_port(monkeypatch):
    from text_rpg import webserver

    captured: dict = {}

    def fake_uvicorn_run(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setenv("APP_PORT", "8806")
    monkeypatch.setattr(webserver.uvicorn, "run", fake_uvicorn_run)
    webserver.main()
    assert captured["port"] == 8806
    assert captured["app"] is webserver.app


def test_startup_audit_gate_blocks_broken_world():
    """spec §5.1：启动自审 errors 非空 → 拒绝启动（RuntimeError 带错误明细）。"""
    from text_rpg import webserver
    from text_rpg.lock_anchors import ANCHORS
    from text_rpg.locks import build_registry

    # 坏世界（悬空锁引用）→ RuntimeError 点名锁 id
    broken = make_world()
    broken.chapters[0].scenes[0].choices[0].lock = "ghost_lock"
    with pytest.raises(RuntimeError, match="ghost_lock"):
        webserver._audit_gate(broken, build_registry(broken), {})

    # 干净世界 + 全覆盖锚 → 静默通过（不抛即过）
    clean = make_world()
    full = {k: {"pass": "p", "deny": "d"} for k in build_registry(clean)}
    webserver._audit_gate(clean, build_registry(clean), full)
    assert ANCHORS  # 真世界装配走同一道闸：真锚表非空


def test_get_game_scene_carries_real_ch01_prose():
    """终审修复：read_game 响应携带 scene={id,text}——场景正文直达前端（spec §5.4 场景文案）。

    用真仓 data/ 装配引擎：断言 scene.id = 起手场景，text = ch01 真实正文前缀。
    """
    from text_rpg.chapters import load_world
    from text_rpg.locks import build_registry
    from text_rpg.persistence import SessionStore
    from text_rpg.routes import build_router

    data_dir = Path(__file__).resolve().parents[1] / "data"
    world = load_world(data_dir)
    engine = GameEngine(world, build_registry(world))
    app = FastAPI()
    app.include_router(build_router(engine, SessionStore()))
    client = TestClient(app)
    game_id = new_game(client)
    resp = client.get(f"/api/games/{game_id}")
    assert resp.status_code == 200
    scene = resp.json()["scene"]
    assert scene["id"] == "s01_village"
    assert scene["text"].startswith("晨光初照，两界山遥遥在望")
