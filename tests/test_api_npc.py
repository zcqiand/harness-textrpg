"""Task 6：NPC 对话路由——talk/memory 端点 + 场景挂 NPC + 错误形状收敛（TDD 先红后绿）。

形状真源 = v2/v3 design spec §5.4。错误形状与 v1 I06 收敛同形：
未知 game 404 / 未知 npc 404 / 空输入 400 / NPC 不在当前场景 400。
被拦输入不消耗记忆轮次（T4 护栏语义在此锚 API 面）；护栏判定只在后端求值一次。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from text_rpg.chapters import Chapter, Choice, EndingDef, Scene, World, load_world
from text_rpg.engine import GameEngine
from text_rpg.llm import MockLLMClient
from text_rpg.locks import build_registry
from text_rpg.memory import MemoryStore
from text_rpg.npcs import NpcDef, audit_npcs, load_npcs
from text_rpg.persistence import SessionStore
from text_rpg.routes import build_router

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class CountingStub:
    """duck-type .generate 计数 stub：断言被拦轮零 LLM 调用（零网络）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_text: str) -> str:
        self.calls.append((system_prompt, user_text))
        return "……"


def make_npc(**overrides: object) -> NpcDef:
    """测试用最小 NPC 契约（tmp 构造，不改 data/ 真件）。"""
    values: dict = {
        "id": "npc_w",
        "name": "樵夫",
        "chapter": "ch01",
        "persona": "两界山下的樵夫，肯给西行路人指路。",
        "red_lines": ["自称神明"],
        "outside": ["手机"],
        "inside": ["两界山"],
        "memory_window": 10,
        "memory_event_tags": {"insulted": ["骂"]},
    }
    values.update(overrides)
    return NpcDef(**values)  # type: ignore[arg-type]


def make_world() -> World:
    """单章小世界：s1 挂 npc_w（有西行抉择去 s2），s2 无 NPC。"""
    ch01 = Chapter(
        id="ch01",
        title="第一章",
        scenes=[
            Scene(
                id="s1",
                text="山门前",
                npc_ids=["npc_w"],
                choices=[
                    Choice(id="west", text="西行", goto="s2"),
                    Choice(id="end_run", text="折返东归", effects=[{"flag": "end_now"}]),
                ],
            ),
            Scene(id="s2", text="山门后", choices=[]),
        ],
        endings=[EndingDef(id="end_now", title="东归", requires=[{"flag": "end_now"}])],
    )
    return World(chapters=[ch01], start_attributes={}, start_backpack=[])


def make_client(
    npc: NpcDef | None = None, llm_client: object | None = None, llm_mode: str = "mock"
) -> tuple[TestClient, MemoryStore]:
    """内存小世界 + 注入面装配 app（不依赖真实 data/）。"""
    world = make_world()
    engine = GameEngine(world, build_registry(world))
    npcs = [npc or make_npc()]
    memory = MemoryStore(npcs)
    llm = llm_client if llm_client is not None else MockLLMClient()
    app = FastAPI()
    app.include_router(
        build_router(
            engine,
            SessionStore(),
            npcs=npcs,
            llm_client=llm,  # type: ignore[arg-type]
            memory=memory,
            llm_mode=llm_mode,
        )
    )
    return TestClient(app), memory


def new_game(client: TestClient) -> str:
    resp = client.post("/api/games", json={"player_name": "悟空"})
    assert resp.status_code == 201
    return resp.json()["id"]


def make_real_client() -> tuple[TestClient, MemoryStore]:
    """真仓 data/ 装配 app：验证三章回包真实 npcs 视图面到 API。"""
    world = load_world(_DATA_DIR)
    engine = GameEngine(world, build_registry(world))
    npcs = load_npcs(data_dir=_DATA_DIR)
    memory = MemoryStore(npcs)
    app = FastAPI()
    app.include_router(
        build_router(
            engine,
            SessionStore(),
            npcs=npcs,
            llm_client=MockLLMClient(),
            memory=memory,
            llm_mode="mock",
        )
    )
    return TestClient(app), memory


