"""API 路由层：v1 五端点 + v2 NPC 对话端点，锁评估只在后端求值一次。

序列化器放本层（JSON 边界归路由，engine 保持传输无关——设计取舍记录在案）。
形状真源 = v1 spec §5.3 + v2/v3 design spec §5.4。错误形状：
- 未知 game id → 404（GET 与 POST choice/talk 同形）
- 未知 scene_id / choice_id / npc_id → 400/404（engine KeyError / ValueError 收敛）
- 终局后提交 → 400（engine ValueError「游戏已结束」）
- NPC 端点：空输入 400、NPC 不在当前场景 400（对话入口来自场景数据）
"""
# @impl M01.F01.I01
# @impl M01.F01.I02
# @impl M01.F01.I03
# @impl M01.F01.I04
# @impl M01.F01.I05
# @impl M01.F01.I06
# @impl M01.F02.I01
# @impl M01.F02.I02
# @impl M01.F02.I03

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from text_rpg.chapters import Scene
from text_rpg.engine import GameEngine, GameState
from text_rpg.guardrails import VERDICT_BLOCKED, Guardrails, LLMClient
from text_rpg.memory import MemoryStore
from text_rpg.npcs import NpcDef
from text_rpg.opponents import OpponentDef
from text_rpg.oppose import apply_oppose_effects, derive_player_power, settle
from text_rpg.persistence import SessionStore

__all__ = ["build_router", "state_to_dict"]


class NewGameBody(BaseModel):
    player_name: str | None = None


class ChoiceBody(BaseModel):
    scene_id: str | None = None
    choice_id: str | None = None
    oppose: str | None = None
    # 无 power 字段（T11 审查阻断 1）：力量由服务端从局状态派生
    # （oppose.derive_player_power），客户端无覆盖通道。


class TalkBody(BaseModel):
    text: str | None = None


def state_to_dict(state: GameState) -> dict:
    """GameState → JSON 安全 dict：flags set → sorted list。"""
    return {
        "player_name": state.player_name,
        "flags": sorted(state.flags),
        "attributes": dict(state.attributes),
        "backpack": list(state.backpack),
        "current_chapter": state.current_chapter,
        "current_scene": state.current_scene,
        "game_over": state.game_over,
        "ending": state.ending,
    }


def _oppose_seed(state: GameState, opponent_id: str) -> str:
    """结算种子服务端从局状态派生（客户端不传种子）：对手 id + 章景 + 属性 + 旗标。
    同局状态 → 同种子 → 账本重放全等（spec §5.5 语义硬约束）。"""
    attrs = sorted(state.attributes.items())
    flags = sorted(state.flags)
    return "|".join(
        (opponent_id, state.current_chapter, state.current_scene, repr(attrs), repr(flags))
    )


