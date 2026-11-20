# harness-textrpg v2.0.0 / v3.0.0 设计文档（ch14 带记忆 NPC / ch17 四源整合）

> 接续 `2026-11-20-textrpg-journey-west-design.md`（v1，已上线 tag v1.0.3-20261120）。
> 本批两个版本批次：**v2.0.0 = 书三 ch14「带记忆的 NPC」**，**v3.0.0 = ch17「综合项目（四源整合）」**。
> 出处：书仓 `xr-know-022` chapter-plan.json（textrpg=ch12/14/17，v1/v2/v3 对应）、
> `gate-waivers.json`（ch14/17 案例导入门豁免，待本批重冻结后撤销）、ch14/ch17 exec 清单要求。
> 六项建造裁定 2026-11-20 人裁通过（LLM=OpenAI 兼容 MiniMax；全链到 tag 上线；本文件 fork 1-5 全按推荐案）。

## 1. 意图与为什么

书三第四篇（智能篇）三章绑定本仓：ch12 底座（v1 已交付）→ ch14 带记忆 NPC（v2）→ ch17 综合
项目（v3）。书稿 ch14/ch17 处于 publication mode，其案例导入门（case_import_gate）当前靠
`gate-waivers.json` 豁免——本批建齐 v2/v3 功能面并打升版 tag，书稿侧即可重冻结导入、撤销豁免。

差异化卖点（书稿原话）：「玩家骂 NPC 一句，十轮之后它还记得并记仇——带记忆的 NPC 是换皮小
游戏做不到的」；v3 收口「三个独立练成的能力在这一章合体——别人换皮不出来的游戏」。

## 2. 目标 / 非目标 / 反目标

**v2.0.0 目标**
1. LLM 桥接层：FastAPI 服务端调 LLM API（OpenAI 兼容 `/chat/completions`，httpx 裸调零新
   依赖），失败重试（指数退避）+ 统一错误形状；`LLM_MODE=mock|live` fail-fast 分离，
   `pytest -q` 无 Key 无网全绿不变。
2. NPC 人设契约：`data/npcs/*.json` 数据驱动（与章回包同构），声明人设、红线话题、知识边界、
   记忆规约；启动自检并入现有 audit 通道（悬空 npc_id/空红线即红）。
3. 对话记忆存取：per-(game, npc) 内存会话记忆库（同 v1 persistence 形状），轮次记录 +
   事件标签（被骂/被赠/立约等）+ 检索窗口；「记仇」= 事件标签进入后续对话 prompt。
4. 幻觉抑制护栏：双层——前置红线拦截（输入命中红线即拦，不调 LLM，留证据记录）+ 后置知识
   边界校验（输出越界 → 重试一次 → 仍越界降级安全回应），证据记录可查询；断言集双向成锚。
5. 整合回 ch12 游戏：场景挂 NPC（`npc_id`），探索态多「对话」入口 + 对话视图 + 护栏拦截
   可视化提示；全量回归绿（pytest/vitest/tsc/vite/gate L0-L5）。

**v3.0.0 目标**
1. 四源合一架构：ch12 剧情底座 + ch14 记忆 NPC + 策略对手 + 程序化奇遇，仓内版本组织清晰
   （data/ 分层：chapters/ npcs/ opponents/ encounter-templates/）。
2. 策略对手（契约化）：`data/opponents/*.json` 对手卡（属性+策略表数据驱动行动规约），抉择级
   对抗结算（比拼属性+策略表，**非回合制战斗系统**），种子可重放可断言；书稿旁证复用
   harness-cardbattle v0.1.5-20261120（结算审计母题），textrpg 侧自建、不跨仓调用。
3. 程序化奇遇：`data/encounter-templates/*.json` 模板 + 种子化生成器——难度规约参数 → 生成
   场景/锁/效果片段 → 无效关卡过滤（难度越界/引用悬空即拒）→ **过 v1 锁注册表自审通道才
   准入**（生成物必过断言闸，maze 走线认证母题）。
4. 全链路验收：验收脚本 + 证据回执 JSON（hstarter evidence 先例）——四能力逐项探活 +
   回归全绿 + 护栏/生成器证据留档。
5. 部署链两跳：v2.0.0 / v3.0.0 逐版 tag → GitHub → CI deploy 首航；secret 增至 6 件（新增
   `LLM_API_KEY`，用户亲供管道直灌）；suite `docs/families/agent.md` 登记同步。