# =========================================================== M01.F02.I01 场景挂 NPC


# fn: M01.F02.I01
def test_read_game_scene_carries_npcs():
    """读局响应的当前场景视图带出 npcs:[{id,name}]（视图层带名，数据面 npc_ids 不动）。"""
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.get(f"/api/games/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["scene"] == {
        "id": "s1",
        "text": "山门前",
        "npcs": [{"id": "npc_w", "name": "樵夫"}],
    }


# fn: M01.F02.I01
def test_scene_view_npcs_empty_when_no_npc_mounted():
    """未挂 NPC 的场景 npcs 为空表（形状统一，前端不用判键）。"""
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "west"})
    assert resp.status_code == 200
    assert resp.json()["state"]["current_scene"] == "s2"
    assert client.get(f"/api/games/{game_id}").json()["scene"]["npcs"] == []


# fn: M01.F02.I01
def test_chapter_packs_declare_npc_ids_exact():
    """三章回包数据驱动实证：npc_ids 精确断言（json.load 回验，非内存视图）。

    叙事锚定：樵夫在村口指路与茅舍奉茶两处登场；白骨老妪在第二变哭寻女儿；
    铁扇公主在芭蕉洞门前现身。
    """
    packs = {
        "ch01": json.loads((_DATA_DIR / "chapters" / "ch01-two-boundary.json").read_text("utf-8")),
        "ch02": json.loads((_DATA_DIR / "chapters" / "ch02-white-bone.json").read_text("utf-8")),
        "ch03": json.loads(
            (_DATA_DIR / "chapters" / "ch03-flaming-mountain.json").read_text("utf-8")
        ),
    }
    mounted = {
        pack_id: {sc["id"]: sc.get("npc_ids", []) for sc in pack["scenes"] if sc.get("npc_ids")}
        for pack_id, pack in packs.items()
    }
    assert mounted == {
        "ch01": {"s01_village": ["npc_woodcutter"], "s01_woodcutter_hut": ["npc_woodcutter"]},
        "ch02": {"s02_second_meet": ["npc_bone_elder"]},
        "ch03": {"s03_cave_door": ["npc_fan_princess"]},
    }
    # 每章 ≥1 个场景挂本章 NPC
    npc_chapters = {
        json.loads(p.read_text("utf-8"))["id"]: json.loads(p.read_text("utf-8"))["chapter"]
        for p in (_DATA_DIR / "npcs").glob("*.json")
    }
    for pack_id, scenes in mounted.items():
        assert scenes, f"{pack_id} 无场景挂 NPC"
        for refs in scenes.values():
            for ref in refs:
                assert npc_chapters.get(ref) == pack_id  # 挂的本章 NPC，不跨章


# fn: M01.F02.I01
def test_real_world_start_scene_view_carries_npcs():
    """真仓 data/ 装配：起手场景 s01_village 的 npcs 直达读局响应（视图层带名）。"""
    client, _ = make_real_client()
    game_id = new_game(client)
    resp = client.get(f"/api/games/{game_id}")
    assert resp.status_code == 200
    scene = resp.json()["scene"]
    assert scene["id"] == "s01_village"
    assert scene["npcs"] == [{"id": "npc_woodcutter", "name": "樵夫"}]


# fn: M01.F02.I01
def test_audit_scene_dangling_npc_ids():
    """启动自审补场景侧悬空 npc_ids 查：引用不存在的 NPC id → error 点名（T1 悬空 chapter 同族）。"""
    world = make_world()
    world.chapters[0].scenes[1].npc_ids = ["ghost_npc"]  # s2 本无 NPC，注入悬空引用
    report = audit_npcs([make_npc()], world)
    assert any("ghost_npc" in e for e in report.errors)
    # 干净世界 + 合法契约（量口径达标：3 契约且每章有挂载）→ 静默通过
    clean = [
        make_npc(id="npc_w", chapter="ch01"),
        make_npc(id="npc_2", chapter="ch01"),
        make_npc(id="npc_3", chapter="ch01"),
    ]
    assert audit_npcs(clean, make_world()).errors == []


