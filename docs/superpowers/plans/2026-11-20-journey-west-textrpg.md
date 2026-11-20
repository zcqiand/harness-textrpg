# harness-textrpg 西游记章回文字冒险 RPG 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 书三第 7 案例仓 harness-textrpg 的 ch12 面一批交付：3 回西游记文字冒险（分支锁突出点）+ Python/FastAPI 引擎 + React 四态前端 + 部署五件套。

**Architecture:** 数据驱动的章回包（`data/chapters/*.json`）经 `chapters.py` 加载为 World；锁注册表=章包 locks 并集，启动自审（悬空引用/空 denial/锚覆盖）；引擎 `engine.py` 做门控→效果→结局判定，锁评估只在后端求值一次；FastAPI 五端点 + 内存会话库；React 建局/探索/反馈/结局图四态。

**Tech Stack:** Python 3.11+ / FastAPI / uvicorn / pytest（钉版随书一 text-adventure-rpg `version-lock.json`）；React 18 / TypeScript / Vite / vitest 3（钉版随 harness-starter）。

**Spec:** `docs/superpowers/specs/2026-11-20-textrpg-journey-west-design.md`（已批；schema 与锁契约以该文档 §5.1 为准，本计划是它的展开）

## Global Constraints

- TDD：每模块先写失败测试再实现；锁的断言先于锁的实现。
- 依赖钉死于 `version-lock.json`，不引入 lock 外的库；钉版来源：后端抄 `output/text-adventure-rpg/version-lock.json`，前端主要钉版抄 `output/harness-starter/package.json`。
- mock-friendly：`pytest -q` 无 Key、无网、无 Docker 全绿。
- 数据驱动：场景/抉择/锁/结局/初始状态全部来自 `data/`，禁止硬编码进 Python。
- npm 一律 `--registry=https://registry.npmmirror.com`。
- 零伪代码：无 `pass`/`TODO`/`...` 占位。
- `APP_PORT` fail-fast 必填，禁兜底默认。
- 过程件进 `_work/`（整目录 .gitignore）；正式件同名唯一。
- tag 规约 `v<MAJOR>.<MINOR>.<PATCH>-<YYYYMMDD>`，禁删/覆盖，禁 `git push --tags`。
- commit 尾注逐字 `Co-Authored-By: Claude Code <noreply@anthropic.com>`；禁止 `git add -A`（逐文件 add）。
- 分支名 `main`（家族先例：deploy 脚本自 `refs/heads/main` 拉取）。
- commit message 用 conventional commits（feat/test/docs/chore/fix）。

## Review Focus

1. **章回 JSON 改锁条件后断言必须红**（数据驱动实证）→ `tests/test_data_driven.py`（Task 9）。
2. **空 denial / 悬空 lock 引用 / 缺锚**必须让启动自审报 errors → `tests/test_registry_audit.py` 三失败方向（Task 4）。
3. **服务重启后旧会话**：GET/POST `/api/games/{id}` 404，前端降级回建局 → `tests/test_api.py`（Task 6）+ vitest（Task 10）。
4. **非法提交**（未知 scene_id/choice_id、game_over 后再提交）→ 400 不炸 → `tests/test_api.py`（Task 6）。
5. **effects 负增量与顺序执行**（属性可减、效果按数组序生效）→ `tests/test_contracts.py`（Task 2）。

---

## 文件结构总览

```
backend/
  pyproject.toml
  src/text_rpg/
    __init__.py  contracts.py  chapters.py  locks.py  lock_anchors.py
    engine.py  persistence.py  routes.py  webserver.py
data/
  game-start.json
  chapters/ch01-two-boundary.json  ch02-white-bone.json  ch03-flaming-mountain.json
frontend/
  package.json  vite.config.ts  tsconfig.json  vitest.config.ts
  src/main.tsx  App.tsx  api.ts  types.ts
  src/views/SetupView.tsx  JourneyView.tsx  EndingView.tsx
  src/__tests__/…（vitest 四组）
backend/Dockerfile  frontend/Dockerfile
.github/workflows/ci.yml
deploy/harness-textrpg.sh  deploy/nginx-vps.conf.example
tests/（pytest，仓根）
version-lock.json  CLAUDE.md  .gitignore
```

**核心签名（各任务按此对接，不得改名）：**