**非目标**
- 战斗系统（回合制）；策略对手只是抉择级对抗结算面。
- ch20 批量换皮、ch21 迭代修复线。
- 多轮长期记忆持久化（重启即失，同 v1 会话库）；语音/多模态。
- 书稿侧重冻结导入与撤豁免（归 xr-knowledge-suite book-craft 线，本批只交付 repo tag 与证据）。

**反目标（做了即失败）**
- 无断言锚的护栏（拦了但说不清怎么验证）。
- 人设/对手/奇遇模板硬编码进 Python（一律数据文件）。
- 前端直调 LLM（LLM 调用与锁评估同纪律：只在后端求值一次）。
- mock 面依赖真 Key/真网（`LLM_MODE=mock` 下 pytest 必须零网络零 Key）。
- 生成器产物绕过锁自审直接进游戏。

## 3. 约束（沿 v1 全部铁律，逐条继承）

- TDD：护栏断言先于护栏实现、生成器过滤断言先于生成器。
- version-lock.json：零新增运行时依赖（httpx 已在 lock；mock LLM 与策略对手结算纯 stdlib）。
  改版两处同 commit（version-lock + backend/pyproject.toml）。
- 数据驱动：人设/对手/模板全部 data/ 文件，形状以本文档 §5 为契约。
- env fail-fast：`APP_PORT` 必填不变；`LLM_MODE` 缺省即拒（无兜底默认，2026-08-28 漂移事故
  纪律）；`LLM_MODE=live` 时 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 缺一即拒启；mock 模式三键
  不读。
- npm 走 npmmirror；零伪代码；过程件进 `_work/`；tag 规约
  `v<MAJOR>.<MINOR>.<PATCH>-<YYYYMMDD>` 禁删/覆盖，v2、v3 各打一枚单 tag push。
- commit 尾注逐字 `Co-Authored-By: Claude Code <noreply@anthropic.com>`；禁 `git add -A`。
- CJK 坏写防范：数据文件小增量写入+逐次回验（U+FFFD grep + id 精确断言）。

## 4. 方案取舍（2026-11-20 人裁）

| # | 决策 | 备选 | 裁定 | 理由 |
|---|---|---|---|---|
| 0 | LLM 提供方 | OpenAI 兼容·MiniMax / Anthropic 兼容 / 纯 mock | **OpenAI 兼容·MiniMax** | text-adventure-rpg（母仓）与三兄弟先例，env 四件套照抄，坑已在账 |
| 0b | 交付边界 | 只到本地 / 全链 | **全链到 tag 上线** | 两版 tag 逐版推 GitHub→deploy 首航；secret 6 件届时用户亲供 |
| 1 | NPC 接线位置 | 场景内 / 独立面板 | **场景内**（`npc_id` 挂场景） | 与剧情数据同构，数据驱动实证覆盖，叙事顺 |
| 2 | 记忆存储 | 内存 / SQLite | **内存会话库** | 同 v1 persistence 形状，零新依赖；记忆契约面照测 |
| 3 | 护栏面 | 双层 / 只前置 | **双层** | 书稿明写红线拦截+知识边界校验两面，断言各自成锚 |
| 4 | 策略对手 | 契约化 / LLM 驱动 | **契约化**（数据驱动策略表） | LLM 对手不可断言，违背 mock-friendly；可重放可审计 |
| 5 | 程序化奇遇 | 模板生成器 / 手写扩展 | **种子化生成器+无效过滤+锁自审准入** | ch17 核心新能力；生成物必过断言闸=全书证据闭环母题 |

## 5. 契约形状（builder 据此实现，细节可裁量）

### 5.1 env 契约（v2 起）

| 键 | 语义 | fail-fast 规则 |
|---|---|---|
| `APP_PORT` | 服务端口 | 必填（v1 不变） |
| `LLM_MODE` | `mock` / `live` | 必填，缺省即拒（禁兜底） |
| `LLM_BASE_URL` | OpenAI 兼容端点（含 `/v1`） | live 必填 |
| `LLM_API_KEY` | 唯一 secret | live 必填，mock 不读 |
| `LLM_MODEL` | 模型名 | live 必填 |

