"""双层幻觉护栏（v2/v3 design spec §5.2/§5.3，TDD 先红后绿）。

第一层红线前置拦截：玩家输入命中 NPC 契约 ``red_lines`` 任一关键词即拦，
不调 LLM、不消耗记忆轮次（不调 :meth:`MemoryStore.record`），但落证据记录。
第二层知识边界后置校验：未拦的输入经注入 client（duck-type ``.generate``，
全仓唯一 httpx 触点在 llm.py，本层禁自起 httpx）取回复；回复命中
``outside`` 黑名单词表即越界（正向检测；``inside`` 白名单只进 system prompt
引导，不参与判定）；越界携带纠偏提示重试一次，仍越界降级安全回应模板，
界内放行。

纯对话层裁定（spec §5.3）：护栏永不写游戏状态（flags/attr/item 不动）；
真实发生的轮次（含降级回应——降级也是真实轮次）调 memory.record。

LLM 消费点走 client.generate 注入，测试以 duck-type stub（计数器 + 脚本化
回复队列）驱动，零网络（仓规 mock-friendly）。
"""
# @impl M02.F05.I03

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from text_rpg.memory import MemoryStore
from text_rpg.npcs import NpcDef

__all__ = [
    "DEGRADED_REPLY",
    "LLMClient",
    "VERDICT_BLOCKED",
    "VERDICT_OUT_OF_BOUNDS_DEGRADED",
    "VERDICT_PASS",
    "GuardResult",
    "Guardrails",
]

# verdict 稳定字符串三值（写死，T5 锚表可直接引用）。
VERDICT_BLOCKED = "blocked"
VERDICT_OUT_OF_BOUNDS_DEGRADED = "out_of_bounds_degraded"
VERDICT_PASS = "pass"

# 降级面固定文案（裁定：属降级模板非业务剧情数据，代码侧常量合法——
# 剧情/词表/锁等业务数据才受「禁硬编码进 Python」约束，spec §5.2 同款边界）。
DEGRADED_REPLY = "（老朽不知你所云，此话休要再提。施主另问别的吧。）"

_BLOCKED_REPLY = "（此话不可说，休要再提。）"

_CORRECTION_HINT = "（以下回应提到了不该知道的事物，请只以本世界内的见闻重新作答。）"


class LLMClient(Protocol):
    """护栏消费的 LLM 注入面（duck-type）：MockLLMClient / LiveLLMClient /
    测试 stub 同形——方法签名即契约，结构化类型不做 isinstance 检查。
    全仓唯一 httpx 触点在 llm.py；本层只消费 .generate。"""

    def generate(self, system_prompt: str, user_text: str) -> str:
        """给定 system prompt 与 user 文本，返回叙事回复。"""


@dataclass
class GuardResult:
    """talk 统一结果对象（T6 路由直接用）。

    ``matched`` 仅 blocked 非空（命中红线明细，spec §5.4 blocked=true + 明细）；
    ``memory_turn`` 为本回合占用的记忆轮号，被拦轮为 None（不消耗）。
    ``turn`` 为对话轮计数（含被拦轮），与证据记录同源。
    """

    game_id: str
    npc_id: str
    turn: int
    input: str
    output: str
    verdict: str
    matched: list[str] = field(default_factory=list)
    memory_turn: int | None = None


def _copy(entry: dict) -> dict:
    """证据条目拷贝（条目只一层标量）：外泄面纪律同 memory._copy。"""
    return dict(entry)


