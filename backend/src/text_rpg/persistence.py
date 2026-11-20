"""内存会话库：game id → GameState。

会话生命周期 = 服务进程生命周期（重启即清空，老 id 404）。
序列化边界在 routes 层，本层只管存取。
"""
# @impl M02.F04.I01

from __future__ import annotations

from uuid import uuid4

from text_rpg.engine import GameState

__all__ = ["SessionStore"]


class SessionStore:
    """dict[str, GameState] 薄封装：create 产 uuid id，get/put/delete_all。"""

    def __init__(self) -> None:
        self._games: dict[str, GameState] = {}

    def create(self, state: GameState) -> str:
        """登记新局，返回 uuid id。"""
        game_id = uuid4().hex
        self._games[game_id] = state
        return game_id

    def get(self, game_id: str) -> GameState | None:
        """读局；不存在返回 None。"""
        return self._games.get(game_id)

    def put(self, game_id: str, state: GameState) -> None:
        """覆盖写回（提交抉择后由 routes 调）。"""
        self._games[game_id] = state

    def delete_all(self) -> None:
        """清空全部会话（模拟重启）。"""
        self._games.clear()
