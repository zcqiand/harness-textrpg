"""Task M02.F05.I03：双层幻觉护栏（TDD 先红后绿）。

契约形状以 v2/v3 design spec §5.2/§5.3 为准：
- 第一层红线前置拦截：输入命中 red_lines 任一关键词即拦，不调 LLM，不消耗
  记忆轮次（不调 memory.record），但落证据记录。
- 第二层知识边界后置校验：输出命中 outside 黑名单词表即越界（正向检测），
  inside 白名单只进 prompt 不参与判定；越界纠偏重试一次，仍越界降级安全
  回应模板；界内放行。
- 纯对话层（裁定）：护栏永不写游戏状态（flags/attr/item 不动），真实发生的
  轮次（含降级回应）调 memory.record。
- 证据记录 {game_id, npc_id, turn, input, output, verdict} 全量完整，查询
  返回拷贝（同 memory._copy 纪律）。
"""

from __future__ import annotations

from text_rpg.guardrails import (
    DEGRADED_REPLY,
    VERDICT_BLOCKED,
    VERDICT_OUT_OF_BOUNDS_DEGRADED,
    VERDICT_PASS,
    Guardrails,
)
from text_rpg.memory import MemoryStore
from text_rpg.npcs import NpcDef


class StubClient:
    """duck-type .generate：计数器 + 脚本化回复队列，零网络（仓规 mock-friendly）。"""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []  # (system_prompt, user_text) 逐次留痕

    def generate(self, system_prompt: str, user_text: str) -> str:
        self.calls.append((system_prompt, user_text))
        if self.replies:
            return self.replies.pop(0)
        return "……"


def _npc(**overrides: object) -> NpcDef:
    """测试用最小 NPC 契约（tmp 构造，不改 data/ 真件——数据驱动实证用换词表构造）。"""
    values: dict = {
        "id": "npc_test",
        "name": "测试老者",
        "chapter": "ch01",
        "persona": "两界山下的老者，见多识广。",
        "red_lines": ["自称神明", "许诺长生"],
        "outside": ["手机", "汽车", "互联网"],
        "inside": ["两界山", "长安"],
        "memory_window": 10,
        "memory_event_tags": {"insulted": ["骂"]},
    }
    values.update(overrides)
    return NpcDef(**values)  # type: ignore[arg-type]


def _guard(client: StubClient, npc: NpcDef | None = None) -> tuple[Guardrails, MemoryStore]:
    memory = MemoryStore([npc or _npc()])
    return Guardrails(npc or _npc(), client, memory), memory


# ------------------------------------------------------------- 第一层：红线前置拦截