```python
# contracts.py
Missing = dict  # {"type": "flag"|"attr"|"item", "key": str, "have": Any, "need": Any}
def evaluate(conditions: list[dict], state: "GameState") -> "EvalResult"   # .satisfied: bool; .missing: list[Missing]
def apply(effects: list[dict], state: "GameState") -> list[str]             # 返回可读 message 串（按数组序执行）

# chapters.py（dataclass）
Scene(id, text, choices: list[Choice]); Choice(id, text, lock: str|None, goto: str|None, effects: list|None)
LockDef(id, requires: list[dict], denial: str, effects: list|None, chapter_id: str)
EndingDef(id, title, requires: list[dict], mid_chapter: bool)
Chapter(id, title, entry_locks: list[str], locks: list[LockDef], scenes: list[Scene], endings: list[EndingDef])
World(chapters: list[Chapter], start_attributes: dict[str, int], start_backpack: list[str])
def load_world(data_dir: Path) -> World    # FileNotFoundError/JSONDecodeError → 可读错误（无 traceback 路径）

# locks.py
def build_registry(world: World) -> dict[str, LockDef]                       # key=lock id
def audit(world: World, registry: dict, anchors: dict) -> "AuditReport"     # .errors/.warnings: list[str]

# lock_anchors.py
ANCHORS: dict[str, dict]  # {lock_id: {"pass": "<pytest 用例 id>", "deny": "<pytest 用例 id>"}}

# engine.py
class GameEngine:
    def __init__(self, world: World, registry: dict[str, LockDef]): ...
    def new_game(self, player_name: str) -> GameState
    def choices_view(self, state: GameState) -> list[dict]   # {id,text,locked,missing,denial}
    def endings_view(self, state: GameState) -> list[dict]   # {id,title,satisfied,missing}
    def chapters_view(self, state: GameState) -> list[dict]  # {id,title,locked}
    def submit_choice(self, state: GameState, scene_id: str, choice_id: str) -> "ChoiceResult"
# ChoiceResult(messages: list[str], state: GameState, unlocked_locks: list[str], game_over: bool, ending: dict|None)
```

**GameState 形状**（dataclass，API 序列化源）：`{id, player_name, attributes: dict[str,int], backpack: list[str], flags: set[str]→序列化为 sorted list, current_chapter, current_scene, unlocked_locks: list[str], game_over: bool, ending: dict|None}`

---

### Task 1: 仓库骨架与门禁底座

**Files:**
- Create: `CLAUDE.md`, `version-lock.json`, `.gitignore`, `backend/pyproject.toml`, `backend/src/text_rpg/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: 可 `pip install -e ./backend` 的空包 `text_rpg`；`pytest -q` 收集到冒烟测试。

- [ ] **Step 1**: 写 `CLAUDE.md`（≤60 行：项目定位=书三第 7 案例仓；铁律照本计划 Global Constraints 抄；验收命令三段：pytest / npm build+test / 冒烟；数据驱动与锁契约两节指向 spec）。
- [ ] **Step 2**: 写 `version-lock.json`（后端钉版抄 `output/text-adventure-rpg/version-lock.json` 的 fastapi/uvicorn/pydantic/pytest 段；前端段记 react 18 / vite / vitest 3 / typescript，与 harness-starter 同版）。
- [ ] **Step 3**: 写 `.gitignore`：`node_modules/`、`dist/`、`build/`、`__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`**/_work/`、`.vite/`。
- [ ] **Step 4**: `backend/pyproject.toml`（setuptools，`package-dir`=`src`，dependencies=version-lock 钉版）；`backend/src/text_rpg/__init__.py` 含 `__version__ = "0.1.0"`。
- [ ] **Step 5**: `tests/test_smoke.py`：`def test_package_importable(): import text_rpg; assert text_rpg.__version__ == "0.1.0"`。
- [ ] **Step 6**: `git branch -m master main`（若当前是 master）；`pip install -e ./backend && pytest -q` → 1 passed。
- [ ] **Step 7**: Commit：`chore: 仓库骨架——CLAUDE/version-lock/pyproject/pytest 冒烟`。

### Task 2: contracts.py 条件求值与效果执行

**Files:**
- Create: `backend/src/text_rpg/contracts.py`
- Test: `tests/test_contracts.py`

**Interfaces:**
- Consumes: GameState 形状（本任务内先以 `types.SimpleNamespace`/轻量 dataclass 占位亦可，但字段名必须与「核心签名」一致）。
- Produces: `evaluate(conditions, state) -> EvalResult`、`apply(effects, state) -> list[str]`、`EvalResult(satisfied, missing)`。

