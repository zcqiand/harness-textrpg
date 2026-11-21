"""对抗结算（spec §5.5，M02.F06.I02）：种子化掷点 + 策略表取行动 + 编号账本。

随机源只用 seed 派生：``random.Random(seed)`` 实例化（禁全局 random）——同种子+同入参
→ 账本逐字段全等（T12 重放全等的地基）。账本每步 {seq, actor, action, power, roll}，
seq 从 1 递增。效果面同 v1 effects 四类（contracts.apply），胜写攻克旗、负减属性。

玩家力量服务端派生（T11 审查阻断 1，spec §5.5「属性+旗标加权」语义的裁量定案）：
**属性和 + 每旗标 +1**（``derive_player_power``，确定性纯派生）——客户端不传力量，
无覆盖通道。

重放前置=对手契约同版（T12 将落此约定）：种子从局状态派生、掷点只吃种子，但策略行
power/base 取自对手契约——契约升版后历史种子不保证重放全等，重放须以同版契约为前提。
"""
# @impl M02.F06.I02

from __future__ import annotations

import random

from text_rpg.contracts import apply as apply_effects

__all__ = ["apply_oppose_effects", "derive_player_power", "pick_action_row", "settle"]


def derive_player_power(state) -> int:
    """玩家力量服务端派生（确定性纯派生，客户端不传力量）：属性和 + 每旗标 +1。

    spec §5.5「属性+旗标加权」语义的最简可核实现——加权规则=每旗标恒 +1，不分支、
    不读随机源，同局状态必同力量（重放全等的组成部分）。"""
    return sum(int(v) for v in state.attributes.values()) + len(state.flags)


def pick_action_row(opponent, player_flags) -> dict:
    """策略表取行动：条件行（when.player_flag ∈ 玩家旗标）按表序首中优先；不命中走
    default 行（when.default is True）。无命中且缺 default → ValueError（审计保证
    default 行必在，此处 fail-fast 双保险）。"""
    flags = set(player_flags)
    default_row = None
    for row in opponent.strategy_table:
        when = row.get("when") or {}
        flag = when.get("player_flag")
        if isinstance(flag, str) and flag in flags:
            return row
        if when.get("default") is True and default_row is None:
            default_row = row
    if default_row is None:
        raise ValueError(f"对手「{opponent.id}」策略表无命中行且缺 default 行")
    return default_row


def settle(opponent, player_power: int, seed, player_flags=()) -> dict:
    """一次对抗结算：策略表取行动 → 种子化掷点 → 胜负判定 → 编号账本。

    对手 power = 命中策略行 power + base 属性和；掷点各 1..6（同一 seed 派生 rng 依序
    抽取，玩家先）；有效力 = power + roll；平点先手归玩家。返回
    {"winner", "action", "ledger"}。
    """
    row = pick_action_row(opponent, player_flags)
    action = str(row["action"])
    row_power = int(row["power"])
    opponent_power = row_power + sum(int(v) for v in opponent.base.values())
    rng = random.Random(seed)
    player_roll = rng.randint(1, 6)
    opponent_roll = rng.randint(1, 6)
    player_effective = player_power + player_roll
    opponent_effective = opponent_power + opponent_roll
    winner = "player" if player_effective >= opponent_effective else opponent.id
    ledger = [
        {
            "seq": 1,
            "actor": "player",
            "action": "oppose",
            "power": player_power,
            "roll": player_roll,
        },
        {
            "seq": 2,
            "actor": opponent.id,
            "action": action,
            "power": opponent_power,
            "roll": opponent_roll,
        },
    ]
    return {"winner": winner, "action": action, "ledger": ledger}


def apply_oppose_effects(opponent, winner: str, state) -> list[str]:
    """胜负效果落地（同 v1 effects 四类）：胜 → flag 效果写攻克旗；负 → attr 效果减属性。
    经 contracts.apply 执行（四类形状/中文消息与 v1 抉择效果同链）。"""
    if winner == "player":
        effects = [{"flag": f"defeated_{opponent.id}"}]
    else:
        # 负面效果锚起始属性实存键（T11 审查建议 3 裁量）：insight 是 game-start.json
        # 起始属性（值 1）——败=受挫失洞察，不凭空造不存在的属性键。
        effects = [{"attr": {"insight": -1}}]
    return apply_effects(effects, state)
