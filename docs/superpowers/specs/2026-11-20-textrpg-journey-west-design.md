# harness-textrpg · 西游记章回文字冒险 RPG 设计文档

> 书三《Harness 工程：Codex 智能游戏开发入门》第 7 案例（覆盖第三、四、五篇）配套仓。
> 本批 = ch12 面（属性背包契约 / **剧情分支锁** / 按契约生成 / 剧情模板化）。
> 技术栈：Python + React（人裁 2026-11-20，Godot 方案否决——ch14 Python 桥接层字面成立）。

## 1. 意图与为什么

- 书三七案例分布表已为本案例留席：`文字冒险 RPG（harness-textrpg）`——本仓补上这个席位。
- 突出点（家族惯例，一个点拼命突出）：**剧情分支锁——抉择有后果，每把锁有断言**。玩家在章回中的每个抉择写入旗标，后续的门（能否进某回、NPC 态度、结局形态）由旗标/属性/背包三类条件门控；锁注册表双向自审，断链即红。
- 为什么是西游记：章回体天生是剧本模板结构（每回 = 一个数据驱动的剧情包，直通 ch12.4 模板化与 ch20 换皮）；妖怪/法宝撑起属性背包面；三打白骨精是「抉择有后果」的教科书素材；悟空/八戒/唐僧性格辨识度高，为 ch14 带记忆 NPC 留种子。三部候选名著均无版权风险，西游记综合契合度最高（人裁 2026-11-20）。

## 2. 目标 / 非目标 / 反目标

**目标（本批）**
1. 可完整通关的 3 回西游记文字冒险（每回约 6 场景，跨回锁 + 多结局）。
2. 分支锁全链：条件契约 → 注册表 → 启动自检 → 运行时门控 → 双向断言 → 前端锁徽标可视化。
3. 章回包纯数据驱动：新回 = 新 JSON，零代码改动（模板化的实物）。
4. pytest 无 Key 无网全绿 + 前端 tsc/vite/vitest 全绿。

**非目标（留后续批次）**
- ch14 面：NPC 人设契约、对话记忆、幻觉护栏、LLM 桥接（第二批突出点升级为「带记忆的 NPC」）。
- ch17 智能整合、ch20 批量换皮、ch21 迭代修复线。
- 战斗系统：textrpg 案例的契约面是属性+背包+抉择，战斗归 cardbattle/snake 案例演示——本批无战斗，锁条件里属性/背包照常成立。

**反目标（做了即失败）**
- 无断言锚的锁（锁了但说不清怎么验证）。
- 硬编码剧情（场景/抉择写进 Python）。
- 玩家读不懂「为什么进不去」（锁拒绝必须给出缺失条件的可读明细）。

## 3. 约束（沿用家族铁律，逐条）

- **TDD**：每模块先失败测试再实现；锁的断言先于锁的实现。
- **version-lock.json**：依赖钉死，不引入 lock 外的库。后端 Python 3.11+，FastAPI + uvicorn + pytest（钉版取本机实装且与 agent 家族三兄弟仓一致的已验证版本）；前端 React 19.1 + TypeScript + Vite + vitest 3（人裁 2026-11-20：以 harness-starter 实况为准，替代草稿的「React 18」）。
- **mock-friendly**：`pytest -q` 无 Key、无网、无 Docker 全绿；后端零第三方运行时依赖超出 lock 清单者禁止。
- **数据驱动**：场景/抉择/锁/结局全部从 `data/chapters/*.json` 加载，禁止硬编码进 Python。
- **npm 一律 npmmirror**。
- **零伪代码**：无 `pass`/`TODO`/`...` 占位。
- **正式区/临时区**：过程件进 `_work/`（整目录 .gitignore）；正式件同名唯一。
- **tag 规约**：`v<MAJOR>.<MINOR>.<PATCH>-<YYYYMMDD>`，禁删/覆盖，禁 `git push --tags`（单 tag push）。
- commit 尾注：`Co-Authored-By: Claude Code <noreply@anthropic.com>`；禁止 `git add -A`（逐文件 add）。

## 4. 方案取舍（已在对话中裁定）

| 决策 | 备选 | 裁定 | 理由 |
|---|---|---|---|
| 技术栈 | Godot / Python+React | **Python+React**（人裁） | ch14 Python 桥接层字面成立；与书一同栈，坑已趟 |
| 主题 | 西游/三国/红楼/水浒 | **西游记**（人裁） | 章回=模板、抉择素材经典、NPC 种子好留 |
| 突出点 | NPC 记忆 / 分支锁 | **分支锁**（本批） | ch12 主场；记忆留 ch14 批次升级 |
| 战斗面 | 有/无 | **无** | 案例契约面是属性+背包+抉择；战斗归其他案例 |
| 部署形状 | 纯静态 / web+api 双容器 | **web+api 双容器**（本批新增形状） | 引擎在 Python 侧；无 LLM 无 secret，env 只有 APP_PORT |

## 5. 架构

