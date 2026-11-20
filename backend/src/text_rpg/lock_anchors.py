"""锁测试锚表。

ANCHORS[lock_id] = {"pass": <pytest 用例 id>, "deny": <pytest 用例 id>}
——每个注册锁须有正反两条 pytest 断言锚，与锁断言测试一一对应。

骨架为空表：逐章条目自 Task 7 起随章回包补入。
启动自审（locks.audit）会在锚未覆盖时拒绝启动，
另有 pytest 侧覆盖检查（后续任务加装）会保持红直到锚补齐。
"""

from __future__ import annotations

__all__ = ["ANCHORS"]

ANCHORS: dict = {
    "lock_ch01_rations_gate": {
        "pass": "test_lock_pass[lock_ch01_rations_gate]",
        "deny": "test_lock_deny[lock_ch01_rations_gate]",
    },
    "lock_ch01_temple_spot": {
        "pass": "test_lock_pass[lock_ch01_temple_spot]",
        "deny": "test_lock_deny[lock_ch01_temple_spot]",
    },
    "lock_ch01_shortcut": {
        "pass": "test_lock_pass[lock_ch01_shortcut]",
        "deny": "test_lock_deny[lock_ch01_shortcut]",
    },
    "lock_ch02_entry": {
        "pass": "test_lock_pass[lock_ch02_entry]",
        "deny": "test_lock_deny[lock_ch02_entry]",
    },
    "lock_ch02_second_strike": {
        "pass": "test_lock_pass[lock_ch02_second_strike]",
        "deny": "test_lock_deny[lock_ch02_second_strike]",
    },
    "lock_ch02_third_strike": {
        "pass": "test_lock_pass[lock_ch02_third_strike]",
        "deny": "test_lock_deny[lock_ch02_third_strike]",
    },
    "lock_ch02_report_tang": {
        "pass": "test_lock_pass[lock_ch02_report_tang]",
        "deny": "test_lock_deny[lock_ch02_report_tang]",
    },
}
