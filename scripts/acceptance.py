"""全链路验收脚本（T17 M05.F01.I01）+ 证据回执（T18 M05.F01.I02）。

形状真源 = v2/v3 design spec §5.7：
- 四能力逐项探活（健康 / 建局+对话含拦截 / 对手结算重放 / 奇遇生成准入），经
  TestClient/内存 app（真仓 data/ 装配，test_api_encounter 的 _real_app 同形），不起服。
- 每项产出 {item, ok, detail}；任一失败 exit 非 0。
- 证据回执 JSON：version/generated_at/mode/四能力逐项结论 + 回归汇总；回归计数由
  CI/调用方填充（脚本不重复跑全量测试，脚本只产出探活面）；落 _work/（过程件不入库，
  正式区/临时区纪律），检入的只有本脚本与 tests/test_acceptance.py。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "backend" / "src"))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from text_rpg.chapters import load_world
from text_rpg.encounters import load_encounter_templates
from text_rpg.engine import GameEngine
from text_rpg.llm import MockLLMClient
from text_rpg.lock_anchors import ANCHORS
from text_rpg.locks import build_registry
from text_rpg.memory import MemoryStore
from text_rpg.npcs import load_npcs
from text_rpg.opponents import load_opponents
from text_rpg.persistence import SessionStore
from text_rpg.routes import build_router

EVIDENCE_VERSION = "3.0.0"
DEFAULT_OUT = _REPO_ROOT / "_work" / "evidence" / "acceptance-latest.json"

# 逐项探活清单（item 名 = 证据回执 checks[].item 取值面）
PROBES: list[tuple[str, object]] = []


def probe(fn):
    """注册装饰器：探活函数登记进 PROBES（顺序即回执 checks 顺序）。"""
    PROBES.append((fn.__name__.removeprefix("probe_"), fn))
    return fn


def build_client() -> TestClient:
    """真仓 data/ 装配内存 app（mock 模式）：真章包+真 NPC+真对手卡+真模板+真锁锚表。"""
    data_dir = _REPO_ROOT / "data"
    world = load_world(data_dir)
    registry = build_registry(world)
    engine = GameEngine(world, registry)
    npcs = load_npcs(data_dir=data_dir)
    opponents = load_opponents(data_dir)
    encounters = load_encounter_templates(data_dir)
    memory = MemoryStore(npcs)
    app = FastAPI()
    app.include_router(
        build_router(
            engine,
            SessionStore(),
            npcs=npcs,
            llm_client=MockLLMClient(),
            memory=memory,
            llm_mode="mock",
            opponents=opponents,
            encounters=encounters,
            lock_anchors=ANCHORS,
        )
    )
    return TestClient(app)


def _new_game(client: TestClient) -> str:
    resp = client.post("/api/games", json={"player_name": "悟空"})
    if resp.status_code != 201:
        raise RuntimeError(f"建局失败：status={resp.status_code} body={resp.text}")
    return resp.json()["id"]


@probe
def probe_health(client: TestClient) -> dict:
    """探活 a：/api/health ok=true 且带 mode 键。"""
    resp = client.get("/api/health")
    body = resp.json()
    ok = resp.status_code == 200 and body.get("ok") is True and "mode" in body
    detail = f"status={resp.status_code} ok={body.get('ok')} mode={body.get('mode')}"
    return {"item": "health", "ok": ok, "detail": detail}


@probe
def probe_talk_interception(client: TestClient) -> dict:
    """探活 b：建局 → talk 红线词「自称神明」→ blocked=true + 拦截回复（护栏全链）。"""
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/npcs/npc_woodcutter/talk",
        json={"text": "你自称神明，方能渡我"},
    )
    body = resp.json()
    ok = (
        resp.status_code == 200
        and body.get("blocked") is True
        and "自称神明" in body.get("guard_evidence", [])
        and "此话不可说" in body.get("reply", "")
    )
    detail = f"status={resp.status_code} blocked={body.get('blocked')} evidence={body.get('guard_evidence')}"
    return {"item": "talk_interception", "ok": ok, "detail": detail}


@probe
def probe_oppose_replay(client: TestClient) -> dict:
    """探活 c：两同构局（各自建局）同 choice 带 oppose → oppose_ledger 全等。

    对手取 opp_prince_dragon（对手注册表内实卡，非章包挂载点——routes 只做注册表成员预检）；
    choice 取无锁不放终局的 c_take_rations。"""
    game_ids = [_new_game(client) for _ in range(2)]
    ledgers = []
    for game_id in game_ids:
        resp = client.post(
            f"/api/games/{game_id}/choice",
            json={
                "scene_id": "s01_village",
                "choice_id": "c_take_rations",
                "oppose": "opp_prince_dragon",
            },
        )
        if resp.status_code != 200 or "oppose_ledger" not in resp.json():
            raise RuntimeError(f"对抗结算探针失败：status={resp.status_code} body={resp.text}")
        ledgers.append(resp.json()["oppose_ledger"])
    a, b = ledgers
    ok = (
        a == b
        and len(a) == 2
        and all(set(row) == {"seq", "actor", "action", "power", "roll"} for row in a)
        and a[0]["actor"] == "player"
        and a[1]["actor"] == "opp_prince_dragon"
    )
    detail = f"两局账本全等={a == b} 步数={len(a)} 步"
    return {"item": "oppose_replay", "ok": ok, "detail": detail}


@probe
def probe_encounter_admission(client: TestClient) -> dict:
    """探活 d：奇遇生成准入（enc_fruit_grove）→ 200，临时场景入章且 GET 可见。"""
    game_id = _new_game(client)
    resp = client.post(
        f"/api/games/{game_id}/encounters",
        json={"template_id": "enc_fruit_grove"},
    )
    body = resp.json()
    scene_id = body.get("scene_id")
    got = client.get(f"/api/games/{game_id}/scenes/{scene_id}") if scene_id else None
    ok = (
        resp.status_code == 200
        and bool(scene_id)
        and bool(body.get("locks"))
        and got is not None
        and got.status_code == 200
        and got.json().get("scene", {}).get("id") == scene_id
    )
    detail = (
        f"status={resp.status_code} template={body.get('template_id')} "
        f"scene={scene_id} visible={bool(got) and got.status_code == 200}"
    )
    return {"item": "encounter_admission", "ok": ok, "detail": detail}


def run_probes(probes=None) -> list[dict]:
    """逐项探活汇总：默认跑 PROBES 全清单，可注入探针清单（测试失败路径用）。"""
    if probes is None:
        probes = PROBES
    client = build_client()
    checks = []
    for item, fn in probes:
        try:
            checks.append(fn(client))
        except Exception as exc:  # 探针抛错也算失败项（fail-visible）
            checks.append({"item": item, "ok": False, "detail": f"探针异常：{exc}"})
    return checks


def build_evidence(checks, regression_total=None, regression_passed=None) -> dict:
    """证据回执组装：schema = version/generated_at/mode/checks/all_green/regression。

    回归汇总默认空（由 CI/调用方填充），显式传 total+passed 则落地并算 all_green。
    """
    all_green = bool(checks) and all(c["ok"] for c in checks)
    regression_all_green = None
    if regression_total is not None and regression_passed is not None:
        regression_all_green = regression_passed == regression_total
    return {
        "version": EVIDENCE_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "mock",
        "checks": checks,
        "all_green": all_green,
        "regression": {
            "passed": regression_passed,
            "total": regression_total,
            "all_green": regression_all_green,
            "filled_by": "caller/CI",
        },
    }


def evidence_exit_code(evidence: dict) -> int:
    """exit code：探活面与回归面（若已填充）任一不绿 → 1；全绿 → 0。"""
    if not evidence["all_green"]:
        return 1
    regression = evidence["regression"]
    if regression["all_green"] is False:
        return 1
    return 0


def main(argv=None, probes=None) -> int:
    """跑探活 + 落证据回执 + exit code；回归计数经 CLI 由调用方/CI 传入。"""
    parser = argparse.ArgumentParser(description="四能力全链路验收探活 + 证据回执")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="证据回执落盘路径")
    parser.add_argument("--regression-total", type=int, default=None)
    parser.add_argument("--regression-passed", type=int, default=None)
    args = parser.parse_args(argv)
    evidence = build_evidence(
        run_probes(probes=probes),
        regression_total=args.regression_total,
        regression_passed=args.regression_passed,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), "utf-8")
    for check in evidence["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        print(f"[{mark}] {check['item']}: {check['detail']}")
    print(f"all_green={evidence['all_green']} evidence={out_path}")
    return evidence_exit_code(evidence)


if __name__ == "__main__":
    sys.exit(main())
