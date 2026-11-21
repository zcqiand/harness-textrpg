"""T17+T18（M05.F01.I01 / M05.F01.I02）全链路验收脚本与证据回执——TDD 先红后绿。

形状真源 = v2/v3 design spec §5.7：
- scripts/acceptance.py 四能力逐项探活（健康/建局+对话含拦截/对手结算重放/奇遇生成
  准入），经 TestClient/内存 app，不起服。
- 每项产出 {item, ok, detail}；任一失败 exit 非 0。
- 证据回执 JSON：version/generated_at/mode/四能力逐项结论 + 回归汇总（回归计数由
  CI/调用方填充，脚本不重复跑全量测试）；落 _work/（过程件不入库）。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import acceptance
import pytest
from fastapi.testclient import TestClient

_ITEMS = ("health", "talk_interception", "oppose_replay", "encounter_admission")


@pytest.fixture()
def client() -> TestClient:
    return acceptance.build_client()


# fn: M05.F01.I01
def test_probe_health_ok(client: TestClient):
    """探活 a：/api/health ok=true 且带 mode 键。"""
    check = acceptance.probe_health(client)
    assert check["item"] == "health"
    assert check["ok"] is True
    assert check["detail"]


# fn: M05.F01.I01
def test_probe_talk_interception_ok(client: TestClient):
    """探活 b：建局 → talk 红线词 → blocked=true（拦截面全链）。"""
    check = acceptance.probe_talk_interception(client)
    assert check["item"] == "talk_interception"
    assert check["ok"] is True
    assert check["detail"]


# fn: M05.F01.I01
def test_probe_oppose_replay_ok(client: TestClient):
    """探活 c：两同构局同 choice 带 oppose → oppose_ledger 全等（重放面）。"""
    check = acceptance.probe_oppose_replay(client)
    assert check["item"] == "oppose_replay"
    assert check["ok"] is True
    assert check["detail"]


# fn: M05.F01.I01
def test_probe_encounter_admission_ok(client: TestClient):
    """探活 d：奇遇生成准入 200，临时场景入章且 GET 可见。"""
    check = acceptance.probe_encounter_admission(client)
    assert check["item"] == "encounter_admission"
    assert check["ok"] is True
    assert check["detail"]


# fn: M05.F01.I01
def test_run_probes_four_items_shape_all_ok():
    """run_probes：四项齐、逐项 {item, ok, detail}、item 精确清单、全 ok。"""
    checks = acceptance.run_probes()
    assert [c["item"] for c in checks] == list(_ITEMS)
    for check in checks:
        assert set(check) == {"item", "ok", "detail"}
        assert check["ok"] is True
        assert isinstance(check["detail"], str) and check["detail"]


# fn: M05.F01.I01
def test_failing_probe_yields_not_all_green_and_nonzero_exit():
    """失败路径：任一探活失败 → 汇总 all_green=false，exit 非 0（monkeypatch 造失败）。"""
    fake = {"item": "health", "ok": False, "detail": "注入失败：health 探针不可达"}
    checks = acceptance.run_probes(probes=[("health", lambda _c: fake)])
    assert any(c["ok"] is False for c in checks)
    evidence = acceptance.build_evidence(checks)
    assert evidence["all_green"] is False
    assert acceptance.evidence_exit_code(evidence) != 0


# fn: M05.F01.I02
def test_build_evidence_schema_fields():
    """证据 schema：version/generated_at/mode/checks/all_green/regression 字段齐。"""
    evidence = acceptance.build_evidence(acceptance.run_probes())
    assert set(evidence) == {
        "version",
        "generated_at",
        "mode",
        "checks",
        "all_green",
        "regression",
    }
    assert isinstance(evidence["version"], str) and evidence["version"]
    # generated_at：只验存在与 ISO 可解析格式，禁断言具体时间值
    generated = datetime.fromisoformat(evidence["generated_at"])
    assert generated.tzinfo is not None  # UTC 带时区
    assert evidence["mode"] == "mock"
    assert evidence["all_green"] is True
    assert [c["item"] for c in evidence["checks"]] == list(_ITEMS)


# fn: M05.F01.I02
def test_build_evidence_regression_summary_defaults_and_filled():
    """回归汇总默认由调用方填充（字段齐、值为空）；显式传入则落地且 all_green 可算。"""
    evidence = acceptance.build_evidence(
        [{"item": "health", "ok": True, "detail": "d"}],
        regression_total=None,
        regression_passed=None,
    )
    regression = evidence["regression"]
    assert set(regression) == {"passed", "total", "all_green", "filled_by"}
    assert regression["passed"] is None and regression["total"] is None
    assert regression["all_green"] is None
    filled = acceptance.build_evidence(
        [{"item": "health", "ok": True, "detail": "d"}], regression_total=268, regression_passed=268
    )
    assert filled["regression"]["passed"] == 268
    assert filled["regression"]["total"] == 268
    assert filled["regression"]["all_green"] is True
    partial = acceptance.build_evidence(
        [{"item": "health", "ok": True, "detail": "d"}], regression_total=268, regression_passed=260
    )
    assert partial["regression"]["all_green"] is False
    assert acceptance.evidence_exit_code(partial) == 1


# fn: M05.F01.I02
def test_main_writes_evidence_json_to_work(tmp_path: Path):
    """main 落盘：evidence JSON 写入指定路径（默认 _work/，过程件不入库），exit 0。"""
    out = tmp_path / "acceptance-latest.json"
    code = acceptance.main(["--out", str(out)])
    assert code == 0
    evidence = json.loads(out.read_text("utf-8"))
    assert set(evidence) == {
        "version",
        "generated_at",
        "mode",
        "checks",
        "all_green",
        "regression",
    }
    assert evidence["all_green"] is True


# fn: M05.F01.I02
def test_main_failing_probe_exit_nonzero(tmp_path: Path):
    """main 失败路径：注入失败探针 → exit 非 0，证据回执如实落盘 all_green=false。"""
    out = tmp_path / "acceptance-fail.json"
    code = acceptance.main(
        ["--out", str(out)],
        probes=[("health", lambda _c: {"item": "health", "ok": False, "detail": "注入失败"})],
    )
    assert code != 0
    evidence = json.loads(out.read_text("utf-8"))
    assert evidence["all_green"] is False