def build_router(
    engine: GameEngine,
    store: SessionStore,
    npcs: list[NpcDef],
    llm_client: LLMClient,
    memory: MemoryStore,
    llm_mode: str,
    opponents: list[OpponentDef] | None = None,
) -> APIRouter:
    """v2 装配面：NPC 契约 + LLM client + 记忆库 + LLM_MODE 显式传入（禁 env 兜底，
    create_app 读 env 一次经参数下发）。"""
    _npcs_by_id = {n.id: n for n in npcs}
    # npc_id → Guardrails（惰性构建，NPC 契约不可变）。并发面为单用户 demo 姿态，
    # 与 v1 SessionStore 同类假设（进程内单写者），不加锁。
    _guards: dict[str, Guardrails] = {}

    def _guard(npc_id: str) -> Guardrails:
        if npc_id not in _guards:
            _guards[npc_id] = Guardrails(_npcs_by_id[npc_id], llm_client, memory)
        return _guards[npc_id]

    # Opponent registry (M02.F06.I02): 显式传入，禁兜底（T11 审查阻断 3，v2 裁量
    # 先例）：opponents 未传即 fail-fast 拒装配——自仓惰性加载分支已删，数据目录
    # 单源=webserver._data_dir 形状（build_router 只认参数，不自寻 data/）。
    if opponents is None:
        raise ValueError("opponents 必须显式传入 build_router（禁自仓惰性加载兜底）")
    _opponents_by_id: dict[str, OpponentDef] = {o.id: o for o in opponents}

    def _opponent(opp_id: str) -> OpponentDef | None:
        return _opponents_by_id.get(opp_id)

    def _find_scene(scene_id: str) -> Scene | None:
        for chapter in engine.world.chapters:
            for scene in chapter.scenes:
                if scene.id == scene_id:
                    return scene
        return None

    def _scene_view(state: GameState) -> dict:
        """当前场景视图：{id, text, npcs}。npcs 由章包 npc_ids 经 _npcs_by_id 映射带名
        （主线裁定 2026-11-21：视图层升格 npcs:[{id,name}]，数据面 npc_ids 不动）。"""
        scene = _find_scene(state.current_scene)
        if scene is None:
            # 悬空 current_scene（理论不可达）：空视图保形状统一，前端不用判键
            return {"id": state.current_scene, "text": "", "npcs": []}
        return {
            "id": state.current_scene,
            "text": scene.text,
            "npcs": [{"id": npc_id, "name": _npcs_by_id[npc_id].name} for npc_id in scene.npc_ids],
        }

    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict:
        return {"ok": True, "mode": llm_mode}

    @router.get("/api/chapters")
    def chapters_catalog() -> dict:
        """静态目录：id/title/序，无局上下文，不携带 locked。"""
        return {
            "chapters": [
                {"id": c.id, "title": c.title, "order": i + 1}
                for i, c in enumerate(engine.world.chapters)
            ]
        }

    @router.post("/api/games", status_code=201)
    def create_game(body: NewGameBody) -> dict:
        name = (body.player_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="player_name 必填且不能为空白")
        state = engine.new_game(name)
        game_id = store.create(state)
        return {"id": game_id, "state": state_to_dict(state)}

    def _load_game(game_id: str) -> GameState:
        state = store.get(game_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"局不存在：{game_id}")
        return state

    @router.get("/api/games/{game_id}")
    def read_game(game_id: str) -> dict:
        state = _load_game(game_id)
        return {
            "state": state_to_dict(state),
            "scene": _scene_view(state),
            "choices": engine.choices_view(state),
            "endings": engine.endings_view(state),
            "chapters": engine.chapters_view(state),
        }

    @router.post("/api/games/{game_id}/choice")
    def submit_choice(game_id: str, body: ChoiceBody) -> dict:
        state = _load_game(game_id)
        if not body.scene_id or not body.choice_id:
            raise HTTPException(status_code=400, detail="scene_id 与 choice_id 必填")
        # 对手存在性预检（T11 审查阻断 2）：引擎动状态之前判定——未知对手 400 且
        # 局状态零推进（场景未迁移），预检后才许引擎 submit_choice。
        opponent = _opponent(body.oppose) if body.oppose else None
        if body.oppose and opponent is None:
            raise HTTPException(status_code=400, detail=f"对手不存在：{body.oppose}")
        try:
            result = engine.submit_choice(state, body.scene_id, body.choice_id)
        except KeyError:
            # 未知 scene_id（engine._scenes[...] 命中失败）
            raise HTTPException(status_code=400, detail=f"未知场景：{body.scene_id}") from None
        except ValueError as exc:
            # 未知 choice_id / 终局后提交（游戏已结束）
            raise HTTPException(status_code=400, detail=str(exc)) from None
        # 对抗结算（M02.F06.I02）：锁放行后（denial 分支不追加）、终局前才追加。
        # 注（T11 审查建议 2 知悉面）：locked 启发式以 body.scene_id==current_scene
        # 近似「本抉择作用于当前场景」，非当前场景的 choice_id 在此恒 False——引擎层
        # 跨场景校验是 v1 面，本分支不扩权。
        locked = False
        if body.scene_id == state.current_scene:
            row = next((r for r in engine.choices_view(state) if r["id"] == body.choice_id), None)
            locked = bool(row is not None and row["locked"])
        oppose_ledger = None
        if body.oppose and not locked and not result.game_over:
            player_power = derive_player_power(result.state)
            seed = _oppose_seed(result.state, body.oppose)
            outcome = settle(opponent, player_power, seed, player_flags=result.state.flags)
            result.messages.extend(apply_oppose_effects(opponent, outcome["winner"], result.state))
            oppose_ledger = outcome["ledger"]
        store.put(game_id, result.state)
        response = {
            "messages": result.messages,
            "state": state_to_dict(result.state),
            "unlocked_locks": result.unlocked_locks,
            "game_over": result.game_over,
            "ending": result.ending,
        }
        if oppose_ledger is not None:
            response["oppose_ledger"] = oppose_ledger
        return response

    @router.post("/api/games/{game_id}/npcs/{npc_id}/talk")
    def npc_talk(game_id: str, npc_id: str, body: TalkBody) -> dict:
        state = _load_game(game_id)
        npc = _npcs_by_id.get(npc_id)
        if npc is None:
            raise HTTPException(status_code=404, detail=f"NPC 不存在：{npc_id}")
        text = (body.text or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text 必填且不能为空白")
        scene = _find_scene(state.current_scene)
        if scene is None or npc_id not in scene.npc_ids:
            raise HTTPException(status_code=400, detail=f"NPC「{npc_id}」不在当前场景")
        result = _guard(npc_id).talk(game_id, text)
        return {
            "reply": result.output,
            "blocked": result.verdict == VERDICT_BLOCKED,
            "guard_evidence": list(result.matched),
            "memory_turn": result.memory_turn,
        }

    @router.get("/api/games/{game_id}/npcs/{npc_id}/memory")
    def npc_memory(game_id: str, npc_id: str) -> dict:
        _load_game(game_id)
        if npc_id not in _npcs_by_id:
            raise HTTPException(status_code=404, detail=f"NPC 不存在：{npc_id}")
        return {"entries": memory.entries(game_id, npc_id)}

    return router