- [ ] **Step 1: 失败测试**（覆盖 Review Focus 5）：

```python
def test_flag_condition_true_and_missing():
    st = make_state(flags={"helped_woodcutter"})
    r = evaluate([{"flag": "helped_woodcutter"}], st)
    assert r.satisfied and r.missing == []
    r2 = evaluate([{"flag": "nope"}], st)
    assert not r2.satisfied
    assert r2.missing == [{"type": "flag", "key": "nope", "have": False, "need": True}]

def test_attr_threshold_and_missing_detail():
    st = make_state(attributes={"insight": 1})
    r = evaluate([{"attr": "insight", "op": ">=", "value": 3}], st)
    assert not r.satisfied
    assert r.missing == [{"type": "attr", "key": "insight", "have": 1, "need": 3}]

def test_item_and_multi_condition_and_semantics():
    st = make_state(backpack=["dry_rations"])
    r = evaluate([{"item": "dry_rations"}, {"item": "fan"}], st)
    assert not r.satisfied and r.missing[0]["type"] == "item"

def test_effects_order_and_negative_delta():
    st = make_state(attributes={"insight": 3}, backpack=["dry_rations"])
    msgs = apply([{"attr": {"insight": -1}}, {"item_remove": "dry_rations"},
                  {"flag": "done"}, {"item_add": "fan"}], st)
    assert st.attributes["insight"] == 2 and st.backpack == ["fan"] and "done" in st.flags
    assert len(msgs) == 4
```

- [ ] **Step 2**: `pytest tests/test_contracts.py -v` → FAIL（module 不存在）。
- [ ] **Step 3**: 实现 `contracts.py`：`evaluate` 全 AND；attr 支持算子 `>=` 与 `==`；条件/效果形状不符 raise `ValueError`（可读中文信息）。GameState 字段不足时以 `getattr` 缺省安全取值（flags 缺省空集、backpack 缺省空表、attributes 缺省空表）。
- [ ] **Step 4**: `pytest tests/test_contracts.py -v` → PASS。
- [ ] **Step 5**: Commit：`feat(contracts): 锁条件三类求值 + 效果四类执行`。

### Task 3: chapters.py 数据加载 + game-start.json

**Files:**
- Create: `backend/src/text_rpg/chapters.py`, `data/game-start.json`, `data/chapters/.keep`
- Test: `tests/test_chapters.py`

**Interfaces:**
- Produces: `load_world(data_dir: Path) -> World`；五个 dataclass（Scene/Choice/LockDef/EndingDef/Chapter/World，字段见核心签名）；空章目录加载不炸（World.chapters==[]）——本任务 data 里只有 game-start.json。

- [ ] **Step 1: 失败测试**：

```python
def test_load_start_state(tmp_path):
    # tmp_path 里放最小 game-start.json：{"attributes": {"insight": 1}, "backpack": []}
    world = load_world(tmp_path)
    assert world.start_attributes == {"insight": 1} and world.start_backpack == []

def test_missing_data_dir_readable_error(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_world(tmp_path / "nope")
    assert "game-start.json" in str(e.value)   # 可读错误，不含 traceback 路径

def test_empty_chapters_dir_ok(tmp_path):
    world = load_world(tmp_path)
    assert world.chapters == []
```

- [ ] **Step 2**: FAIL 后实现：`load_world` 读 `game-start.json` + 遍历 `chapters/*.json`（按文件名序）；章包字段映射到 dataclass；`game-start.json` 缺失/坏 JSON 抛带文件名的可读错误。
- [ ] **Step 3**: 写真实 `data/game-start.json`：`{"attributes": {"insight": 1}, "backpack": []}`。
- [ ] **Step 4**: PASS 后 Commit：`feat(chapters): 章回包与开局数据加载器`。

### Task 4: locks.py 注册表与启动自审 + 锚表

**Files:**
- Create: `backend/src/text_rpg/locks.py`, `backend/src/text_rpg/lock_anchors.py`
- Test: `tests/test_registry_audit.py`

**Interfaces:**
- Consumes: `World`/`LockDef`（Task 3）、`ANCHORS`（本任务建空表骨架）。
- Produces: `build_registry(world)`、`audit(world, registry, anchors) -> AuditReport(.errors, .warnings)`。

- [ ] **Step 1: 失败测试**（Review Focus 2，三失败方向 + 一绿向）：

