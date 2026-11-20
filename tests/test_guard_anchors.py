"""Task M02.F05.I05：护栏锚表三查（缺锚/测试名漂移/孤儿条款）+ 启动自审并账。

锚纪律母本 = lock_anchors.py + test_lock_assertions.py 同形：
锚表每条 = 护栏断言面的双向锚（hit 命中侧 / miss 未命中·放行侧），
生产自检（webserver._audit_gate 并账）与 pytest 共读同一 audit_guards 实现。

测试集侧两本账（AST 扫 tests/test_guardrails.py，只读不改）：
- suite_test_names：全部测试函数名（漂移红的比对集）
- pinned_verdict_tests：断言面带 .verdict / ["verdict"] 且比较对象为 VERDICT_*
  常量的测试（孤儿条款红的反向账本——持有锚断言而无锚条目引用即孤儿）
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from text_rpg import guardrails, webserver
from text_rpg.guard_anchors import GUARD_ANCHORS, audit_guards
from text_rpg.guardrails import (
    VERDICT_PASS,
)

_GUARDRAILS_TEST = Path(__file__).resolve().parent / "test_guardrails.py"


def _verdict_name_map() -> dict[str, str]:
    """verdict 名册派生自 guardrails 模块 vars（与 guard_anchors.guard_verdicts 同源，
    非手抄账——新 VERDICT_* 出口即时入两本账，消静默 no-op 面）。"""
    return {name: value for name, value in vars(guardrails).items() if name.startswith("VERDICT_")}


def _suite_tree(path: Path) -> ast.Module:
    """被锚测试文件 → AST（读盘+解析一次复用）；文件缺失显式报错，不静默空账。"""
    if not path.is_file():
        raise AssertionError(f"被锚测试文件缺失：{path}")
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _iter_test_functions(tree: ast.Module):
    """顶层测试函数（FunctionDef 与 AsyncFunctionDef 都收——漏收 async 即锚断言逃逸）。"""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            yield node


def _suite_test_names(path: Path = _GUARDRAILS_TEST) -> set[str]:
    """被锚测试文件全部顶层测试函数名（AST 只读扫描）。"""
    return {node.name for node in _iter_test_functions(_suite_tree(path))}


def _pinned_verdict_tests(path: Path = _GUARDRAILS_TEST) -> dict[str, set[str]]:
    """verdict 出口 → 真实断言该出口的测试名集合（AST 扫描 Compare 节点）。"""
    name_map = _verdict_name_map()
    pinned: dict[str, set[str]] = {}
    for node in _iter_test_functions(_suite_tree(path)):
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Compare):
                continue
            has_face = False
            verdicts: set[str] = set()
            for piece in ast.walk(sub):
                if isinstance(piece, ast.Attribute) and piece.attr == "verdict":
                    has_face = True
                elif isinstance(piece, ast.Subscript):
                    sl = piece.slice
                    if isinstance(sl, ast.Constant) and sl.value == "verdict":
                        has_face = True
                elif isinstance(piece, ast.Name) and piece.id in name_map:
                    verdicts.add(name_map[piece.id])
            if has_face:
                for v in verdicts:
                    pinned.setdefault(v, set()).add(node.name)
    return pinned


def _anchored_test_names(anchors: dict) -> set[str]:
    names: set[str] = set()
    for entry in anchors.values():
        names.update(entry["hit"])
        names.update(entry["miss"])
    return names


# --------------------------------------------------------------- 绿向：全量对账


# fn: M02.F05.I05
def test_guard_anchor_table_passes_full_audit():
    """绿向：真锚表 × 真测试集（漂移+孤儿两账齐注入）全量对账，errors == []。"""
    report = audit_guards(
        GUARD_ANCHORS,
        suite_test_names=_suite_test_names(),
        pinned_verdict_tests=_pinned_verdict_tests(),
    )
    assert report.errors == []


# fn: M02.F05.I05
def test_real_anchor_names_all_exist_in_suite():
    """绿向小口：真锚表引用的每个测试名都在 tests/test_guardrails.py 真实存在。"""
    assert _anchored_test_names(GUARD_ANCHORS) <= _suite_test_names()


# fn: M02.F05.I05
def test_every_pinned_verdict_test_is_anchored_in_real_table():
    """绿向小口：真测试集里每个持有 verdict 锚断言的测试都被锚表引用（无孤儿）。"""
    for verdict, names in _pinned_verdict_tests().items():
        for name in names:
            assert name in _anchored_test_names(GUARD_ANCHORS), f"{name}（{verdict}）未被锚表引用"


# fn: M02.F05.I05
def test_anchor_hit_side_really_pins_declared_verdict():
    """绿向小口：每条锚 hit 侧至少一个测试真实断言其声明的 verdict（防锚表指错测试）。"""
    pinned = _pinned_verdict_tests()
    for face_id, entry in GUARD_ANCHORS.items():
        assert pinned[entry["verdict"]] & set(entry["hit"]), (
            f"锚面「{face_id}」hit 侧无任何测试真断言 verdict「{entry['verdict']}」"
        )


# --------------------------------------------------------------- 红向一：缺锚


# fn: M02.F05.I05
def test_missing_anchor_face_is_red():
    """缺锚红（面级）：删掉必备面条目 → 报缺面；补回即消。"""
    docked = {k: v for k, v in GUARD_ANCHORS.items() if k != "red_line_matched_detail"}
    report = audit_guards(docked)
    assert any("red_line_matched_detail" in msg and "缺" in msg for msg in report.errors)
    assert audit_guards(GUARD_ANCHORS).errors == []


# fn: M02.F05.I05
def test_verdict_exit_without_anchor_is_red():
    """缺锚红（出口级）：某 verdict 出口零锚条目 → 报出口缺锚。"""
    docked = {k: v for k, v in GUARD_ANCHORS.items() if k != "out_of_bounds_degraded"}
    report = audit_guards(docked)
    assert any("out_of_bounds_degraded" in msg for msg in report.errors)


# fn: M02.F05.I05
def test_orphan_anchor_face_is_red():
    """孤儿条款红（反向）：锚表挂了必备清单之外的面 → 报孤儿锚面。"""
    extra = dict(GUARD_ANCHORS)
    extra["ghost_face"] = {
        "verdict": VERDICT_PASS,
        "hit": ["test_inside_word_in_reply_passes_judgment"],
        "miss": ["test_out_of_bounds_twice_degrades_to_safe_template"],
    }
    report = audit_guards(extra)
    assert any("ghost_face" in msg and "孤儿" in msg for msg in report.errors)


# ----------------------------------------------------------- 红向二：测试名漂移


# fn: M02.F05.I05
def test_anchor_test_name_drift_is_red():
    """测试名漂移红：锚条目引用的测试名在测试集不存在（改名/删除未同步）→ 红。"""
    drifted = {
        "in_bounds_pass": {
            "verdict": VERDICT_PASS,
            "hit": ["test_inside_word_in_reply_passes_judgment"],
            "miss": ["test_out_of_bounds_twice_degrades_to_safe_template_renamed_away"],
        }
    }
    report = audit_guards(drifted, suite_test_names=_suite_test_names())
    assert any("漂移" in msg and "renamed_away" in msg for msg in report.errors)


# ------------------------------------------------------------- 红向三：孤儿条款


# fn: M02.F05.I05
def test_orphan_pinned_test_without_anchor_is_red():
    """孤儿条款红（正向）：测试集持有 verdict 锚断言但锚表无任何条目引用 → 红；
    真账本（无幻影）则绿。"""
    pinned = _pinned_verdict_tests()
    phantom = {v: set(n) for v, n in pinned.items()}
    phantom.setdefault(VERDICT_PASS, set()).add("test_brand_new_verdict_assertion")
    report = audit_guards(
        GUARD_ANCHORS,
        suite_test_names=_suite_test_names(),
        pinned_verdict_tests=phantom,
    )
    assert any("孤儿" in msg and "test_brand_new_verdict_assertion" in msg for msg in report.errors)
    assert (
        audit_guards(
            GUARD_ANCHORS,
            suite_test_names=_suite_test_names(),
            pinned_verdict_tests=pinned,
        ).errors
        == []
    )


# fn: M02.F05.I05
def test_anchor_hit_not_backed_by_verdict_assertion_is_red():
    """锚虚红：hit 侧引用的测试并不真断言其声明的 verdict（锚表指错测试）→ 红。"""
    fake = {
        "in_bounds_pass": {
            "verdict": VERDICT_PASS,
            "hit": ["test_system_prompt_contains_persona_and_inside_guidance"],
            "miss": ["test_out_of_bounds_twice_degrades_to_safe_template"],
        }
    }
    report = audit_guards(
        fake,
        suite_test_names=_suite_test_names(),
        pinned_verdict_tests=_pinned_verdict_tests(),
    )
    assert any("hit 侧" in msg for msg in report.errors)


# --------------------------------------------------------- 启动自审并账（webserver）


# fn: M02.F05.I05
def test_create_app_startup_self_check_includes_guard_anchor_gate(monkeypatch):
    """启动自审并账（npcs 先例同形）：坏锚表 → create_app RuntimeError，消息含护栏锚。"""
    monkeypatch.setattr(webserver, "GUARD_ANCHORS", {})
    with pytest.raises(RuntimeError) as exc:
        webserver.create_app()
    assert "护栏锚" in str(exc.value)


# fn: M02.F05.I05
def test_create_app_green_with_real_anchor_table():
    """绿向：真锚表随真世界过启动自审，create_app 正常装配。"""
    app = webserver.create_app()
    assert app is not None


# --------------------------------------------- 审查建议收口回归（建议 1/2/3）


# fn: M02.F05.I05
def test_anchor_miss_side_backed_by_verdict_assertion_is_red():
    """miss 侧绕过面红：miss 挂了真断言本面 verdict 的测试（放行侧不得挂命中证据）→ 红。"""
    fake = {
        "red_line_block": {
            "verdict": guardrails.VERDICT_BLOCKED,
            "hit": ["test_red_line_hit_blocks_without_llm_call"],
            "miss": ["test_red_line_blocked_turn_records_evidence_but_not_memory"],
        }
    }
    report = audit_guards(
        fake,
        suite_test_names=_suite_test_names(),
        pinned_verdict_tests=_pinned_verdict_tests(),
    )
    assert any("miss 侧" in msg for msg in report.errors)


# fn: M02.F05.I05
def test_moving_block_hit_test_into_miss_is_red():
    """审查建议 1 闭口：把 blocked 命中锚 test_red_line_hit_blocks_without_llm_call
    挪进 miss → 必须红（放行侧不得挂命中证据）。"""
    moved = {
        k: {"verdict": v["verdict"], "hit": list(v["hit"]), "miss": list(v["miss"])}
        for k, v in GUARD_ANCHORS.items()
    }
    entry = moved["red_line_block"]
    entry["hit"].remove("test_red_line_hit_blocks_without_llm_call")
    entry["miss"].append("test_red_line_hit_blocks_without_llm_call")
    report = audit_guards(
        moved,
        suite_test_names=_suite_test_names(),
        pinned_verdict_tests=_pinned_verdict_tests(),
    )
    assert any("miss 侧" in msg for msg in report.errors)


# fn: M02.F05.I05
def test_new_verdict_exit_is_derived_into_both_ledgers(monkeypatch):
    """verdict 名册派生自模块 vars（非手抄账）：monkeypatch 新出口 →
    audit 缺锚红 + 测试侧名册收录，双账同源无静默 no-op。"""
    monkeypatch.setattr(guardrails, "VERDICT_FUTURE_EXIT", "future_exit", raising=False)
    report = audit_guards(GUARD_ANCHORS)
    assert any("future_exit" in msg for msg in report.errors)
    assert "VERDICT_FUTURE_EXIT" in _verdict_name_map()


# fn: M02.F05.I05
def test_async_test_functions_are_collected(tmp_path):
    """AST 脆断修复：async def test_* 同样入两本账（漏收 = 锚断言逃逸审计面）。"""
    p = tmp_path / "suite_async.py"
    p.write_text(
        "from text_rpg.guardrails import VERDICT_PASS\n"
        "class _R:\n"
        "    verdict = 'pass'\n"
        "async def test_async_verdict_probe():\n"
        "    assert _R().verdict == VERDICT_PASS\n",
        encoding="utf-8",
    )
    assert "test_async_verdict_probe" in _suite_test_names(p)
    pinned = _pinned_verdict_tests(p)
    assert pinned[guardrails.VERDICT_PASS] == {"test_async_verdict_probe"}


# fn: M02.F05.I05
def test_missing_suite_file_raises_with_explicit_message(tmp_path):
    """AST 脆断修复：被锚测试文件缺失 → 显式报错文案，不静默空账。"""
    with pytest.raises(AssertionError, match="被锚测试文件缺失"):
        _suite_test_names(tmp_path / "nope.py")
