"""Guard test anchor table (v1 lock_anchors twin discipline: production self-check
and pytest share one audit implementation).

GUARD_ANCHORS[face_id] = {
    "verdict": <guardrails.VERDICT_* constant>,
    "hit": [pytest names...],   # positive side: the guard actually fires
    "miss": [pytest names...],  # negative side: no fire / pass-through
}

Faces: the three verdict exits + red-line matched detail + evidence verdict ledger.
Checks (audit_guards):
1. missing-anchor red: required face absent / a verdict exit has zero anchor entries
2. shape red: orphan face not in required list / bad verdict value / hit-miss sides
   missing or overlapping
3. suite reconciliation (runs only when pytest injects the two ledgers):
   - drift red: anchored test name missing from the test suite
   - orphan red: suite test holds a verdict assertion but no anchor references it;
     hit side has no test truly asserting the declared verdict; miss side holds a
     test that truly asserts the declared verdict (bypass face)
Production side (webserver._audit_gate) passes the table only; pytest injects the
two ledgers (see tests/test_guard_anchors.py).
"""

# @impl M02.F05.I05

from __future__ import annotations

import text_rpg.guardrails as guardrails
from text_rpg.locks import AuditReport

__all__ = ["GUARD_ANCHORS", "REQUIRED_FACES", "audit_guards"]


def guard_verdicts() -> frozenset:
    """Verdict exits derived from guardrails module vars at call time:
    a new VERDICT_* export enters both ledgers immediately (no silent no-op)."""
    return frozenset(
        value for name, value in vars(guardrails).items() if name.startswith("VERDICT_")
    )


# Required anchor faces: three verdict exits + matched detail + evidence ledger.
REQUIRED_FACES = (
    "red_line_block",
    "red_line_matched_detail",
    "out_of_bounds_degraded",
    "in_bounds_pass",
    "evidence_verdict_ledger",
)

GUARD_ANCHORS: dict = {
    "red_line_block": {
        "verdict": guardrails.VERDICT_BLOCKED,
        "hit": [
            "test_red_line_hit_blocks_without_llm_call",
            "test_red_line_vocab_follows_npc_contract_data",
        ],
        "miss": [
            "test_red_line_miss_passes_through_to_llm",
            "test_empty_input_passes_through_to_llm",
        ],
    },
    "red_line_matched_detail": {
        "verdict": guardrails.VERDICT_BLOCKED,
        "hit": [
            "test_red_line_blocked_turn_records_evidence_but_not_memory",
            "test_red_line_vocab_follows_npc_contract_data",
        ],
        "miss": ["test_red_line_miss_passes_through_to_llm"],
    },
    "out_of_bounds_degraded": {
        "verdict": guardrails.VERDICT_OUT_OF_BOUNDS_DEGRADED,
        "hit": [
            "test_out_of_bounds_twice_degrades_to_safe_template",
            "test_outside_vocab_follows_npc_contract_data",
        ],
        "miss": ["test_out_of_bounds_reply_retries_once_then_passes"],
    },
    "in_bounds_pass": {
        "verdict": guardrails.VERDICT_PASS,
        "hit": [
            "test_red_line_miss_passes_through_to_llm",
            "test_correction_prompt_carries_history_and_offending_reply",
            "test_inside_word_in_reply_passes_judgment",
        ],
        "miss": ["test_out_of_bounds_twice_degrades_to_safe_template"],
    },
    "evidence_verdict_ledger": {
        "verdict": guardrails.VERDICT_PASS,
        "hit": [
            "test_evidence_fields_complete_all_verdicts",
            "test_evidence_turn_is_dialogue_counter_blocked_consumes_dialogue_not_memory",
            "test_evidence_query_returns_copies_not_internal_state",
        ],
        "miss": ["test_red_line_blocked_turn_records_evidence_but_not_memory"],
    },
}


def audit_guards(anchors: dict, suite_test_names=None, pinned_verdict_tests=None) -> AuditReport:
    """Shared audit: production passes the table only; pytest injects the ledgers."""
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_coverage(anchors))
    errors.extend(_check_shape(anchors))
    if suite_test_names is not None or pinned_verdict_tests is not None:
        errors.extend(
            _check_suite(
                anchors,
                suite_test_names,
                pinned_verdict_tests,
            )
        )

    return AuditReport(errors=errors, warnings=warnings)


def _check_coverage(anchors: dict) -> list[str]:
    errors = []
    for face in REQUIRED_FACES:
        if face not in anchors:
            errors.append(f"护栏锚：必备锚面「{face}」缺条目")
    for verdict in sorted(guard_verdicts()):
        if not any(e.get("verdict") == verdict for e in anchors.values()):
            errors.append(f"护栏锚：verdict 出口「{verdict}」零锚条目")
    return errors


def _check_shape(anchors: dict) -> list[str]:
    errors = []
    for face_id, entry in anchors.items():
        if face_id not in REQUIRED_FACES:
            errors.append(f"护栏锚：孤儿锚面「{face_id}」不在必备面清单")
        if entry.get("verdict") not in guard_verdicts():
            errors.append(f"护栏锚：锚面「{face_id}」verdict 值非法或缺失")
        hit = entry.get("hit") or []
        miss = entry.get("miss") or []
        if not _valid_side(hit) or not _valid_side(miss):
            errors.append(f"护栏锚：锚面「{face_id}」hit/miss 双侧须为非空测试名清单")
        elif set(hit) & set(miss):
            errors.append(f"护栏锚：锚面「{face_id}」hit/miss 两侧不得引用同一测试")
    return errors


def _check_suite(anchors, suite_test_names, pinned_verdict_tests) -> list[str]:
    errors = []
    for face_id, entry in anchors.items():
        for side in ("hit", "miss"):
            for name in entry.get(side) or []:
                if suite_test_names is not None and name not in suite_test_names:
                    errors.append(
                        f"护栏锚：锚面「{face_id}」{side} 侧测试名漂移：{name} 不在测试集"
                    )
    if pinned_verdict_tests is None:
        return errors
    anchored = set()
    for e in anchors.values():
        anchored.update(e.get("hit") or [])
        anchored.update(e.get("miss") or [])
    for verdict, names in pinned_verdict_tests.items():
        for name in names:
            if name not in anchored:
                errors.append(
                    f"护栏锚：孤儿条款——测试「{name}」持有 verdict「{verdict}」锚断言但锚表无引用"
                )
    for face_id, entry in anchors.items():
        verdict = entry.get("verdict")
        hit = set(entry.get("hit") or [])
        miss = set(entry.get("miss") or [])
        if verdict in pinned_verdict_tests and not (pinned_verdict_tests[verdict] & hit):
            errors.append(f"护栏锚：锚面「{face_id}」hit 侧无任何测试真断言 verdict「{verdict}」")
        if verdict in pinned_verdict_tests and (pinned_verdict_tests[verdict] & miss):
            offenders = "、".join(sorted(pinned_verdict_tests[verdict] & miss))
            errors.append(
                f"护栏锚：锚面「{face_id}」miss 侧挂了真断言 verdict「{verdict}」的测试"
                f"（放行侧不得挂命中证据）：{offenders}"
            )
    return errors


def _valid_side(value) -> bool:
    return (
        isinstance(value, list) and len(value) > 0 and all(isinstance(s, str) and s for s in value)
    )