```python
def _world_with(chapter_dict): ...   # 造单章 World 的测试工厂

def test_audit_clean_world_has_no_errors(): ...          # 锁齐、denial 非空、锚覆盖 → errors == []

def test_audit_dangling_choice_lock_reference_is_error():
    # choice.lock 指向不存在的 lock id → errors 含该 id，且含 "悬空" 字样
def test_audit_empty_denial_is_error(): ...
def test_audit_missing_anchor_is_error():
    # 锁存在但 ANCHORS 无条目 → errors 提示缺锚
def test_registry_is_union_of_chapter_locks():
    # 两章各含锁 → registry keys = 并集，LockDef.chapter_id 正确
```

- [ ] **Step 2**: FAIL 后实现：`build_registry`（章包 locks 并集）+ `audit` 三查（遍历章包 choices 收集 `choice.lock` 引用 → 悬空即 error；`denial.strip()==""` 即 error；`lock_id not in anchors` 即 error）。`AuditReport` 为 dataclass。
- [ ] **Step 3**: `lock_anchors.py` 先建空 `ANCHORS: dict = {}`（Task 7 起逐章补条目）。
- [ ] **Step 4**: PASS 后 Commit：`feat(locks): 锁注册表并集 + 启动自审三查 + 锚表骨架`。

### Task 5: engine.py 状态机

**Files:**
- Create: `backend/src/text_rpg/engine.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: Task 2/3/4 全部。
- Produces: `GameEngine` 五方法与 `GameState`、`ChoiceResult`（核心签名）。**章回推进规则**：抉择 effects 写入 `chapter_XX_complete` 后，引擎把 `current_chapter` 推进到下一章、`current_scene` 置为下一章首个场景，前提是下一章 `entry_locks` 全满足；不满足则停在原章并给出 denial message。**结局判定**：每次 `submit_choice` 效果执行后，按章声明序（ch01→ch03 顺序拼接）找第一条 `requires` 满足的结局 → `game_over=True, ending={id,title}`。

- [ ] **Step 1: 失败测试**（用两个内存小章包构造，不依赖真实 data）：

```python
def test_new_game_uses_start_state(): ...            # 属性/背包来自 world.start_*；首个场景=ch01 首场景
def test_locked_choice_rejected_with_denial(): ...   # 提交挂锁抉择，条件不满足 → 抉择被拒，messages 含 denial，状态不变
def test_choice_effects_and_goto_applied(): ...      # 满足条件的挂锁抉择 → effects 生效 + goto 换场景 + unlocked_locks 含锁 id
def test_chapter_advance_on_complete_flag(): ...     # 写 chapter_01_complete → current_chapter=ch02、场景=ch02 首场景
def test_chapter_advance_blocked_by_entry_lock(): ...
def test_mid_chapter_ending_fires_and_locks_input(): # ending 触发后 game_over=True；再 submit_choice raise ValueError("游戏已结束")
def test_choices_view_reports_missing_detail(): ...  # choices_view 每条含 locked/missing/denial；缺失明细含 have/need
def test_endings_view_satisfied_and_missing(): ...   # endings_view 按 ch 序拼接，satisfied/missing 正确
```

- [ ] **Step 2**: FAIL 后实现（约 150 行：门控 → `contracts.apply` → goto → 章推进 → 结局判定）。
- [ ] **Step 3**: PASS 后 Commit：`feat(engine): 门控-效果-章推进-结局判定状态机`。

### Task 6: persistence + routes + webserver（API 面）

**Files:**
- Create: `backend/src/text_rpg/persistence.py`, `backend/src/text_rpg/routes.py`, `backend/src/text_rpg/webserver.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 5 全部。
- Produces: FastAPI `app`（`routes.build_router(engine, store)`）；`webserver.main()` 读 `APP_PORT`（缺失 raise `RuntimeError("缺少环境变量 APP_PORT")`，禁兜底）。

- [ ] **Step 1: 失败测试**（httpx/TestClient，Review Focus 3/4）：

```python
def test_health(): ...                               # GET /api/health → {"ok": true, "mode": "local"}
def test_chapters_catalog_static(): ...              # GET /api/chapters → {"chapters":[{id,title,order}]}，无 locked 字段
def test_create_game_201_and_empty_name_400(): ...
def test_get_game_embeds_choices_endings_chapters_views(): ...  # 读局含 choices/endings/chapters 三视图 + state
def test_submit_choice_messages_state_unlocked(): ...
def test_unknown_game_404(): ...                     # GET/POST 不存在 id → 404
def test_unknown_scene_or_choice_400(): ...
def test_choice_after_game_over_400(): ...
def test_session_gone_after_store_reset(): ...       # 清空 store（模拟重启）→ 404
```

