"""游戏引擎状态机：门控 → 效果 → goto → 章推进 → 结局判定。

引擎持有世界（章回包）与锁注册表；状态是每局数据，由调用方持有
（后续持久化任务按 game id 存取 GameState）。

约定：
- 章完成旗：``chapter_<章id>_complete``（如 ch01 → ``chapter_ch01_complete``），
  抉择 effects 写入该旗即视为本章完成，引擎尝试推进到下一章。
- 推进前提：下一章 ``entry_locks`` 全部满足；不满足则停在原章，
  并把受阻 entry lock 的 denial 追加进消息。
- 结局判定：每次 submit_choice 效果执行后，按章声明序（world.chapters 顺序）
  拼接全部结局，第一条 requires 满足的即 game_over。
- unlocked_locks：注册表中「提交前未满足、效果执行后满足」的锁 id
  （即本次抉择推开的门），按注册表登记序返回。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from text_rpg.chapters import Chapter, Choice, LockDef, Scene, World
from text_rpg.contracts import apply as apply_effects
from text_rpg.contracts import evaluate

__all__ = ["ChoiceResult", "GameEngine", "GameState"]


@dataclass
class GameState:
    player_name: str
    flags: set = field(default_factory=set)
    attributes: dict = field(default_factory=dict)
    backpack: list = field(default_factory=list)
    current_chapter: str = ""
    current_scene: str = ""
    game_over: bool = False
    ending: dict | None = None


@dataclass
class ChoiceResult:
    messages: list[str]
    state: GameState
    unlocked_locks: list[str]
    game_over: bool
    ending: dict | None


class GameEngine:
    """状态机本体。world+registry 归引擎，state 归调用方。"""

    def __init__(self, world: World, registry: dict[str, LockDef]):
        self.world = world
        self.registry = registry
        self._scenes: dict[str, Scene] = {}
        self._chapters: dict[str, Chapter] = {}
        for chapter in world.chapters:
            self._chapters[chapter.id] = chapter
            for scene in chapter.scenes:
                self._scenes[scene.id] = scene

    # ---------- 开局 ----------

    def new_game(self, player_name: str) -> GameState:
        first = self.world.chapters[0]
        return GameState(
            player_name=player_name,
            flags=set(),
            attributes=dict(self.world.start_attributes),
            backpack=list(self.world.start_backpack),
            current_chapter=first.id,
            current_scene=first.scenes[0].id,
        )

    # ---------- 视图 ----------

    def choices_view(self, state: GameState) -> list[dict]:
        """当前场景的抉择视图：{id,text,locked,missing,denial}。"""
        scene = self._scenes[state.current_scene]
        rows: list[dict] = []
        for c in scene.choices:
            if c.lock is None:
                rows.append(
                    {"id": c.id, "text": c.text, "locked": False, "missing": [], "denial": None}
                )
                continue
            result = evaluate(self.registry[c.lock].requires, state)
            rows.append(
                {
                    "id": c.id,
                    "text": c.text,
                    "locked": not result.satisfied,
                    "missing": result.missing,
                    "denial": self.registry[c.lock].denial if not result.satisfied else None,
                }
            )
        return rows

    def endings_view(self, state: GameState) -> list[dict]:
        """全部结局按章声明序拼接：{id,title,satisfied,missing}。"""
        rows: list[dict] = []
        for chapter in self.world.chapters:
            for e in chapter.endings:
                result = evaluate(e.requires, state)
                rows.append(
                    {
                        "id": e.id,
                        "title": e.title,
                        "satisfied": result.satisfied,
                        "missing": result.missing,
                    }
                )
        return rows

    def chapters_view(self, state: GameState) -> list[dict]:
        """章列表视图：{id,title,locked}。locked = 存在未满足的 entry_lock。"""
        return [
            {
                "id": chapter.id,
                "title": chapter.title,
                "locked": any(
                    not evaluate(self.registry[lock_id].requires, state).satisfied
                    for lock_id in chapter.entry_locks
                ),
            }
            for chapter in self.world.chapters
        ]

    # ---------- 抉择提交 ----------

    def submit_choice(self, state: GameState, scene_id: str, choice_id: str) -> ChoiceResult:
        if state.game_over:
            raise ValueError("游戏已结束")
        scene = self._scenes[scene_id]
        choice = self._find_choice(scene, choice_id)

        # 一、门控：挂锁且条件不满足 → 拒绝，状态不变
        lock = self.registry[choice.lock] if choice.lock is not None else None
        if lock is not None and not evaluate(lock.requires, state).satisfied:
            return ChoiceResult(
                messages=[lock.denial],
                state=state,
                unlocked_locks=[],
                game_over=state.game_over,
                ending=None,
            )

        # unlocked_locks 基线：提交前已满足的锁
        before = self._satisfied_lock_ids(state)

        # 二、效果：门效果在前（过门的代价/奖励），抉择效果在后
        messages: list[str] = []
        if lock is not None:
            messages.extend(apply_effects(lock.effects, state))
        messages.extend(apply_effects(choice.effects, state))

        # 三、goto
        if choice.goto is not None:
            state.current_scene = choice.goto

        # 四、章推进：本章完成旗被写入 → 尝试推进到下一章
        messages.extend(self._maybe_advance_chapter(state))

        # 五、结局判定：按章声明序找第一条满足的结局
        game_over = False
        ending: dict | None = None
        for chapter in self.world.chapters:
            matched = next(
                (e for e in chapter.endings if evaluate(e.requires, state).satisfied), None
            )
            if matched is not None:
                game_over = True
                ending = {"id": matched.id, "title": matched.title}
                messages.append(f"结局达成：{matched.title}")
                break

        unlocked = [
            lock_id
            for lock_id, lk in self.registry.items()
            if (lock_id not in before and evaluate(lk.requires, state).satisfied)
        ]
        state.game_over = game_over
        state.ending = ending
        return ChoiceResult(
            messages=messages,
            state=state,
            unlocked_locks=unlocked,
            game_over=game_over,
            ending=ending,
        )

    # ---------- 内部 ----------

    def _find_choice(self, scene: Scene, choice_id: str) -> Choice:
        for c in scene.choices:
            if c.id == choice_id:
                return c
        raise ValueError(f"场景「{scene.id}」中无此抉择：{choice_id}")

    def _maybe_advance_chapter(self, state: GameState) -> list[str]:
        messages: list[str] = []
        idx = self._chapter_index(state.current_chapter)
        if idx is None:
            return messages
        done_flag = f"chapter_{state.current_chapter}_complete"
        if done_flag not in state.flags:
            return messages
        nxt = self._next_chapter(idx)
        if nxt is None:
            return messages  # 已是最后一章，停在原地
        blocked = [
            self.registry[lock_id]
            for lock_id in nxt.entry_locks
            if not evaluate(self.registry[lock_id].requires, state).satisfied
        ]
        if blocked:
            for lk in blocked:
                messages.append(f"前往{nxt.title}受阻：{lk.denial}")
            return messages
        state.current_chapter = nxt.id
        state.current_scene = nxt.scenes[0].id
        messages.append(f"进入{nxt.title}")
        return messages

    def _chapter_index(self, chapter_id: str) -> int | None:
        for i, chapter in enumerate(self.world.chapters):
            if chapter.id == chapter_id:
                return i
        return None

    def _next_chapter(self, idx: int) -> Chapter | None:
        return self.world.chapters[idx + 1] if idx + 1 < len(self.world.chapters) else None

    def _satisfied_lock_ids(self, state: GameState) -> set[str]:
        return {
            lock_id
            for lock_id, lk in self.registry.items()
            if evaluate(lk.requires, state).satisfied
        }
