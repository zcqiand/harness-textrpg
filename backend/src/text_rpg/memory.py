"""NPC 对话记忆存取：per-(game_id, npc_id) 内存记忆库（spec §5.3）。

同 v1 SessionStore——进程生命周期即生命周期，零持久化零新依赖。
条目形状 {turn, player_text, npc_text, event_tags}；事件标签判定=契约声明
词表命中即打标（词表是业务数据，出自 data/npcs/*.json 的 memory_spec 映射，
禁止硬编码进 Python）。打标条目永久参与 prompt（记仇钩子），普通条目
只保留最近 window 条。
"""
# @impl M02.F05.I02

from __future__ import annotations

from text_rpg.npcs import NpcDef

__all__ = ["MemoryStore"]


def _copy(entry: dict) -> dict:
    """条目深拷贝（条目只两层）：dict 与 event_tags 内层 list 都拷出，
    调用方原地改返回值不得扰动库内记仇钩子。"""
    return dict(entry, event_tags=list(entry["event_tags"]))


class MemoryStore:
    """(game_id, npc_id) → list[entry] 薄封装；词表与窗口出自 NPC 契约。"""

    def __init__(self, npcs: list[NpcDef]) -> None:
        self._specs: dict[str, NpcDef] = {n.id: n for n in npcs}
        self._logs: dict[tuple[str, str], list[dict]] = {}

    def _vocab(self, npc_id: str) -> dict[str, list[str]]:
        npc = self._specs.get(npc_id)
        tags = npc.memory_event_tags if npc is not None else {}
        return tags if isinstance(tags, dict) else {}

    def record(self, game_id: str, npc_id: str, player_text: str, npc_text: str) -> dict:
        """落账一条对话并返回条目拷贝；轮次号 1 起单调递增，只有本方法推进轮次
        （被拦输入不调 record 即不计轮次）。按契约词表给 player_text 或
        npc_text 打标：命中任意触发词即打该标，可多标。
        未知 npc_id fail-fast（MemoryStore 持有 NPC 契约，契约外 NPC 不许
        攒孤儿账），抛 ValueError 点名 npc_id。"""
        if npc_id not in self._specs:
            raise ValueError(f"未知 NPC「{npc_id}」：契约外 NPC 不许攒孤儿账")
        vocab = self._vocab(npc_id)
        tags = [
            tag
            for tag, words in vocab.items()
            if any(w in player_text or w in npc_text for w in words)
        ]
        log = self._logs.setdefault((game_id, npc_id), [])
        entry = {
            "turn": len(log) + 1,
            "player_text": player_text,
            "npc_text": npc_text,
            "event_tags": tags,
        }
        log.append(entry)
        return _copy(entry)

    def entries(self, game_id: str, npc_id: str) -> list[dict]:
        """原始全量清单（GET memory 端点用）；空/未知键返回空列表不报错。
        返回深拷贝，调用方改返回值不扰动库内条目。"""
        return [_copy(e) for e in self._logs.get((game_id, npc_id), [])]

    def prompt_entries(self, game_id: str, npc_id: str) -> list[dict]:
        """进 LLM prompt 的记忆面：窗口内条目 + 仍有效的打标条目
        （去重、按轮次序）。空/未知键返回空列表不报错。
        返回深拷贝，调用方改返回值不扰动库内条目。"""
        npc = self._specs.get(npc_id)
        log = self._logs.get((game_id, npc_id), [])
        if npc is None or not log:
            return []
        window = npc.memory_window
        merged: dict[int, dict] = {e["turn"]: e for e in log[-window:] if window > 0}
        for e in log:
            if e["event_tags"]:
                merged.setdefault(e["turn"], e)
        return [_copy(merged[t]) for t in sorted(merged)]