- [ ] **Step 2**: FAIL 后实现：`persistence.py`（`SessionStore`：`dict[str, GameState]`，`create()` 产 uuid id，`get/put/delete_all`）；`routes.py` 五端点按 spec §5.3 形状（`GET /api/games/{id}` 内嵌 `choices_view/endings_view/chapters_view`）；`webserver.py` uvicorn 入口。
- [ ] **Step 3**: PASS + 全量 `pytest -q` 绿。Commit：`feat(api): 五端点 + 内存会话库 + APP_PORT fail-fast`。

### Task 7: 回 1 数据包「两界山前」+ 锁断言实证

**Files:**
- Create: `data/chapters/ch01-two-boundary.json`
- Modify: `backend/src/text_rpg/lock_anchors.py`（补 ch01 锚）
- Test: `tests/test_lock_assertions.py`, `tests/test_world_content.py`

**Interfaces:**
- Consumes: Task 3-5。**锁断言测试是通用参数化**：读 `ANCHORS` 表，对每把锁用「条件满足构造器」与「缺条件构造器」各跑一条。
- Produces: ch01 章包（下列 id/条件为契约，文案措辞自由）；通用锁断言测试框架。

**章包契约（场景 5 / 锁 3 / 结局 1 / 旗标 3 / 物品 1）：**

- 场景与抉择：`s01_village`（`c_take_rations` effects `item_add dry_rations`；`c_talk_woodcutter` effects `flag helped_woodcutter`+`attr insight+1`，goto `s01_woodcutter_hut`；`c_leave` **lock `lock_ch01_rations_gate`**，goto `s01_foothill`）→ `s01_woodcutter_hut`（`c_listen` effects `attr insight+1`，goto `s01_village`；`c_visit_temple` goto `s01_temple`）→ `s01_temple`（`c_spot_mural` **lock `lock_ch01_temple_spot`** effects `attr insight+1`；`c_leave_temple` goto `s01_village`）→ `s01_foothill`（`c_shortcut` **lock `lock_ch01_shortcut`** effects `flag chapter_01_complete`；`c_long_way` goto `s01_cliff`）→ `s01_cliff`（`c_press_on` effects `flag went_long_way`）
- 锁：`lock_ch01_rations_gate` requires `[{"item":"dry_rations"}]`，denial 提「干粮」；`lock_ch01_temple_spot` requires `[{"attr":"insight","op":">=","value":2}]`，denial 提「悟性」；`lock_ch01_shortcut` requires `[{"flag":"helped_woodcutter"}]`，denial 提「樵夫指路」。
- 结局：`turned_back`「半途折返」requires `[{"flag":"went_long_way"}]`，`mid_chapter: true`。

- [ ] **Step 1: 失败测试**——`tests/test_lock_assertions.py` 通用参数化（先只对 ch01 三锁红）：

```python
def _satisfy(requires, state): ...   # flag→flags.add / attr→attributes[key]=value / item→backpack.append
@pytest.mark.parametrize("lock_id", sorted(ANCHORS))
def test_lock_pass(lock_id): ...     # 满足 requires → choices_view 该锁对应抉择 locked=False
@pytest.mark.parametrize("lock_id", sorted(ANCHORS))
def test_lock_deny(lock_id): ...     # 缺条件 → locked=True 且 missing 首条与 requires 首条同 type/key，denial 非空
def test_anchors_cover_registry():   # audit(world, registry, ANCHORS).errors == []（全量数据）
```

  及 `tests/test_world_content.py`：`test_ch01_loads_and_starts`（load_world 后 ch01 在首位、5 场景 3 锁 1 结局）、`test_turned_back_ending_fires`（走 long_way 线 → game_over 且 ending id == "turned_back"）。
- [ ] **Step 2**: FAIL（无数据/无锚）后写章包 JSON + ANCHORS 补 3 条目（`{"pass": "test_lock_pass[lock_ch01_…]", "deny": "test_lock_deny[lock_ch01_…]"}` 形状）。
- [ ] **Step 3**: `pytest tests/test_lock_assertions.py tests/test_world_content.py -v` → PASS；全量 `pytest -q` 绿。Commit：`feat(data): 回1 两界山前——3 锁 1 结局 + 通用锁断言框架`。

### Task 8: 回 2 数据包「三打白骨精」

