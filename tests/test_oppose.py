"""T11 M02.F06.I02：对抗结算（choice 内嵌 oppose，TDD 先红后绿）。

spec §5.5：策略对手结算——玩家力量（属性+旗标加权）vs 对手策略表行动，种子化掷点
定胜负，账本每步 {seq, actor, action, power, roll}；效果面同 v1 effects 四类。
接线语义（裁定）：对手结算内嵌 POST /choice——锁放行后，若抉择声明 oppose →
追加对抗结算，账本随抉择响应返回（oppose_ledger 键）；不声明 → 无此键。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from text_rpg.chapters import Chapter, Choice, EndingDef, LockDef, Scene, World
from text_rpg.engine import GameEngine, GameState
from text_rpg.llm import MockLLMClient
from text_rpg.locks import build_registry
from text_rpg.memory import MemoryStore
from text_rpg.opponents import opponent_from_dict
from text_rpg.oppose import apply_oppose_effects, derive_player_power, settle
from text_rpg.persistence import SessionStore
from text_rpg.routes import build_router

_LEDGER_KEYS = {"seq", "actor", "action", "power", "roll"}


def make_opponent() -> object:
    """契约合法的最小对手卡（审计同形）：条件行 + default 行。"""
    return opponent_from_dict(
        {
            "id": "opp_test_spirit",
            "name": "测试小妖",
            "chapter": "ch01",
            "base": {"deception": 3, "insight": 2},
            "strategy_table": [
                {"when": {"player_flag": "evidence"}, "action": "weep", "power": 1},
                {"when": {"default": True}, "action": "disguise", "power": 3},
            ],
        }
    )


# fn: M02.F06.I02
def test_settle_ledger_shape_and_numbering():
    """种子化掷点结算：账本两条、seq 从 1 递增、每步 {seq,actor,action,power,roll} 齐。"""
    opp = make_opponent()
    outcome = settle(opp, 5, "seed-a", player_flags=set())
    ledger = outcome["ledger"]
    assert isinstance(ledger, list) and len(ledger) == 2
    assert [row["seq"] for row in ledger] == [1, 2]
    for row in ledger:
        assert set(row) == _LEDGER_KEYS
        assert isinstance(row["power"], int) and isinstance(row["roll"], int)
    first = ledger[0]
    assert first["actor"] == "player"
    assert first["action"] == "oppose"
    assert first["power"] == 5
    assert 1 <= first["roll"] <= 6
    second = ledger[1]
    assert second["actor"] == "opp_test_spirit"
    # 对手 power = 策略行 power + base 属性和（3+2=5）→ default 行 3+5=8
    assert second["power"] == 8
    assert 1 <= second["roll"] <= 6
    assert outcome["winner"] in ("player", "opp_test_spirit")


# fn: M02.F06.I02
def test_strategy_table_conditional_row_hit_and_default_fallback():
    """策略表分支：player_flag 命中条件行取该行 action；不命中走 default 行。"""
    opp = make_opponent()
    hit = settle(opp, 5, "seed-a", player_flags={"evidence"})
    assert hit["ledger"][1]["action"] == "weep"
    assert hit["ledger"][1]["power"] == 1 + 5  # 条件行 power 1 + base 和 5
    miss = settle(opp, 5, "seed-a", player_flags=set())
    assert miss["ledger"][1]["action"] == "disguise"
    assert miss["ledger"][1]["power"] == 3 + 5  # default 行 power 3 + base 和 5


# fn: M02.F06.I02
def test_settle_same_seed_same_inputs_replay_identical():
    """重放地基（T12 验收锚前置）：同种子+同入参 → 账本逐字段全等。"""
    opp = make_opponent()
    a = settle(opp, 5, "seed-x", player_flags={"evidence"})
    b = settle(opp, 5, "seed-x", player_flags={"evidence"})
    assert a["ledger"] == b["ledger"] and a["winner"] == b["winner"]


# fn: M02.F06.I02
def test_effects_win_writes_flag_via_v1_effects():
    """效果落地（胜）：走 v1 flag 效果——写攻克旗 defeated_<opp_id>。"""
    opp = make_opponent()
    win_seed = next(
        s for s in (f"s{i}" for i in range(200)) if settle(opp, 9, s)["winner"] == "player"
    )
    from text_rpg.engine import GameState

    state = GameState(player_name="悟空", attributes={"courage": 2})
    messages = apply_oppose_effects(opp, winner="player", state=state)
    assert messages and all(isinstance(m, str) for m in messages)
    assert f"标记：defeated_{opp.id}" in messages  # contracts flag 效果固定产出（建议 1 锚）
    assert f"defeated_{opp.id}" in state.flags


# fn: M02.F06.I02
def test_effects_lose_applies_attr_via_v1_effects():
    """效果落地（负）：走 v1 attr 效果——属性减量真实落地。"""
    opp = make_opponent()
    lose_seed = next(
        s for s in (f"s{i}" for i in range(200)) if settle(opp, 1, s)["winner"] == "opp_test_spirit"
    )
    outcome = settle(opp, 1, lose_seed)
    from text_rpg.engine import GameState

    state = GameState(player_name="悟空", attributes={"insight": 3})
    messages = apply_oppose_effects(opp, outcome["winner"], state)
    assert messages
    assert state.attributes["insight"] == 2  # -1 落地（受挫失洞察，起始实存键）


# fn: M02.F06.I02
def test_choice_embeds_oppose_ledger():
    """接线：锁放行后抉择声明 oppose → 响应含 oppose_ledger（两条、seq 1..2）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "fight", "oppose": "opp_test_spirit"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "oppose_ledger" in body
    ledger = body["oppose_ledger"]
    assert [row["seq"] for row in ledger] == [1, 2]
    assert ledger[0]["actor"] == "player"
    assert ledger[1]["actor"] == "opp_test_spirit"
    assert ledger[0]["power"] == 1  # 服务端派生力量（阻断 1）：属性和 1 + 0 旗标
    # 实体效果消息锚（建议 1）：contracts 属性效果固定产出「属性变化：{delta}」——
    # 本夹具玩家力量 1 < 对手 8+掷点恒负，结算消息必为减属性，不是恒真死断言。
    assert any("属性变化" in m for m in body["messages"])