```
harness-textrpg/
├── backend/                      # Python 包 text_rpg（或平铺 src/，随 text-adventure-rpg 惯例）
│   ├── contracts.py              # Attribute/Backpack/Flag 三类锁条件的解析与求值
│   ├── locks.py                  # 锁注册表 + 启动自检（双向自审）
│   ├── engine.py                 # 游戏引擎：状态机、抉择处理、旗标写入、门控判定
│   ├── chapters.py               # 章回包加载器（data/chapters/*.json）
│   ├── persistence.py            # 会话内存库（服务器重启即失，前端 localStorage 恢复 id 降级建局）
│   ├── routes.py                 # FastAPI 路由层
│   └── webserver.py              # uvicorn 入口（APP_PORT，fail-fast）
├── data/chapters/*.json          # 章回包（回1/回2/回3），同一 schema
├── frontend/                     # React 18 + Vite + TS
│   └── src/...                   # 建局 / 章回探索 / 抉择+锁徽标 / 结局图 四态
├── tests/                        # pytest：contracts / locks / engine / chapters / api / 锁断言集
├── version-lock.json
├── CLAUDE.md
└── docs/superpowers/specs/       # 本文档
```

### 5.1 锁契约（突出点核心）

**状态与初始值（数据驱动，不硬编码）**：玩家初始属性与初始背包定义在 `data/game-start.json`（`{attributes: {insight: 1, ...}, backpack: []}`），建局时加载——改 JSON 即改开局，与章回包同受「数据驱动实证」覆盖。

**锁条件三类，可组合（全部 AND）**：

- `flag`：旗标布尔（如 `white_bone_evidence_1`）
- `attr`：属性阈值（如 `insight >= 3`，insight=悟性）
- `item`：背包持有（如 `banana_leaf_fan`）

**效果四类**（抉择通过后的状态变更，`effects` 数组顺序执行）：

- `{"flag": "bone_spirit_exposed"}` 写旗标
- `{"attr": {"insight": 1}}` 属性增量（负数即减）
- `{"item_add": "dry_rations"}` 入背包
- `{"item_remove": "banana_leaf_fan"}` 出背包

**引用方向（单箭头，裁定）**：**抉择侧挂锁**——`choice.lock = "<lock_id>"`；锁定义只声明 `requires/denial/effects`，不反向指向抉择。一把锁可被多个抉择复用。

```jsonc
// data/chapters/ch02-white-bone.json 片段（示意 schema，非最终文案）
{
  "id": "ch02", "title": "第二回·三打白骨精",
  "entry_locks": ["lock_ch02_entry"],           // 章回级进入条件（回完成旗标由抉择显式写入）
  "locks": [
    {
      "id": "lock_ch02_third_strike",
      "requires": [{"flag": "white_bone_evidence_2"}],
      "denial": "没有二验的证据，这一棒下去师父只会信妖怪的哭声。",
      "effects": [{"flag": "bone_spirit_exposed"}]
    }
  ],
  "scenes": [
    {
      "id": "s03", "text": "……",
      "choices": [
        {"id": "strike_third", "text": "当头第三棒", "lock": "lock_ch02_third_strike",
         "effects": [{"attr": {"insight": 1}}]},
        {"id": "verify_twice", "text": "再验一次", "effects": [{"flag": "white_bone_evidence_2"}]}
      ]
    }
  ],
  "endings": [
    {"id": "banished_early", "title": "被逐早终",
     "requires": [{"flag": "struck_without_evidence"}], "mid_chapter": true}
  ]
}
```

**章回完成是显式数据**：某抉择的 `effects` 写 `{"flag": "chapter_XX_complete"}` 才算完成该回，引擎不做隐式推进；下一回 `entry_locks` 引用该旗标（章回级门控同锁机制）。

**锁注册表双向自审**（注册表 = 全部章回包 `locks` 数组的并集，无独立 locks.json；`locks.py` 启动自检，errors 阻断、warnings 放行——同书一 validators 形状）：
1. **生产启动自检**：抉择引用的每个 `lock id` 都在注册表中存在（无悬空引用）；每把锁 `denial` 非空（玩家必须读得懂缺什么）；每把锁在锚表中有条目。
2. **锚表**（`text_rpg/lock_anchors.py`，包内数据，生产自检与 pytest 共读）：`lock_id → [test 文件名, 放行用例名, 拒绝用例名]`。
3. **pytest 侧核锚**：锚表中每个用例名在测试集里真实存在且双向各有一条（满足 requires → 放行；不满足 → 拒绝且 denial 可读）——生产代码不读 tests 目录，依赖方向是 pytest 读锚表。

### 5.2 本批章回内容（3 回，约 18 场景，12 把锁，4 结局）