**Files:**
- Create: `data/chapters/ch02-white-bone.json`
- Modify: `backend/src/text_rpg/lock_anchors.py`
- Test: `tests/test_world_content.py`（追加）

**Interfaces:**
- Consumes: Task 7 的断言框架（新锁自动进参数化）。

**章包契约（场景 6 / 锁 4 / 结局 1 / 旗标 6）：**

- `entry_locks: ["lock_ch02_entry"]`；`lock_ch02_entry` requires `[{"flag":"chapter_01_complete"}]`，denial 提「第一回未了」。
- 场景链：`s02_first_meet`（`c_observe` effects `flag white_bone_evidence_1`+`attr insight+1`，goto `s02_after_first`；`c_strike_1` effects `flag struck_first`，goto `s02_after_first`）→ `s02_after_first`（`c_move_on` goto `s02_second_meet`）→ `s02_second_meet`（`c_verify` effects `flag white_bone_evidence_2`，goto `s02_after_second`；`c_strike_2` **lock `lock_ch02_second_strike`**，goto `s02_after_second`）→ `s02_after_second`（`c_report` **lock `lock_ch02_report_tang`** effects `flag tang_convinced`，goto `s02_third_meet`；`c_proceed` goto `s02_third_meet`）→ `s02_third_meet`（`c_strike_3` **lock `lock_ch02_third_strike`** effects `flag bone_spirit_exposed`+`flag chapter_02_complete`，goto `s03_approach`；`c_force_strike` effects `flag struck_without_evidence`，goto `s02_exposed`）→ `s02_exposed`（无抉择）
- 锁：`lock_ch02_second_strike` requires `[{"flag":"white_bone_evidence_1"}]`；`lock_ch02_third_strike` requires `[{"flag":"white_bone_evidence_2"}]`，denial 提「二验」；`lock_ch02_report_tang` requires `[{"attr":"insight","op":">=","value":3}]`，denial 提「悟性」。
- 结局：`banished_early`「被逐早终」requires `[{"flag":"struck_without_evidence"}]`，`mid_chapter: true`。

- [ ] **Step 1: 失败测试**（追加 `test_world_content.py`）：`test_ch02_entry_lock_blocks_until_ch01_complete`（直接构造 ch02 为当前章、无旗标 → chapters_view ch02 locked=True）、`test_full_evidence_line_exposes_spirit`（observe→verify→strike_3 → `bone_spirit_exposed` ∈ flags 且章推进到 ch03）、`test_force_strike_ends_banished`（force 线 → ending == "banished_early"）。
- [ ] **Step 2**: 写章包 + ANCHORS 补 4 条目。PASS + 全量绿。Commit：`feat(data): 回2 三打白骨精——4 锁 1 结局（跨回旗标种子）`。

### Task 9: 回 3 数据包「火焰山」+ 数据驱动实证 + 全门自检绿

**Files:**
- Create: `data/chapters/ch03-flaming-mountain.json`
- Modify: `backend/src/text_rpg/lock_anchors.py`
- Test: `tests/test_world_content.py`（追加）, `tests/test_data_driven.py`

**章包契约（场景 5 / 锁 5 / 结局 2 / 旗标 3 / 物品 1）：**

- `entry_locks: ["lock_ch03_entry"]`（requires `chapter_02_complete`，denial 提「第二回未了」）。
- 场景链：`s03_approach`（`c_to_cave` goto `s03_cave_door`）→ `s03_cave_door`（`c_request` **lock `lock_ch03_fan_request`** goto `s03_plea`；`c_snatch` goto `s03_snatch`）→ `s03_plea`（`c_appeal` **lock `lock_ch03_smart_fan`** effects `item_add banana_leaf_fan`，goto `s03_pass_gate`）→ `s03_snatch`（`c_grab_forced` effects `item_add banana_leaf_fan`+`flag suspect_fake`，goto `s03_pass_gate`）→ `s03_pass_gate`（`c_discern` **lock `lock_ch03_discern_fan`** effects `flag true_fan`；`c_cross` **lock `lock_ch03_fan_gate`** effects `flag crossed_mountain`，goto `s03_summit`）→ `s03_summit`（无抉择）
- 锁：`lock_ch03_fan_request` requires `[{"flag":"tang_convinced"}]`（**跨回锁**：回 2 的旗标开回 3 的门），denial 提「师父未曾信你」；`lock_ch03_smart_fan` requires `[{"flag":"tang_convinced"},{"attr":"insight","op":">=","value":3}]`；`lock_ch03_discern_fan` requires `[{"attr":"insight","op":">=","value":4}]`；`lock_ch03_fan_gate` requires `[{"item":"banana_leaf_fan"}]`，denial 提「芭蕉扇」。
- 结局（顺序即判定序，跨章拼接）：`true_form`「现形归真」requires `[{"flag":"bone_spirit_exposed"},{"flag":"true_fan"}]`；`west_won`「借扇西行」requires `[{"flag":"crossed_mountain"}]`。