# fn: M02.F06.I02
def test_choice_without_oppose_has_no_ledger_key():
    """不声明 oppose → 响应无 oppose_ledger 键（键不存在，非空列表）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "fight"}
    )
    assert resp.status_code == 200
    assert "oppose_ledger" not in resp.json()


# fn: M02.F06.I02
def test_choice_oppose_unknown_opponent_is_400():
    """未知对手 id → 400（中文短语锚）。"""
    client, _ = _make_client()
    game_id = engine_view_guard(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "fight", "oppose": "opp_ghost"},
    )
    assert resp.status_code == 400
    assert "对手不存在" in resp.json()["detail"]


# fn: M02.F06.I02
def test_choice_oppose_unknown_opponent_is_400():
    """未知对手 id → 400（中文短语锚）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "fight", "oppose": "opp_ghost"},
    )
    assert resp.status_code == 400
    assert "对手不存在" in resp.json()["detail"]


# fn: M02.F06.I02
def test_unknown_opponent_400_leaves_state_unadvanced():
    """审查阻断 2 顺序钉：未知对手 400 是引擎前置预检——400 后 GET 局面，
    状态零推进（场景未迁移、未终局）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "fight", "oppose": "opp_ghost"},
    )
    assert resp.status_code == 400
    view = client.get(f"/api/games/{game_id}")
    assert view.status_code == 200
    state = view.json()["state"]
    assert state["current_scene"] == "s1"  # 场景未迁移
    assert state["game_over"] is False


# fn: M02.F06.I02
def test_power_derived_server_side_attrs_plus_flag_weight():
    """审查阻断 1 钉：力量=服务端派生（属性和 + 每旗标 +1），客户端无覆盖通道
    （ChoiceBody 无 power 字段）。"""
    state = GameState(player_name="悟空", attributes={"courage": 2, "insight": 1})
    assert derive_player_power(state) == 3  # 纯属性和
    state.flags.update({"evidence", "peak_reached"})
    assert derive_player_power(state) == 5  # 每旗标 +1 加权


# fn: M02.F06.I02
def test_choice_oppose_skipped_when_ending_triggers():
    """审查阻断 4：终局触发抉择带 oppose → 不追加对抗结算——响应无 oppose_ledger
    键且无结算消息（无属性变化）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "summit", "oppose": "opp_test_spirit"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["game_over"] is True  # 终局确已触发
    assert "oppose_ledger" not in body
    assert all("属性变化" not in m for m in body["messages"])  # 无结算效果消息


# fn: M02.F06.I02
def test_choice_oppose_skipped_when_lock_denies():
    """锁未放行（denial 分支）→ 对手结算不追加（无 oppose_ledger 键）。"""
    client, _ = _make_client()
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/choice",
        json={"scene_id": "s1", "choice_id": "flee", "oppose": "opp_test_spirit"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "oppose_ledger" not in body
    assert body["messages"] == ["此路不通"]


def _make_client() -> tuple[TestClient, object]:
    """内存小世界 + 显式对手卡装配 app（不依赖真实 data/）。"""
    world = World(
        chapters=[
            Chapter(
                id="ch01",
                title="第一章",
                locks=[
                    # 挂锁抉择：锁不放行 → denial 分支
                    LockDef(id="road_gate", requires=[{"flag": "pass_token"}], denial="此路不通")
                ],
                scenes=[
                    Scene(
                        id="s1",
                        text="山道",
                        choices=[
                            Choice(id="fight", text="迎战"),
                            Choice(id="flee", text="绕行", lock="road_gate"),
                            # 终局触发抉择（阻断 4 夹具）：写终局旗 → ending 判定命中
                            Choice(
                                id="summit",
                                text="登顶",
                                effects=[{"flag": "peak_reached"}],
                            ),
                        ],
                    )
                ],
                endings=[
                    EndingDef(
                        id="end_summit", title="登顶结局", requires=[{"flag": "peak_reached"}]
                    )
                ],
            )
        ],
        start_attributes={"insight": 1},  # 镜像 data/game-start.json（负面效果锚实存键）
        start_backpack=[],
    )
    engine = GameEngine(world, build_registry(world))
    app = FastAPI()
    app.include_router(
        build_router(
            engine,
            SessionStore(),
            npcs=[],
            llm_client=MockLLMClient(),
            memory=MemoryStore([]),
            llm_mode="mock",
            opponents=[make_opponent()],
        )
    )
    return TestClient(app), None


def _new_game(client: TestClient) -> str:
    resp = client.post("/api/games", json={"player_name": "悟空"})
    assert resp.status_code == 201
    return resp.json()["id"]