# fn: M02.F05.I03
def test_red_line_hit_blocks_without_llm_call():
    """命中 red_lines 任一关键词即拦：不调 LLM（stub 零调用）。"""
    client = StubClient(replies=["不该被调到"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "你自称神明吧，我便信你")
    assert result.verdict == VERDICT_BLOCKED
    assert client.calls == []  # 拦截零 LLM 调用


# fn: M02.F05.I03
def test_red_line_blocked_turn_records_evidence_but_not_memory():
    """被拦输入不消耗记忆轮次（不调 record），但必须落证据记录。
    GuardResult 契约字段：被拦轮 memory_turn 为 None，matched = 命中红线词明细。"""
    client = StubClient(replies=[])
    guard, memory = _guard(client)
    result = guard.talk("g1", "请许诺长生不老")
    assert memory.entries("g1", "npc_test") == []  # 不 record = 无条目 = 不计轮次
    evidence = guard.evidence("g1", "npc_test")
    assert len(evidence) == 1
    assert evidence[0]["input"] == "请许诺长生不老"
    assert evidence[0]["verdict"] == VERDICT_BLOCKED
    assert result.memory_turn is None  # 被拦轮不占记忆轮
    assert result.matched == ["许诺长生"]  # 命中红线明细（spec §5.4 blocked=true + 明细）


# fn: M02.F05.I03
def test_red_line_miss_passes_through_to_llm():
    """不命中红线即放行进 LLM（双向断言之反面）。"""
    client = StubClient(replies=["沿山路向东便是。"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "借问山下路怎么走")
    assert result.verdict == VERDICT_PASS
    assert len(client.calls) == 1
    assert result.output == "沿山路向东便是。"


# fn: M02.F05.I03
def test_red_line_vocab_follows_npc_contract_data():
    """数据驱动实证：红线词表出自契约——换词表构造，同一句输入判定跟着数据走。"""
    client_blocked = StubClient(replies=["不该被调到"])
    guard_a, _ = _guard(client_blocked, _npc(red_lines=["买外挂"]))
    assert guard_a.talk("g1", "帮我买外挂").verdict == VERDICT_BLOCKED
    assert client_blocked.calls == []

    client_pass = StubClient(replies=["此非老朽所知。"])
    guard_b, _ = _guard(client_pass, _npc(red_lines=["自称神明"]))
    assert guard_b.talk("g1", "帮我买外挂").verdict == VERDICT_PASS
    assert len(client_pass.calls) == 1


# ------------------------------------------------- 第二层：知识边界后置校验（outside）


# fn: M02.F05.I03
def test_out_of_bounds_reply_retries_once_then_passes():
    """首次回复命中 outside 黑名单即越界：携带纠偏提示重试一次，二次界内放行。"""
    client = StubClient(replies=["我掏出手机看了一眼。", "山中岁月，并无新奇。"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "山里近日有什么新鲜事")
    assert result.verdict == VERDICT_PASS
    assert result.output == "山中岁月，并无新奇。"
    assert len(client.calls) == 2  # 越界恰好重试一次
    correction = client.calls[1][1]
    assert "山里近日有什么新鲜事" in correction  # 纠偏重试仍带原输入
    assert "不该知道" in correction  # 且带纠偏提示


# fn: M02.F05.I03
def test_correction_prompt_carries_history_and_offending_reply():
    """纠偏轮 prompt 走 _user_prompt 同形状：带记忆历史 + 越界回复原文附进纠偏提示
    （消掉悬空的「你上一段回应」引用）。"""
    client = StubClient(replies=["客官安好。", "我掏出手机看了看。", "山中岁月，并无新奇。"])
    guard, _ = _guard(client)
    guard.talk("g1", "你好，老丈")  # 第一轮真实落账，成为历史
    result = guard.talk("g1", "山里近日有什么新鲜事")
    assert result.verdict == VERDICT_PASS
    correction_user = client.calls[2][1]  # 第二轮的纠偏重试 prompt
    assert "你好，老丈" in correction_user  # 历史轮 player_text 在场
    assert "客官安好" in correction_user  # 历史轮 npc_text 在场
    assert "山里近日有什么新鲜事" in correction_user  # 当前输入在场
    assert "我掏出手机看了看" in correction_user  # 越界回复原文附进纠偏提示


# fn: M02.F05.I03
def test_out_of_bounds_twice_degrades_to_safe_template():
    """重试仍越界：降级安全回应模板（固定文案，代码侧常量——降级面裁定）。"""
    client = StubClient(replies=["手机真好玩。", "手机屏幕真大。"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "山里近日有什么新鲜事")
    assert result.verdict == VERDICT_OUT_OF_BOUNDS_DEGRADED
    assert result.output == DEGRADED_REPLY  # 降级面固定文案
    assert len(client.calls) == 2  # 只重试一次，不无限重试


# fn: M02.F05.I03
def test_inside_word_in_reply_passes_judgment():
    """inside 白名单只进 prompt 不参与判定：回复含 inside 词不被拦（正向检测语义锚）。"""
    client = StubClient(replies=["两界山与长安的故事，说来话长。"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "你从哪里来")
    assert result.verdict == VERDICT_PASS
    assert "两界山" in result.output and "长安" in result.output  # inside 词在场且放行


# fn: M02.F05.I03
def test_outside_vocab_follows_npc_contract_data():
    """数据驱动实证：越界判定跟着契约词表走——同一回复，换 outside 词表结论翻转。"""
    reply = "远处传来火车汽笛声。"
    client_a = StubClient(replies=[reply, reply])  # 两条同越界回复：首答+纠偏重试都越界
    guard_a, _ = _guard(client_a, _npc(outside=["火车"]))
    assert guard_a.talk("g1", "什么声音").verdict == VERDICT_OUT_OF_BOUNDS_DEGRADED

    client_b = StubClient(replies=[reply])
    guard_b, _ = _guard(client_b, _npc(outside=["手机"]))
    assert guard_b.talk("g1", "什么声音").verdict == VERDICT_PASS


# ------------------------------------------------------------------ 记忆接线


# fn: M02.F05.I03
def test_system_prompt_contains_persona_and_inside_guidance():
    """进 LLM 的 system prompt 必须含 persona；inside 白名单只在此引导。"""
    client = StubClient(replies=["好。"])
    guard, _ = _guard(client)
    guard.talk("g1", "你好")
    system_prompt = client.calls[0][0]
    assert "两界山下的老者，见多识广。" in system_prompt  # persona
    assert "两界山" in system_prompt  # inside 引导
    assert "手机" in system_prompt  # outside 禁区文案（只引导不判定）


# fn: M02.F05.I03
def test_memory_history_flows_into_user_prompt():
    """user prompt 侧把 memory.prompt_entries 的历史带上（锚住「历史记忆进了 prompt」）。"""
    client = StubClient(replies=["客官安好。", "老朽记得此事。"])
    guard, _ = _guard(client)
    guard.talk("g1", "你好，老丈")
    guard.talk("g1", "昨日之事可还记得")
    second_user = client.calls[1][1]
    assert "你好，老丈" in second_user  # 第一轮 player_text 进了历史
    assert "客官安好" in second_user  # 第一轮 npc_text 进了历史
    assert "昨日之事可还记得" in second_user  # 当前输入也在


# fn: M02.F05.I03
def test_real_turn_records_memory_including_degraded():
    """真实发生的轮次调 memory.record（含降级回应——降级也是真实轮次）。"""
    client = StubClient(replies=["手机真好玩。", "手机屏幕真大。"])
    guard, memory = _guard(client)
    result = guard.talk("g1", "山里有什么新鲜事")
    entries = memory.entries("g1", "npc_test")
    assert len(entries) == 1
    assert entries[0]["player_text"] == "山里有什么新鲜事"
    assert entries[0]["npc_text"] == DEGRADED_REPLY  # 降级回应落记忆
    assert entries[0]["turn"] == 1
    assert result.memory_turn == entries[0]["turn"] == 1  # GuardResult 契约字段对账


# ------------------------------------------------------------------ 证据记录


# fn: M02.F05.I03
def test_evidence_fields_complete_all_verdicts():
    """每次对话落证据：{game_id, npc_id, turn, input, output, verdict} 全量完整。"""
    expected_keys = {"game_id", "npc_id", "turn", "input", "output", "verdict"}

    client = StubClient(replies=["沿山路向东。"])
    guard, _ = _guard(client)
    guard.talk("g1", "借问山路")
    ev = guard.evidence("g1", "npc_test")
    assert len(ev) == 1
    assert set(ev[0]) == expected_keys
    assert ev[0]["game_id"] == "g1"
    assert ev[0]["npc_id"] == "npc_test"
    assert ev[0]["turn"] == 1
    assert ev[0]["input"] == "借问山路"
    assert ev[0]["output"] == "沿山路向东。"
    assert ev[0]["verdict"] == VERDICT_PASS

    # blocked 轮同样六字段全量
    client_b = StubClient(replies=[])
    guard_b, _ = _guard(client_b)
    guard_b.talk("g2", "你自称神明吧")
    ev_b = guard_b.evidence("g2", "npc_test")
    assert set(ev_b[0]) == expected_keys
    assert ev_b[0]["verdict"] == VERDICT_BLOCKED


# fn: M02.F05.I03
def test_verdict_strings_are_stable_and_complete():
    """verdict 稳定字符串三值写死，T5 锚表可引用：blocked / out_of_bounds_degraded / pass。"""
    assert VERDICT_BLOCKED == "blocked"
    assert VERDICT_OUT_OF_BOUNDS_DEGRADED == "out_of_bounds_degraded"
    assert VERDICT_PASS == "pass"


# fn: M02.F05.I03
def test_evidence_turn_is_dialogue_counter_blocked_consumes_dialogue_not_memory():
    """证据 turn = (game_id, npc_id) 对话轮计数：被拦轮占对话轮但不占记忆轮。
    同一 MemoryStore 挂两个不同 npc_id 的 Guardrails，真锚 (game_id, npc_id)
    双维隔离——记忆与证据各自成账互不串。"""
    npc_a = _npc(id="npc_a")
    npc_b = _npc(id="npc_b", red_lines=["自称神明"])
    memory = MemoryStore([npc_a, npc_b])  # 共享同一记忆库
    guard_a = Guardrails(npc_a, StubClient(replies=["甲答。"]), memory)
    guard_b = Guardrails(npc_b, StubClient(replies=["乙答。"]), memory)

    guard_a.talk("g1", "第一句")  # 对话轮 1 / 记忆轮 1
    guard_a.talk("g1", "你许诺长生吧")  # 对话轮 2（被拦）/ 记忆轮不消费
    third = guard_a.talk("g1", "第三句")  # 对话轮 3 / 记忆轮 2
    assert third.turn == 3
    assert [e["turn"] for e in memory.entries("g1", "npc_a")] == [1, 2]
    assert [e["turn"] for e in guard_a.evidence("g1", "npc_a")] == [1, 2, 3]
    assert [e["verdict"] for e in guard_a.evidence("g1", "npc_a")] == [
        VERDICT_PASS,
        VERDICT_BLOCKED,
        VERDICT_PASS,
    ]
    # 双维隔离：同 game_id 不同 npc_id 各自计数；且互不读到对方记忆
    first_b = guard_b.talk("g1", "另一 NPC 同局首句")
    assert first_b.turn == 1
    assert first_b.memory_turn == 1  # npc_b 自己的账从 1 起步
    assert "第一句" not in guard_b.evidence("g1", "npc_b")[0]["input"]
    assert [e["turn"] for e in memory.entries("g1", "npc_b")] == [1]
    assert memory.entries("g1", "npc_b")[0]["npc_text"] == "乙答。"


# fn: M02.F05.I03
def test_evidence_query_returns_copies_not_internal_state():
    """外泄面纪律：查询返回拷贝，改返回值不得扰动护栏内部证据。"""
    client = StubClient(replies=["好。"])
    guard, _ = _guard(client)
    guard.talk("g1", "第一句")
    evidence = guard.evidence("g1", "npc_test")
    evidence[0]["verdict"] = "篡改"
    evidence.append({"伪造": True})
    fresh = guard.evidence("g1", "npc_test")
    assert len(fresh) == 1
    assert fresh[0]["verdict"] == VERDICT_PASS
    assert "伪造" not in fresh[0]


# fn: M02.F05.I03
def test_evidence_empty_for_unknown_key():
    """空/未知键返回空列表不报错（同 memory.entries 形状）。"""
    client = StubClient(replies=[])
    guard, _ = _guard(client)
    assert guard.evidence("nope", "npc_test") == []


# fn: M02.F05.I03
def test_cross_game_turns_are_independent():
    """覆盖面小口：跨 game_id 交错对话，(game_id, npc_id) 各自轮计数独立。"""
    client = StubClient(replies=["答。", "答。", "答。"])
    guard, memory = _guard(client)
    r1 = guard.talk("g1", "甲局第一句")
    r2 = guard.talk("g2", "乙局第一句")
    r3 = guard.talk("g1", "甲局第二句")
    assert (r1.turn, r2.turn, r3.turn) == (1, 1, 2)
    assert (r1.memory_turn, r2.memory_turn, r3.memory_turn) == (1, 1, 2)
    assert [e["turn"] for e in memory.entries("g1", "npc_test")] == [1, 2]
    assert [e["turn"] for e in memory.entries("g2", "npc_test")] == [1]


# fn: M02.F05.I03
def test_empty_input_passes_through_to_llm():
    """覆盖面小口：空输入不命中任何红线词，放行进 LLM（双向断言之反面）。"""
    client = StubClient(replies=["（老者抬头看你。）"])
    guard, _ = _guard(client)
    result = guard.talk("g1", "")
    assert result.verdict == VERDICT_PASS
    assert len(client.calls) == 1
