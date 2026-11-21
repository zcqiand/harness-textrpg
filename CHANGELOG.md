# 更新日志

格式照 `v<MAJOR>.<MINOR>.<PATCH>-<YYYYMMDD>`（tag 即放行：全量182→270 passed 全绿后打 tag）。

## [Unreleased]

v3.0.0（ch17 四源整合）十任务批（T9-T18，HEAD=171bb1c；本段含收官件）：

- 功能面：
  - 策略对手线（T9-T12）：3 对手卡（每回 ≥1）+ 加载自审七检 + choice 内嵌 oppose 种子化结算
    （账本 [{seq,actor,action,power,roll}]）+ 同种子同局状态重放全等
  - 程序化奇遇线（T13-T16）：2 奇遇模板（参数化槽位+锁条件槽+效果槽+难度规约）+ 种子化生成器
    （五类无效过滤报因）+ 准入通道（服务端派生种子，临时场景并入当前章，锁注册表自审+撞车闸）
  - 验收与证据（T17-T18）：scripts/acceptance.py 四能力探活 + 证据回执 JSON schema（落 _work/）
- 契约变更：
  - POST /api/games/{id}/encounters 新端点（准入）；GET /api/games/{id}/scenes/{sid} 新端点（任意场景读面）
  - POST /choice 响应增 oppose_ledger 键（声明 oppose 时）；力量服务端派生（属性和+旗标计数），无客户端力量字段
  - 装配面：build_router 增显式 templates/opponents 参数（None fail-fast 拒装配，禁惰性兜底）
- 冒烟五探针过（mock）：拦截/记忆/对手重放全等/奇遇准入可见
- 冒烟期望文档面同步：README:17 与 功能规格 A1 的 mode 期望 "local"→"mock"（v1 遗留挂账清偿）

v2.0.0（ch14 带记忆 NPC）八任务批（T1-T7 已提交，HEAD=8dd7d64；本段含 T8 代码面清偿）：

- 功能面：
  - LLM 桥接层（LLM_MODE/LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 四键 fail-fast 装配；mock/live 双形态，无 Key 无网全绿）
  - 带记忆 NPC（人设契约 data/npcs/*.json + 会话内记忆窗口 + event_tags 触发词表）
  - 双层护栏（red_lines 前置红线拦截面 + outside 知识边界降级面，判定只在后端求值一次；被拦轮不消耗记忆轮次）
  - 护栏锚表 lock_anchors 双测同款纪律
  - talk + memory 端点（M01.F02.I01-I03）与场景视图 npcs 带名
  - 前端 NPC 对话屏（含护栏拦截可视化，M03.F04.I01+I02）
- 契约变更：
  - 场景视图（GET /api/games/{id}）scene.npcs 由裸 id 列表改为带名对象 `[{id, name}]`
  - /api/health 的 mode 值随 LLM_MODE（"mock"/"live"）
  - env 新增 LLM_MODE / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 四键，缺失 fail-fast（禁兜底）
- 依赖变更：httpx 0.28.1 dev → runtime（LLM 桥接运行时依赖；version-lock.json 与 backend/pyproject.toml 两处同值同批）
- 收官清偿（T8）：
  - `load_npcs` 缺 `data/npcs/` 目录/空目录由静默返 [] 改为 fail-fast（FileNotFoundError/ValueError）
  - `audit_npcs` 量口径入闸：契约总数 <3 红、world 章清单任一章零挂载红（章清单由 world.chapters 派生，禁硬编码）
  - 对应红→绿用例 4 条（test_npc_contracts.py / test_api_npc.py 既有用例合法扩到 3 契约）；spec §8 计划落点注记更正