- **回1·两界山前**：出村救樵夫还是先赶路（旗标 `helped_woodcutter`）；背包锁：不取干粮不得离村（`item: dry_rations`）。
- **回2·三打白骨精**：三段抉择（打/拦/验），每次选择写证据旗标；无二验证据强打第三下 → 触发「被逐」早终结局；集齐三证 → 白骨现形（跨回锁种子：`bone_spirit_exposed`）。
- **回3·火焰山**：背包锁 `banana_leaf_fan`（芭蕉扇）；借扇抉择：硬抢（丢旗标 `respect`）或智取（需回 1/回 2 旗标组合）→ 真/假扇两条线汇入不同结局。

**结局 4 态**：现形归真（全证全德）/ 借扇西行（智取线）/ 被逐早终（强打线）/ 半途折返（回1不救樵夫连锁）。**结局与锁同机制**：结局注册在章回包 `endings` 数组，`requires` 条件同锁；引擎每次抉择结算后判定，`mid_chapter: true` 允许章中途触发（被逐/折返都是中途局）。「走过的结局」是跨局进度，落前端 localStorage（重启不清）；**未达结局在结局图上显示缺失条件链**——这是锁证据链在 UI 的二次收口，剧透是接受的代价（家族重证据轻悬念）。

### 5.3 API 面

| 端点 | 语义 |
|---|---|
| `GET /api/health` | `{"ok":true,"mode":"local"}`（家族探活契约同款） |
| `GET /api/chapters` | 章回**静态目录**（id/title/序，无局上下文，**不携带锁定状态**） |
| `POST /api/games` | 建局（`{player_name}`）→ 201 `{id, state}` |
| `POST /api/games/{id}/choice` | 提交抉择 `{scene_id, choice_id}` → `{messages, state, unlocked_locks, game_over, ending?}` |
| `GET /api/games/{id}` | 读局：旗标/属性/背包/已解锁锁清单 + 当前场景逐 choice 锁评估 `{locked, missing:[{type,key,have,need}], denial}` + 4 结局条件链摘要（已满足/缺失）——**锁评估只在后端求值一次**，前端零复算 |

无 LLM、无 secret：env 契约只有 `APP_PORT`（fail-fast 必填，禁兜底默认）。

### 5.4 前端四态

1. **建局态**：输入名号（悟空视角开局）。
2. **章回探索态**：场景文案 + 出口 + 可用抉择列表；**被锁的抉择灰显并挂锁徽标**，点徽标弹条件明细（缺哪个旗标/属性/物品）——突出点的可视化面。
3. **抉择反馈态**：抉择结果 + 本步解锁的锁高亮 1.5s（同 starter 点亮节奏）。
4. **结局图态**：4 结局的图，走过的结局点亮，未达结局显示缺失条件链——锁证据链在 UI 的二次收口。

前端测试：vitest（锁徽标灰显/条件明细/解锁高亮/结局点亮四组）+ `tsc` strict + vite build。

## 6. 验收

```bash
# 后端
pip install -e ./backend && pytest -q          # 无 Key 无网全绿
# 前端
cd frontend && npm install --registry=https://registry.npmmirror.com
npm run build                                   # tsc strict + vite build 零错误
npm test -- run                                 # vitest 全绿
# 冒烟
APP_PORT=8806 uvicorn text_rpg.webserver:app    # /api/health ok
```

- 锁断言集：12 把锁 × 双向 ≥ 24 条用例 + 注册表自审 3 方向（悬空引用/缺断言锚/空 denial 均能红）。
- 数据驱动实证：复制一份章回 JSON 改一个锁条件 → 断言红（锁的断言跟着数据走，不是跟着代码走）。

## 7. 部署（本批交付五件套，形状升级）

web+api 双容器（家族内 textrpg 是第一个带后端的 harness 仓）：

- `backend/Dockerfile`（uvicorn，host=container 单层，ADR-0018 同款）+ `frontend/Dockerfile`（nginx 静态，容器内 :80）
- `.github/workflows/ci.yml`（test job + tag 触发 deploy job）
- `deploy/harness-textrpg.sh` + `deploy/nginx-vps.conf.example`（一域双 upstream：`/`→web，`/api/`→api；无 SSE 需求）
- 端口：web 5313 / api 5413（5410-5412 未占用——api 段此前无 harness 使用，取 5413 与 web 段同序对齐，部署批再核）
- env-file：仅 `APP_PORT`；Secrets：4 件（DOCKER_USERNAME/DOCKER_PASSWORD/VPS_HOST/VPS_USER）+ VPS_SSH_KEY = 5 件，无 LLM_API_KEY
- 域名 `htextrpg.xiangru.uk`（部署批在 suite `docs/families/agent.md` 登记值表）

## 8. 留给实现者的裁量

- 后端包布局（`backend/src/text_rpg/` vs 平铺）随实现者对 text-adventure-rpg 惯例的判断。
- 场景文案的最终措辞（schema 与锁条件为契约，文案可自由发挥到有趣）。
- 会话并发形态（单进程 dict 够用；不引入外部存储）。
- 前端样式风格（文字冒险的纸墨感自定，但锁徽标/条件明细/结局图三件是硬交付）。