- [ ] **Step 1: 失败测试**：`test_cross_chapter_lock_needs_ch02_flag`（tang_convinced 缺 → fan_request locked）、`test_smart_line_reaches_true_form`（全德线 → ending == "true_form"）、`test_snatch_line_reaches_west_won`（强抢线 → "west_won"）、`test_registry_audit_full_green`（12 锁 12 锚 audit errors==[]）。
- [ ] **Step 2**: `tests/test_data_driven.py`（Review Focus 1）：

```python
def test_mutation_changes_lock_verdict(tmp_path):
    # 复制 data/ 到 tmp_path，把 lock_ch03_fan_gate.requires 的 item 改成 "nonexistent_key"
    # → 该锁对持有芭蕉扇的状态 locked=True，missing[0].key == "nonexistent_key"
```

- [ ] **Step 3**: 写章包 + ANCHORS 补 5 条目 → 全量 `pytest -q` 绿（≥12 锚 × 2 参数化 + 其余）。Commit：`feat(data): 回3 火焰山——跨回锁收官 + 数据驱动实证`。

### Task 10: 前端脚手架 + api client + 建局态

**Files:**
- Create: `frontend/`（vite react-ts 模板）、`frontend/src/types.ts`, `frontend/src/api.ts`, `frontend/src/App.tsx`, `frontend/src/views/SetupView.tsx`, `frontend/src/__tests__/setup.test.tsx`
- Modify: `.gitignore`（必要时补 node_modules/dist）

**Interfaces:**
- Produces: `types.ts` 全部 API 响应类型（GameView/ChoiceView/EndingView/ChapterView，字段对齐 Task 6 响应体）；`api.ts`：`createGame(name)`, `submitChoice(gameId, sceneId, choiceId)`, `getGame(gameId)`, `getChapters()`——同源相对 `/api`。

- [ ] **Step 1**: 脚手架：vite react-ts 模板（npm 走 npmmirror）；devDependencies 补 vitest 3 / jsdom / @testing-library/react / @testing-library/user-event / @testing-library/jest-dom（版本随 harness-starter）；`npm run test` 脚本=`vitest run`；`vitest.config.ts`（environment jsdom）。
- [ ] **Step 2**: 失败测试 `setup.test.tsx`：渲染 App（mock api）→ 输入名号「悟空」→ 点击开始 → 调用了 `createGame("悟空")` 并进入探索视图（探索视图本任务先渲染占位文案）。
- [ ] **Step 3**: 实现 `types.ts`/`api.ts`/`SetupView`/`App` 最小闭环。
- [ ] **Step 4**: `npm run test` 绿 + `npm run build`（tsc strict）零错误。Commit：`feat(web): 前端脚手架 + api client + 建局态`。

### Task 11: 章回探索态 + 锁徽标/条件明细

**Files:**
- Create: `frontend/src/views/JourneyView.tsx`
- Test: `frontend/src/__tests__/journey.test.tsx`

- [ ] **Step 1: 失败测试**（Review Focus 3 前端侧）：

```tsx
// mock getGame 返回含 choices 两态：一未锁、一 locked 且 missing=[{type:"item",key:"dry_rations",have:0,need:1}] denial 非空
test("未锁抉择可点击并提交 submitChoice"); 
test("锁抉择灰显（disabled）且挂锁徽标");
test("点锁徽标弹条件明细，展示缺失 type/key 与 denial 文案");
```

- [ ] **Step 2**: 实现 JourneyView：场景文案 + 抉择列表（锁抉择 `disabled` + 徽标按钮，点击弹明细面板）+ 会话失效（api 404）→ 回建局态。
- [ ] **Step 3**: vitest 绿 + build 零错误。Commit：`feat(web): 章回探索态——锁徽标与条件明细`。

### Task 12: 抉择反馈态（解锁高亮 1.5s）

**Files:**
- Modify: `frontend/src/views/JourneyView.tsx`
- Test: `frontend/src/__tests__/unlock.test.tsx`