# fn: M01.F02.I01
def test_health_mode_reflects_llm_mode():
    """/api/health 的 mode 值随 LLM_MODE 反映（spec §6 人裁："mock"/"live"）。"""
    client, _ = make_client(llm_mode="live")
    assert client.get("/api/health").json() == {"ok": True, "mode": "live"}


# =========================================================== M01.F02.I01 talk 端点


# fn: M01.F02.I01
def test_talk_full_chain_reply_and_memory():
    """talk 全链：guard 放行 → client 生成 → memory 落账；memory_turn 从 1 起。"""
    llm = MockLLMClient(reply_table={"两界山": "此山正是两界山，西去便出大唐地界。"})
    client, memory = make_client(llm_client=llm)
    game_id = new_game(client)
    resp = client.post(f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": "此处可是两界山？"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"reply", "blocked", "guard_evidence", "memory_turn"}
    assert body["reply"] == "此山正是两界山，西去便出大唐地界。"
    assert body["blocked"] is False
    assert body["guard_evidence"] == []
    assert body["memory_turn"] == 1
    # 对话纯层：记忆已落账但游戏状态不被写（flags 不动）
    assert client.get(f"/api/games/{game_id}").json()["state"]["flags"] == []


# fn: M01.F02.I01
def test_talk_blocked_returns_matched_and_skips_memory():
    """blocked=true 带红线明细（GuardResult.matched）；零 LLM 调用；不消耗记忆轮次。"""
    llm = CountingStub()
    client, memory = make_client(llm_client=llm)
    game_id = new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": "你自称神明，方能渡我"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["blocked"] is True
    assert body["guard_evidence"] == ["自称神明"]
    assert body["memory_turn"] is None
    assert "此话不可说" in body["reply"]  # 错误消息子串断言锚中文短语
    assert llm.calls == []  # 前置拦截零 LLM 调用
    # 被拦输入不消耗记忆轮次：记忆库仍为空
    assert client.get(f"/api/games/{game_id}/npcs/npc_w/memory").json() == {"entries": []}


# fn: M01.F02.I01
def test_talk_second_turn_advances_memory_turn():
    """连续放行轮次单调递增（memory_turn 2）；记忆清单按轮次序。"""
    client, memory = make_client()
    game_id = new_game(client)
    for i in range(2):
        resp = client.post(f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": f"问路{i}"})
        assert resp.status_code == 200
    assert resp.json()["memory_turn"] == 2
    body = client.get(f"/api/games/{game_id}/npcs/npc_w/memory").json()
    assert [e["turn"] for e in body["entries"]] == [1, 2]


# =========================================================== M01.F02.I02 memory 端点


# fn: M01.F02.I02
def test_memory_endpoint_returns_entries():
    """GET memory 返回 entries() 清单：条目形状 {turn, player_text, npc_text, event_tags}。"""
    client, _ = make_client(llm_client=MockLLMClient(reply_table={"两界山": "正是两界山。"}))
    game_id = new_game(client)
    client.post(f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": "此处可是两界山？"})
    resp = client.get(f"/api/games/{game_id}/npcs/npc_w/memory")
    assert resp.status_code == 200
    assert resp.json() == {
        "entries": [
            {
                "turn": 1,
                "player_text": "此处可是两界山？",
                "npc_text": "正是两界山。",
                "event_tags": [],
            }
        ]
    }


# fn: M01.F02.I02
def test_memory_empty_before_any_talk():
    """未对话时 memory 清单为空表（不报错，形状统一）。"""
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.get(f"/api/games/{game_id}/npcs/npc_w/memory")
    assert resp.status_code == 200
    assert resp.json() == {"entries": []}


# =========================================================== M01.F02.I03 错误形状收敛


# fn: M01.F02.I03
def test_talk_unknown_game_404():
    client, _ = make_client()
    resp = client.post("/api/games/no-such-id/npcs/npc_w/talk", json={"text": "问路"})
    assert resp.status_code == 404


# fn: M01.F02.I03
def test_memory_unknown_game_404():
    client, _ = make_client()
    assert client.get("/api/games/no-such-id/npcs/npc_w/memory").status_code == 404


# fn: M01.F02.I03
def test_talk_and_memory_unknown_npc_404():
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.post(f"/api/games/{game_id}/npcs/npc_ghost/talk", json={"text": "问路"})
    assert resp.status_code == 404
    assert "npc_ghost" in resp.json()["detail"]
    assert client.get(f"/api/games/{game_id}/npcs/npc_ghost/memory").status_code == 404


# fn: M01.F02.I03
def test_talk_empty_text_400():
    """空输入 400：空串 / 纯空白 / 缺键同形（v1 player_name 收敛同款）。"""
    client, _ = make_client()
    game_id = new_game(client)
    url = f"/api/games/{game_id}/npcs/npc_w/talk"
    assert client.post(url, json={"text": ""}).status_code == 400
    assert client.post(url, json={"text": "   "}).status_code == 400
    assert client.post(url, json={}).status_code == 400


# fn: M01.F02.I03
def test_talk_npc_not_in_current_scene_400():
    """NPC 不在当前场景 400（对话入口来自场景数据——离开 s1 后樵夫不在场）。"""
    client, _ = make_client()
    game_id = new_game(client)
    resp = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "west"})
    assert resp.status_code == 200
    resp = client.post(f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": "问路"})
    assert resp.status_code == 400
    assert "不在当前场景" in resp.json()["detail"]


# fn: M01.F02.I01
def test_audit_scene_npc_ids_bad_shape():
    """npc_ids 畸形形状（str 非 str 列表）→ audit error 点名场景 id。"""
    world = make_world()
    world.chapters[0].scenes[0].npc_ids = "npc_w"  # 畸形：字符串非列表
    report = audit_npcs([make_npc()], world)
    assert any("形状不符" in e and "s1" in e for e in report.errors)


# fn: M01.F02.I01
def test_audit_scene_cross_chapter_mount():
    """NPC 挂进非本契约章的场景 → audit error 点名场景+npc+两章号。"""
    world = make_world()
    ch02 = Chapter(
        id="ch02",
        title="第二章",
        scenes=[Scene(id="s9", text="别章地界", npc_ids=["npc_w"])],
    )
    world.chapters.append(ch02)
    report = audit_npcs([make_npc()], world)  # npc_w 契约章 = ch01
    assert any(
        "跨章挂载" in e and "s9" in e and "npc_w" in e and "ch01" in e and "ch02" in e
        for e in report.errors
    )


# fn: M01.F02.I01
def test_talk_allowed_after_game_over():
    """终局后 talk 放行——钉行为：对话纯层不写游戏状态故不拦（依据 spec §5.3），防误修。"""
    client, memory = make_client()
    game_id = new_game(client)
    r = client.post(f"/api/games/{game_id}/choice", json={"scene_id": "s1", "choice_id": "end_run"})
    assert r.json()["game_over"] is True
    resp = client.post(f"/api/games/{game_id}/npcs/npc_w/talk", json={"text": "别来无恙"})
    assert resp.status_code == 200
    assert resp.json()["blocked"] is False
    assert resp.json()["memory_turn"] == 1


# fn: M01.F02.I02
def test_memory_isolated_across_games():
    """跨局隔离：局 A 对话后局 B 的 memory 仍空、互不可见。"""
    client, memory = make_client()
    ga = new_game(client)
    gb = new_game(client)
    r = client.post(f"/api/games/{ga}/npcs/npc_w/talk", json={"text": "问路"})
    assert r.status_code == 200
    assert client.get(f"/api/games/{gb}/npcs/npc_w/memory").json() == {"entries": []}
    entries = client.get(f"/api/games/{ga}/npcs/npc_w/memory").json()["entries"]
    assert entries[0]["player_text"] == "问路"