### 5.2 NPC 人设契约（`data/npcs/*.json`，示意非最终文案）

```jsonc
{
  "id": "npc_bone_spirit_elder",
  "name": "老妇",
  "chapter": "ch02",
  "persona": "白骨精初化老妇……（人设文本，进 system prompt）",
  "red_lines": ["自称神明", "许诺长生"],           // 前置拦截：玩家输入命中即拦
  "outside": ["手机", "汽车", "互联网"],           // 后置判定词表（黑名单，见下）
  "inside": ["两界山", "白虎岭", "长安"],           // 进 system prompt 引导用，不参与判定
  "memory_spec": {"window": 10, "event_tags": ["insulted", "gifted", "promised"]}
}
```

- `red_lines` 匹配走关键词表（数据声明，代码只解释契约）；拦截不调 LLM；**被拦输入不消耗
  记忆轮次，但进证据记录**。
- 知识边界后置校验判定式：**输出命中 `outside` 黑名单词表即越界**（正向检测，无假阳性面；
  `inside` 白名单只进 prompt 引导，不参与判定）。越界重试一次，仍越界 → 安全回应模板 +
  证据记录 `{game_id, npc_id, turn, input, output, verdict}`。

### 5.3 对话记忆（内存会话库）

- 键 `(game_id, npc_id)`；条目 `{turn, player_text, npc_text, event_tags[]}`。
- 事件标签判定=契约声明词表（如 `insulted` 词表命中→打标）；打标条目永久参与后续 prompt
  （记仇钩子），普通条目滑出 `window` 窗口。
- 重启即失（同 v1）；前端 localStorage 已有 game id 降级路径沿用。
- **对话为纯对话层（裁定）**：记忆只进 prompt，talk 循环**永不写游戏状态**（flags/attr/item
  不动，v1 锁契约零变更、三章回包回归面零波及）；「记仇」在对话面成立（被打上 `insulted`
  等事件标签的条目永久参与后续 prompt，NPC 后续回复带记仇语气）。对话产效果（talk 写旗标）
  列非目标，书稿如需留 v3+ 另批。

### 5.4 API 增量（v2）

| 端点 | 语义 |
|---|---|
| `GET /api/games/{id}/scenes/{sid}` 内含 `npc_ids` | 场景挂 NPC（或并入现有读局响应，取实现者裁量，契约=对话入口来自场景数据） |
| `POST /api/games/{id}/npcs/{npc_id}/talk` | `{text}` → `{reply, blocked?, guard_evidence?, memory_turn}`；被拦时 `blocked=true` + 红线明细 |
| `GET /api/games/{id}/npcs/{npc_id}/memory` | 记忆条目清单（前端对话视图展示用） |

### 5.5 策略对手（v3，示意）

```jsonc
{
  "id": "opp_bone_spirit",
  "name": "白骨精",
  "base": {"deception": 3, "insight": 2},
  "strategy_table": [
    {"when": {"player_flag": "white_bone_evidence_1"}, "action": "weep", "power": 2},
    {"when": {"default": true}, "action": "disguise", "power": 3}
  ]
}
```

- 对抗结算：玩家抉择侧声明 `oppose: "<opp_id>"` + 己方力量（属性+旗标加权），对手按策略表
  取行动，种子化掷点决定胜负 → 效果（同 v1 effects 四类，可写旗标/减属性/失物）。
  **接线语义（裁定）：对手结算内嵌 `POST /choice`**（抉择声明 `oppose` 则在锁放行后追加对抗
  结算，账本随抉择响应返回）；独立端点形状与字段 builder 自定，语义硬约束=同种子+同局状态
  重放全等。
- 结算过程落编号账本（cardbattle 结算审计母题）：每步 `{seq, actor, action, power, roll}`
  可重放；测试从账本断言。

### 5.6 程序化奇遇（v3）

- 模板：`data/encounter-templates/*.json`——题材骨架 + 参数化槽位（场景文本模板/锁条件槽/
  效果槽）+ 难度规约（`difficulty: {attr_min, locks_max, ...}`）。