- [ ] **Step 1: 失败测试**：submitChoice 响应 `unlocked_locks=["lock_ch01_rations_gate"]` → 对应抉择徽标变「解锁」态并高亮；`vi.useFakeTimers()` 推进 1.5s 后高亮消退；响应 `unlocked_locks=[]` 时无高亮。
- [ ] **Step 2**: 实现（`useEffect` + timer，组件卸载/新抉择清理 timer——starter 终审同款教训：per-choice timer map，重开清理）。
- [ ] **Step 3**: 绿 + build。Commit：`feat(web): 解锁高亮反馈 1.5s`。

### Task 13: 结局图态（localStorage 跨局 + 缺失条件链）

**Files:**
- Create: `frontend/src/views/EndingView.tsx`
- Test: `frontend/src/__tests__/ending.test.tsx`

- [ ] **Step 1: 失败测试**：game_over 响应 → 渲染 EndingView，本局 ending 点亮并写 localStorage 键 `htextrpg-endings`；重开一局到达另一结局 → 两枚点亮；未达结局渲染 `missing` 条件链（mock 数据含 `{id,title,satisfied:false,missing:[…]}`）；localStorage 读失败（throw）时页面照常渲染全灰（try/catch 包裹）。
- [ ] **Step 2**: 实现 EndingView：4 结局卡片图 + 已达点亮（localStorage 合并）+ 未达缺失链 + 「再入轮回」按钮回建局态（清当前会话 id，保留结局进度）。
- [ ] **Step 3**: 绿 + build + 全前端 `npm run test`。Commit：`feat(web): 结局图态——跨局点亮与缺失条件链`。

### Task 14: 部署五件套

**Files:**
- Create: `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf`, `.github/workflows/ci.yml`, `deploy/harness-textrpg.sh`, `deploy/nginx-vps.conf.example`

- [ ] **Step 1**: `backend/Dockerfile`：`python:3.11-slim`，`pip install --no-cache-dir -e ./backend`（照 agent 家族 api 形状：uvicorn host=container 单层，`CMD` 读 `APP_PORT`）。
- [ ] **Step 2**: `frontend/Dockerfile`：node 构建（npm ci 走 npmmirror；rollup 版本 override 随 harness-starter 防 musl 坑）→ `nginx:alpine`；`nginx.conf` 用 React 缓存形状（`/assets/` immutable 31536000，`/` try_files no-cache）。
- [ ] **Step 3**: `ci.yml`：test job（push/PR：pytest + npm build + vitest）；deploy job（仅 tag，concurrency 按仓隔离）：双镜像 `zcqiand/harness-textrpg-api`+`-web`（latest+tag）→ appleboy/ssh-action 拉 `refs/heads/main` 的 deploy 脚本 → env-file 自举（仅 `APP_PORT`）→ vhost 渲染（**cert 归一化 sed 规则排在 `<domain>` 之前**——家族纪律）→ 起双容器 → 探活 `/api/health` + web `/` 各 120s。
- [ ] **Step 4**: `deploy/harness-textrpg.sh`（web 5313 / api 5413，BASE=`/home/deploy/harness-textrpg`，无数据卷）+ `nginx-vps.conf.example`（`htextrpg.xiangru.uk`：`/`→127.0.0.1:5313，`/api/`→127.0.0.1:5413）。
- [ ] **Step 5**: Commit：`feat(deploy): 部署五件套——harness 家族首个 web+api 双容器仓（5313/5413）`。

### Task 15: 文档收口与全门验收

**Files:**
- Create: `docs/功能规格.md`, `README.md`

- [ ] **Step 1**: `docs/功能规格.md`（照书一仓同款表格式：核心引擎/API/前端四态/锁断言四节，验收标准列逐条可测）+ `README.md`（三行定位 + 快速开始 + 突出点一段）。
- [ ] **Step 2**: 全门验收（逐条记录输出）：

```bash
pip install -e ./backend && pytest -q                    # 全绿（含 12 锚×2 参数化）
cd frontend && npm run build && npm run test             # 双绿
APP_PORT=8806 uvicorn text_rpg.webserver:app             # 冒烟：/api/health → {"ok":true,"mode":"local"}
# 数据驱动实证：临时改 data/chapters/ch03 的 fan_gate requires → pytest 红 → 还原 → 绿（手工或跑 test_data_driven 即可）
```

- [ ] **Step 3**: `grep -rn "TODO\|pass$" backend/src frontend/src` 零占位确认。Commit：`docs: 功能规格与 README 收口`。
