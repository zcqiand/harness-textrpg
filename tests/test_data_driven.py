"""Task 9：数据驱动实证——「锁的断言跟着数据走，不跟测试走」。

把 repo 的 data/ 整目录复制进 tmp_path，只改一处章包 JSON
（lock_ch03_fan_gate 的 requires item 换成不存在的 "nonexistent_key"），
再用同一套真加载器 + 引擎重判：同一把锁对同一状态（持有芭蕉扇）
的裁决从放行翻成锁死，missing 首条直接点名被改的 key——证明锁行为
完全由章包数据驱动，测试与引擎未硬编码任何锁逻辑。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from text_rpg.chapters import load_world
from text_rpg.engine import GameEngine
from text_rpg.locks import build_registry

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"


def test_mutation_changes_lock_verdict(tmp_path):
    """只改数据不改代码：fan_gate 对持扇者从放行翻成锁死，missing 点名新 key。"""
    data_dir = tmp_path / "data"
    shutil.copytree(_REPO_DATA, data_dir)
    pack_path = data_dir / "chapters" / "ch03-flaming-mountain.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    gate = next(lk for lk in pack["locks"] if lk["id"] == "lock_ch03_fan_gate")
    assert gate["requires"] == [{"item": "banana_leaf_fan"}]
    gate["requires"] = [{"item": "nonexistent_key"}]
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    world = load_world(data_dir)
    engine = GameEngine(world, build_registry(world))
    state = engine.new_game("玄奘")
    state.backpack.append("banana_leaf_fan")
    state.current_chapter = "ch03"
    state.current_scene = "s03_pass_gate"
    rows = {r["id"]: r for r in engine.choices_view(state)}
    assert rows["c_cross"]["locked"] is True
    assert rows["c_cross"]["missing"] == [
        {"type": "item", "key": "nonexistent_key", "have": False, "need": True}
    ]
