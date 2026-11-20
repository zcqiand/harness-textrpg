# PLAN-textrpg-v2 — 带记忆 NPC（ch14，tag v2.0.0）

> 规格：`docs/superpowers/specs/2026-11-20-textrpg-v2-v3-design.md`（已人批）。
> fn-ID 来源：tree-change 提案（M01.F02 / M02.F05 / M03.F04 / M04.F02，批准后生效）。
> 纪律：每任务先 red-first（测试跑红留证）再实现；零新依赖；CJK 数据文件小增量写+回验。
> 验证命令统一在仓根跑（pytest.ini 已接 backend/src）。

## 依赖图

```
T1 契约加载+资产 ─┬─→ T2 LLM 桥接 ─┬─→ T4 双层护栏 ─→ T5 锚表+证据 ─→ T6 路由 ─→ T7 前端 ─→ T8 回归+tag
T3 记忆存取 ──────┘                ┘
（T2 与 T3 并行；T4 依赖 T2+T3；T6 依赖 T5；T7 依赖 T6）
```

## 任务清单

### 任务 1: NPC 人设契约加载器与启动自审
- fn-ID: M02.F05.I01 + M04.F02.I01
- 文件: `tests/test_npc_contracts.py` / `backend/src/text_rpg/npcs.py` / `data/npcs/*.json`（3 个：每回 ≥1）
- 测试先行: 红——加载器解析契约（persona/red_lines/outside/inside/memory_spec）；自审三查红
  （悬空 chapter、空 red_lines、空 outside）；启动 audit 并入现有通道断言
- 验证: `python -m pytest tests/test_npc_contracts.py -q` 红→绿；随跑全量 `pytest -q`
- 备注: 数据文件逐个写，每写一个 grep U+FFFD 回验

### 任务 2: LLM 桥接层（与任务 3 并行）
- fn-ID: M02.F05.I04
- 文件: `tests/test_llm_bridge.py` / `backend/src/text_rpg/llm.py`
- 测试先行: 红——`LLM_MODE` 缺省拒启（禁兜底）；`live` 缺 BASE_URL/API_KEY/MODEL 任一拒启；
  mock 模式零网络返回契约回复（驱动护栏与记忆断言）；live 重试退避（httpx 假 transport 断言
  重试次数与指数退避）与统一错误形状；**重试预算照 text-adventure-rpg 母仓实况**（实现前先读
  母仓 `backend/` 对应模块抄值，母仓没有的部分 builder 定并在任务卡记一句）
- 验证: `python -m pytest tests/test_llm_bridge.py -q` 红→绿

### 任务 3: 对话记忆存取（与任务 2 并行）
- fn-ID: M02.F05.I02
- 文件: `tests/test_npc_memory.py` / `backend/src/text_rpg/memory.py`
- 测试先行: 红——per-(game,npc) 键存取；事件标签判定（契约词表命中打标）；窗口滑出与打标条目
  永久参与 prompt；被拦输入不计轮次；记忆条目序列化形状
- 验证: `python -m pytest tests/test_npc_memory.py -q` 红→绿

### 任务 4: 双层幻觉护栏（依赖 T2+T3）
- fn-ID: M02.F05.I03
- 文件: `tests/test_guardrails.py` / `backend/src/text_rpg/guardrails.py`
- 测试先行: 红——红线前置拦截（输入命中即拦，不调 LLM——mock 计数器断言零调用）；outside
  黑名单后置校验（输出命中即越界；重试一次；仍越界降级安全回应）；界内放行；证据记录四元组
  `{game_id, npc_id, turn, input, output, verdict}` 完整性
- 验证: `python -m pytest tests/test_guardrails.py -q` 红→绿

### 任务 5: 护栏锚表与生产自检接线
- fn-ID: M02.F05.I05
- 文件: `tests/test_guard_anchors.py` / `backend/src/text_rpg/guard_anchors.py`
- 测试先行: 红——锚表每条在测试集真实存在且双向（拦截/放行 或 越界降级/界内放行）；缺锚、
  测试名漂移、孤儿条款三方向各自红（v1 锚纪律同形变异实验）
- 验证: `python -m pytest tests/test_guard_anchors.py -q` 红→绿；启动自检含护栏锚核查断言

### 任务 6: NPC 对话路由（依赖 T5）
- fn-ID: M01.F02.I01 + M01.F02.I02 + M01.F02.I03
- 文件: `tests/test_api_npc.py` / `backend/src/text_rpg/routes.py`
- 测试先行: 红——POST talk 正常回复链（guard→llm→memory 落账）；blocked 形状
  `{blocked: true, denial 明细}`；GET memory 条目清单；未知 game/npc 404、空输入 400 形状统一
  （v1 I06 同款）；场景 `npc_ids` 进读局响应
- 验证: `python -m pytest tests/test_api_npc.py -q` 红→绿；全量 `pytest -q` 绿

### 任务 7: 前端对话屏（依赖 T6）
- fn-ID: M03.F04.I01 + M03.F04.I02
- 文件: `frontend/src/__tests__/talk.test.tsx` / `frontend/src/views/TalkView.tsx` /
  `frontend/src/views/JourneyView.tsx`（NPC 入口）/ `frontend/src/api.ts`（talk/memory 客户端）
- 测试先行: 红——场景挂 NPC 时探索态出现对话入口（触发元素挂 `data-fn="M03.F04.I01"`）；
  对话视图展示轮次与回复；blocked 时红线明细可视化（`data-fn="M03.F04.I02"`）；错误分支只认
  ApiError.status（v1 指纹）
- 验证: `npm --prefix frontend run test` 红→绿；`npx --no -- tsc --noEmit -p frontend` 绿；
  `npm --prefix frontend run build` 绿

### 任务 8: v2 全量回归 + gate + tag
- fn-ID: 全部 v2 子项
- 文件: 无新代码；`.state/`、CHANGELOG、version-lock 核对
- 验证: `pytest -q` 全绿（LLM_MODE=mock conftest 注入，无 Key 无网）；前端双绿；
  suite 侧 `python scripts/gate.py -p harness-textrpg` exit 0；
  冒烟三探针（mock 对话/拦截/记忆）；commit + 单 tag `v2.0.0-<YYYYMMDD>` push
- 备注: 推 tag 前 npm install 重同步 lock 自检（首推锁漂移坑家族先例）；CHANGELOG 记
  [Unreleased] 段

## 交接

- 实现交给 `executing-plans`（逐任务子代理+两段审查）；每个任务开工前过 `red-first`。
- T8 通过后开 v3 批次（PLAN-textrpg-v3，另拆）。