- 生成器（Python，种子化）：模板+难度参数+种子 → 候选奇遇（场景/锁/效果片段）→ **无效过滤**
  （难度越界、引用悬空、空 denial、锚缺失即拒收并报原因）→ 通过者经锁注册表自审通道准入。
  **准入通道架构（裁定）**：生成锁**不进** `lock_anchors.py` 静态锚表——生成锁的「锚纪律」由
  生成器模板级双向断言承担（每模板：有效参数+种子 → 准入；构造的五类无效种子 → 拒收并报因），
  静态锁照旧全锚不变；生成奇遇作为临时场景并入当前章（服务端从 game state 派生种子，客户端
  不传种子），效果面同 v1 四类、可写玩家状态。
- 书稿实践练习=「加一个模板跑全链路回归留证据」：新模板 JSON 落 data/ 即被生成器测试覆盖
  （数据驱动实证同 v1 章回包）。

### 5.7 全链路验收与证据（v3）

- `scripts/acceptance.py`（或同形）：四能力逐项探活（健康/建局/对话含拦截/对手结算重放/
  奇遇生成准入）+ 双端测试全绿汇总 → 证据回执 JSON（`_work/` 生成、检入的只有脚本与 schema；
  CI 内产证据随 build 烘焙照 hstarter 先例裁量）。

## 6. 留给实现者的裁量

- 护栏断言锚载体（独立 `guard_anchors.py`，同 v1 锚纪律形状：生产自检与 pytest 共读）。
- mock LLM 回复库形状（固定回复表 vs 小型规则回复器——须能驱动护栏双向断言与记忆断言）。
- live 重试预算（次数/退避/单次超时）：**照 text-adventure-rpg 母仓实况**抄值，母仓没有的
  部分 builder 定（计划阶段先读母仓）。
- `/api/health` 的 `mode` 值随 `LLM_MODE` 反映（`"mock"` / `"live"`）——家族探活契约只断言
  `ok` 字段与 `mode` 键存在，值自由。
- 前端对话视图样式（纸墨感沿用）；NPC 入口在探索态的具体呈现。
- v3 API 字段形状（§5.5 已约束语义面）。
- 证据回执的具体 schema 与落点。

**内容量口径（裁定，对接书稿 case_import_gate 判定面）**：书稿 gate 按功能面+tag 绑定判定
（registry `pending_refreeze.needed`），无数量下限；数量约束来自书稿清单量（ch14/ch17 各
10-12 个清单须有真实代码面可引）。据此定基线：**NPC ≥3（每回 ≥1）、对手 ≥3（每回 ≥1）、
奇遇模板 ≥2（含留书稿练习新增 1 个的空间）**——书稿侧重冻结导入时照此绑定，不够再加。

## 7. 验收（两版各自全量）

```bash
pip install -e ./backend && pytest -q            # v2/v3 全绿（无 Key 无网：LLM_MODE=mock）
cd frontend && npm run build && npm run test     # tsc strict + vitest 全绿
python scripts/gate.py -p harness-textrpg        # suite gate L0-L5 exit 0（suite 侧跑）
# 冒烟：mock 模式对话/拦截/记忆三探针 + v3 加对手结算重放与奇遇生成准入
```

- 护栏断言集：红线拦截双向（命中拦/不命中放）+ 知识边界双向（越界降级/界内放行）+ 证据记录
  完整性；每锚正反双测（v1 锚纪律）。
- 生成器断言集：有效种子准入 / 五类无效种子（难度越界/悬空引用/空 denial/缺锚/超锁上限）
  各自拒收并报因。
- 对手结算断言：同种子重放全等 + 策略表分支覆盖 + 账本逐条对账。
- 数据驱动实证：改一份人设 JSON 的红线词表 → 拦截断言跟着数据走（v1 同款变异实验）。
- 版本 tag：`v2.0.0-<date>`、`v3.0.0-<date>` 各单 tag push → CI deploy 绿 → live 探活
  （含 mock 对话探针；live LLM 探活用真 Key 由部署批执行）。

## 8. 批次与交接

- v2 先收官（tag+deploy+回归绿）再开 v3（v3 以 v2 为底，书稿明写「第 14 章 v2 为底」）。
- 两批各自 docs/superpowers/plans/ 落实现计划（writing-plans 流程）。
- 收官交接：suite `docs/families/agent.md` textrpg 段更新（Secrets 5→6 件含 LLM_API_KEY 注记）、
  仓 CHANGELOG、`.state/session.json`；书稿侧重冻结导入+撤豁免移交 xr-knowledge-suite
  book-craft 线（不在本批）。