class Guardrails:
    """单 NPC 双层护栏：红线前置拦截 + 知识边界后置校验 + 证据记录。

    注入式装配（npc 契约 / LLM client / 记忆库全部外部传入），本层不持有
    任何游戏状态——纯对话层，永不写 flags/attr/item。
    """

    def __init__(self, npc: NpcDef, client: LLMClient, memory: MemoryStore) -> None:
        self._npc = npc
        self._client = client
        self._memory = memory
        self._evidence: dict[tuple[str, str], list[dict]] = {}

    # ------------------------------------------------------------ 对话入口

    def talk(self, game_id: str, player_text: str) -> GuardResult:
        """对话主入口：第一层红线拦截 → 第二层知识边界校验 → 记忆落账 + 证据落账。"""
        turn = len(self._evidence.setdefault((game_id, self._npc.id), [])) + 1

        # 第一层：红线前置拦截（命中即拦，不调 LLM，不调 memory.record）。
        matched = [w for w in self._npc.red_lines if w in player_text]
        if matched:
            self._append_evidence(
                game_id,
                turn,
                input_text=player_text,
                output=_BLOCKED_REPLY,
                verdict=VERDICT_BLOCKED,
            )
            return GuardResult(
                game_id=game_id,
                npc_id=self._npc.id,
                turn=turn,
                input=player_text,
                output=_BLOCKED_REPLY,
                verdict=VERDICT_BLOCKED,
                matched=list(matched),
                memory_turn=None,
            )

        # 第二层：知识边界后置校验（outside 正向检测；inside 只进 prompt 不判定）。
        system_prompt = self._system_prompt()
        user_text = self._user_prompt(game_id, player_text)
        reply = self._client.generate(system_prompt, user_text)
        if self._is_out_of_bounds(reply):
            # 纠偏重试走 _user_prompt 同形状（带记忆历史），并把越界回复原文
            # 附进纠偏提示——消掉「你上一段回应」的悬空引用。
            correction = f"{player_text}\n{_CORRECTION_HINT}\n越界原文：{reply}"
            corrected = self._client.generate(system_prompt, self._user_prompt(game_id, correction))
            if self._is_out_of_bounds(corrected):
                output, verdict = DEGRADED_REPLY, VERDICT_OUT_OF_BOUNDS_DEGRADED
            else:
                output, verdict = corrected, VERDICT_PASS
        else:
            output, verdict = reply, VERDICT_PASS

        # 真实发生的轮次（含降级回应）落记忆；被拦轮走不到这里。
        entry = self._memory.record(game_id, self._npc.id, player_text, output)
        self._append_evidence(game_id, turn, input_text=player_text, output=output, verdict=verdict)
        return GuardResult(
            game_id=game_id,
            npc_id=self._npc.id,
            turn=turn,
            input=player_text,
            output=output,
            verdict=verdict,
            matched=[],
            memory_turn=entry["turn"],
        )

    # ------------------------------------------------------------ 证据查询

    def evidence(self, game_id: str, npc_id: str) -> list[dict]:
        """按 (game_id, npc_id) 列证据清单；空/未知键返回空列表不报错。
        返回拷贝（外泄面纪律），调用方改返回值不扰动内部证据。"""
        return [_copy(e) for e in self._evidence.get((game_id, npc_id), [])]

    # ------------------------------------------------------------ 内部装配

    def _system_prompt(self) -> str:
        """system prompt = persona + inside 圈内话题引导 + outside 禁区引导。
        inside/outside 在此只作引导文案，判定逻辑不见 inside（见 _is_out_of_bounds）。"""
        return (
            f"{self._npc.persona}\n"
            f"（你只熟悉这些圈内话题：{'、'.join(self._npc.inside)}；"
            f"绝不谈及：{'、'.join(self._npc.outside)}。）"
        )

    def _user_prompt(self, game_id: str, player_text: str) -> str:
        """user prompt = 记忆历史（prompt_entries 面）+ 当前输入。"""
        npc_name = self._npc.name
        lines = [
            f"（第{e['turn']}轮）玩家：{e['player_text']}｜{npc_name}：{e['npc_text']}"
            for e in self._memory.prompt_entries(game_id, self._npc.id)
        ]
        lines.append(f"玩家：{player_text}")
        return "\n".join(lines)

    def _is_out_of_bounds(self, reply: str) -> bool:
        """越界判定只认 outside 黑名单（正向检测，无假阳性面）；inside 不在此判定。"""
        return any(w in reply for w in self._npc.outside)

    def _append_evidence(
        self, game_id: str, turn: int, input_text: str, output: str, verdict: str
    ) -> None:
        self._evidence[(game_id, self._npc.id)].append(
            {
                "game_id": game_id,
                "npc_id": self._npc.id,
                "turn": turn,
                "input": input_text,
                "output": output,
                "verdict": verdict,
            }
        )
