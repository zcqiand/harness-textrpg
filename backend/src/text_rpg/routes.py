"""API 路由层：五端点，锁评估只在后端求值一次。

序列化器放本层（JSON 边界归路由，engine 保持传输无关——设计取舍记录在案）。
形状真源 = spec §5.3。错误形状：
- 未知 game id → 404（GET 与 POST choice 同形）
- 未知 scene_id / choice_id → 400（engine KeyError / ValueError 收敛）
- 终局后提交 → 400（engine ValueError「游戏已结束」）
"""
# @impl M01.F01.I01
# @impl M01.F01.I02
# @impl M01.F01.I03
# @impl M01.F01.I04
# @impl M01.F01.I05
# @impl M01.F01.I06

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from text_rpg.engine import GameEngine, GameState
from text_rpg.persistence import SessionStore

__all__ = ["build_router", "state_to_dict"]


class NewGameBody(BaseModel):
    player_name: str | None = None


class ChoiceBody(BaseModel):
    scene_id: str | None = None
    choice_id: str | None = None


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


def build_router(engine: GameEngine, store: SessionStore) -> APIRouter:
    def _scene_view(state: GameState) -> dict:
        """当前场景视图：{id, text}。text 从 world 章包取（spec §5.4 场景文案）。"""

        def _text() -> str:
            for chapter in engine.world.chapters:
                for scene in chapter.scenes:
                    if scene.id == state.current_scene:
                        return scene.text
            return ""  # 悬空 current_scene（理论不可达）：退空串，state 本体仍是真源

        return {"id": state.current_scene, "text": _text()}

    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict:
        return {"ok": True, "mode": "local"}

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
        try:
            result = engine.submit_choice(state, body.scene_id, body.choice_id)
        except KeyError:
            # 未知 scene_id（engine._scenes[...] 命中失败）
            raise HTTPException(status_code=400, detail=f"未知场景：{body.scene_id}") from None
        except ValueError as exc:
            # 未知 choice_id / 终局后提交（游戏已结束）
            raise HTTPException(status_code=400, detail=str(exc)) from None
        store.put(game_id, result.state)
        return {
            "messages": result.messages,
            "state": state_to_dict(result.state),
            "unlocked_locks": result.unlocked_locks,
            "game_over": result.game_over,
            "ending": result.ending,
        }

    return router
