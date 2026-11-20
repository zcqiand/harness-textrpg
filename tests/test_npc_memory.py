"""Task M02.F05.I02：NPC 对话记忆存取（TDD 先红后绿）。

契约形状以 v2/v3 design spec §5.3 为准：per-(game_id, npc_id) 键的内存记忆库，
条目 {turn, player_text, npc_text, event_tags}；打标条目永久参与 prompt
（记仇钩子），普通条目只保留最近 window 条；同 v1 SessionStore——
进程生命周期即生命周期，零持久化零新依赖。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from text_rpg.memory import MemoryStore
from text_rpg.npcs import NpcDef, load_npcs

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"


def _npc(npc_id: str = "npc_woodcutter", window: int = 2) -> NpcDef:
    """测试用最小 NPC 契约（词表为契约声明的映射形状，spec §5.3 升级版）。"""
    return NpcDef(
        id=npc_id,
        name="樵夫",
        chapter="ch01",
        persona="两界山下的樵夫。",
        red_lines=["自称神明"],
        outside=["手机"],
        inside=["两界山"],
        memory_window=window,
        memory_event_tags={
            "insulted": ["骂", "畜生", "滚"],
            "gifted": ["送", "赠"],
            "promised": ["答应", "约定"],
        },
    )


# fn: M02.F05.I02
def test_record_assigns_monotonic_turns_and_returns_entry():
    store = MemoryStore([_npc()])
    e1 = store.record("g1", "npc_woodcutter", "你好", "客官安好")
    e2 = store.record("g1", "npc_woodcutter", "借问山路", "往西便是")
    assert e1["turn"] == 1 and e2["turn"] == 2  # 1 起单调递增无空洞
    assert e1["player_text"] == "你好" and e1["npc_text"] == "客官安好"
    assert e1["event_tags"] == []
    assert set(e1) == {"turn", "player_text", "npc_text", "event_tags"}


# fn: M02.F05.I02
def test_no_record_no_entry_no_turn_consumed():
    """被拦输入不计轮次：拦截路径不调 record——不 record 就不产生条目，
    轮次号不消费，两次 record 之间轮次连续。"""
    store = MemoryStore([_npc()])
    assert store.entries("g1", "npc_woodcutter") == []  # 不 record 就没有条目
    store.record("g1", "npc_woodcutter", "第一条", "答")
    # 中间一次输入被红线拦截：拦截路径不调 record
    e = store.record("g1", "npc_woodcutter", "第二条", "答")
    assert e["turn"] == 2
    assert [x["turn"] for x in store.entries("g1", "npc_woodcutter")] == [1, 2]


# fn: M02.F05.I02
def test_tagging_by_contract_vocab_on_player_or_npc_text():
    store = MemoryStore([_npc()])
    e1 = store.record("g1", "npc_woodcutter", "你这畜生，滚开！", "施主息怒")
    assert e1["event_tags"] == ["insulted"]
    e2 = store.record("g1", "npc_woodcutter", "贫僧送你一程", "贫僧答应施主一事")
    assert e2["event_tags"] == ["gifted", "promised"]  # 可多标
    e3 = store.record("g1", "npc_woodcutter", "无事", "休要骂人")
    assert e3["event_tags"] == ["insulted"]  # npc_text 命中也打标


# fn: M02.F05.I02
def test_tagged_entries_permanent_in_prompt_normal_slide_out():
    store = MemoryStore([_npc(window=2)])
    store.record("g1", "npc_woodcutter", "骂你一句畜生", "答")  # turn1 打标
    store.record("g1", "npc_woodcutter", "闲话二", "答")
    store.record("g1", "npc_woodcutter", "闲话三", "答")
    store.record("g1", "npc_woodcutter", "闲话四", "答")
    prompt = store.prompt_entries("g1", "npc_woodcutter")
    assert [e["turn"] for e in prompt] == [1, 3, 4]  # 打标永久 + 窗口内最近 2 条，按轮次序
    assert len(store.entries("g1", "npc_woodcutter")) == 4  # 原始全量不受窗口影响


# fn: M02.F05.I02
def test_prompt_dedups_tagged_entry_already_in_window():
    store = MemoryStore([_npc(window=3)])
    store.record("g1", "npc_woodcutter", "闲话一", "答")
    store.record("g1", "npc_woodcutter", "骂一句畜生", "答")  # turn2 打标且在窗口内
    store.record("g1", "npc_woodcutter", "闲话三", "答")
    prompt = store.prompt_entries("g1", "npc_woodcutter")
    assert [e["turn"] for e in prompt] == [1, 2, 3]  # turn2 去重只出现一次


# fn: M02.F05.I02
def test_empty_and_unknown_keys_return_empty_list():
    store = MemoryStore([_npc()])
    assert store.entries("gX", "npc_woodcutter") == []
    assert store.entries("", "npc_woodcutter") == []
    assert store.entries("g1", "npc_unknown") == []
    assert store.prompt_entries("gX", "npc_woodcutter") == []
    assert store.prompt_entries("", "npc_unknown") == []


# fn: M02.F05.I02
def test_multi_game_isolation():
    store = MemoryStore([_npc()])
    store.record("gA", "npc_woodcutter", "甲局的话", "答")
    store.record("gB", "npc_woodcutter", "乙局的话", "答")
    assert [e["player_text"] for e in store.entries("gA", "npc_woodcutter")] == ["甲局的话"]
    assert [e["player_text"] for e in store.entries("gB", "npc_woodcutter")] == ["乙局的话"]


# fn: M02.F05.I02
def test_repo_asset_vocab_drives_tagging_end_to_end():
    """真资产接线：load_npcs 读出的契约词表映射直接喂 MemoryStore 并生效。"""
    npcs = load_npcs(_REPO_DATA)
    store = MemoryStore(npcs)
    e = store.record("g1", "npc_woodcutter", "老丈莫骂俺", "答")
    assert "insulted" in e["event_tags"]


# ---------------------------------------------------------------- 外泄面（返回拷贝）


# fn: M02.F05.I02
def test_record_returns_copy_mutating_it_does_not_touch_store():
    """record 返回值是拷贝：调用方原地改 event_tags/文本不得清掉库内记仇钩子。"""
    store = MemoryStore([_npc(window=2)])
    e = store.record("g1", "npc_woodcutter", "骂一句畜生", "答")
    e["event_tags"].append("hacked")
    e["player_text"] = "hacked"
    e["npc_text"] = "hacked"
    stored = store.entries("g1", "npc_woodcutter")[0]
    assert stored["event_tags"] == ["insulted"]
    assert stored["player_text"] == "骂一句畜生" and stored["npc_text"] == "答"


# fn: M02.F05.I02
def test_entries_and_prompt_entries_return_deep_copies():
    """entries/prompt_entries 返回深拷贝：dict 浅拷贝不够，event_tags 内层
    list 仍指库内对象时原地 append 会静默改库——必须层层拷出。"""
    store = MemoryStore([_npc(window=2)])
    store.record("g1", "npc_woodcutter", "闲话一", "答")
    store.record("g1", "npc_woodcutter", "骂一句畜生", "答")  # turn2 打标
    got = store.entries("g1", "npc_woodcutter")
    got[0]["event_tags"].append("hacked")
    got[1]["event_tags"].clear()
    fresh = store.entries("g1", "npc_woodcutter")
    assert fresh[0]["event_tags"] == []
    assert fresh[1]["event_tags"] == ["insulted"]
    prompt = store.prompt_entries("g1", "npc_woodcutter")
    prompt[-1]["event_tags"].append("hacked")
    assert store.prompt_entries("g1", "npc_woodcutter")[-1]["event_tags"] == ["insulted"]


# ---------------------------------------------------------------- record 写面 fail-fast


# fn: M02.F05.I02
def test_record_unknown_npc_id_fails_fast():
    """MemoryStore 持有 NPC 契约：契约外 npc_id 不许攒孤儿账，写面 fail-fast。"""
    store = MemoryStore([_npc()])
    with pytest.raises(ValueError, match="npc_unknown"):
        store.record("g1", "npc_unknown", "你好", "答")
    assert store.entries("g1", "npc_unknown") == []


# fn: M02.F05.I02
def test_record_known_npc_id_still_works_after_fail_fast_guard():
    """fail-fast 守卫不得误伤契约内 NPC：守卫就位后正常落账打标不变。"""
    store = MemoryStore([_npc()])
    e = store.record("g1", "npc_woodcutter", "骂一句畜生", "答")
    assert e["turn"] == 1 and e["event_tags"] == ["insulted"]
