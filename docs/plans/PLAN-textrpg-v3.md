# PLAN-textrpg-v3 — v3.0.0 四源整合（ch17）

> 规格真源=docs/superpowers/specs/2026-11-20-textrpg-v2-v3-design.md §5.5-§5.7。
> 本批 10 个 fn-ID 全在树（规划态），无新增 ID。
> 执行照 executing-plans：每任务新鲜子代理 + red-first + 两段审查 + gate 收口。

## 任务序列

### 任务 T9: 对手卡集资产（3 张卡）
- fn-ID: M04.F03.I01
- 文件: data/opponents/ 三件 JSON（opp_bone_spirit / opp_prince_dragon / opp_princess_fan）
- 测试先行: tests/test_opponents.py::test_opponent_contracts_exist_and_shape
- 验证: python -m pytest tests/test_opponents.py -q 由红转绿
- 备注: 卡面照 spec §5.5 示意（白骨精/魔王亲王/铁扇公主），strategy_table 含条件行+default 行。

### 任务 T10: 对手卡加载与自审
- fn-ID: M02.F06.I01
- 文件: backend/src/text_rpg/opponents.py（load_opponents + audit_opponents）
- 测试先行: tests/test_opponents.py 增 audit 用例（悬空章/空策略表/总数不足/每章零挂载各自红）
- 验证: python -m pytest tests/test_opponents.py -q → 全量 pytest -q
- 备注: audit 形状照 npcs.py 同族；量口径两闸=总数 <3 红、章清单任一章零挂载红（chapter 字段派生）。

### 任务 T11: 对抗结算（choice 内嵌 oppose）
- fn-ID: M02.F06.I02
- 文件: backend/src/text_rpg/oppose.py（种子化掷点 + 策略表取行动 + 编号账本 [{seq, actor, action, power, roll}]）
- 接线: routes.py POST /choice 锁放行后追加对抗结算，账本随响应返回；效果面同 v1 effects 四类
- 测试先行: tests/test_oppose.py（策略表分支通过+账本形状+效果落地）
- 验证: python -m pytest tests/test_oppose.py -q → 全量 pytest -q

### 任务 T12: 结算账本重放
- fn-ID: M02.F06.I03
- 文件: tests/test_oppose.py 增重放断言面 + backend/src/text_rpg/oppose.py 增 replay helpers
- 测试先行: 同种子+同局状态 → 账本全等断言（两次结算逐字段相等）；异种子 → 结果可异；账本逐条对账
- 阳断言面: 「同种子重放全等」是 T11 实现的验收锚——若 T11 实现不可重放，本任务将其打红
- 验证: python -m pytest tests/test_oppose.py -q → 全量 pytest -q

### 任务 T13: 奇遇模板集资产（2 模板）
- fn-ID: M04.F03.I02
- 备件: data/encounter-templates/enc_lost_sutra.json / enc_fruit_grove.json 2 件
- 测试先行: tests/test_encounters.py::test_encounter_templates_exist_and_shape
- 验证: python -m pytest tests/test_encounters.py -q 由红转绿
- 备注: 模板槽位/锁条件槽/效果槽/难度规约键齐（spec §5.6）；词面沿西游记语料。

### 任务 T14: 奇遇模板与难度规约加载
- fn-ID: M02.F07.I01
- 文件: backend/src/text_rpg/encounters.py（load_encounter_templates + audit：模板槽位/难度规约键齐，空槽位/空 denial 红）
- 测试先行: tests/test_encounters.py 增 load/audit 用例
- 验证: python -m pytest tests/test_encounters.py -q → 全量 pytest -q

### 任务 T15: 种子化生成器与无效过滤
- fn-ID: M02.F07.I02
- 文件: backend/src/text_rpg/encounters.py 增 generate_encounter(template, params, seed)
- 测试先行: 有效种子准入 + 五类无效种子（难度越界/悬空引用/空 denial/缺锚/超锁上限）各自拒收并报因
- 备注: 生成锁不进 lock_anchors 专供静态锁的全锚纪律，改由生成器模板级双向断言承担（spec §5.6 裁定）；静态锁照旧全锚不变。
- 验证: python -m pytest tests/test_encounters.py -q → 全量 pytest -q

### 任务 T16: 奇遇准入通道
- fn-ID: M02.F07.I03
- 文件: routes.py 增奇遇准入端点 + encounters.py 增 admit（过锁注册表自审后作临时场景并入当前章）
- 测试先行: tests/test_api_encounter.py（准入 200 临时场景入章 / 无效参数 400 报因 / 同局重放同种子全等）
- 备注: 种子服务端从 game state 派生，客户端不传种子（spec §5.6 硬约束）。
- 验证: python -m pytest tests/test_api_encounter.py -q → 全量 pytest -q

### 任务 T17: 全链路验收脚本
- fn-ID: M05.F01.I01
- 文件: scripts/acceptance.py（四能力探活：健康/建局/对话含拦截/对手结算重放/奇遇生成准入）
- 测试先行: tests/test_acceptance.py（探活函数逐项断言 + mock 服务器形状）
- 验证: python -m pytest tests/test_acceptance.py -q → 全量 pytest -q

### 任务 T18: 证据回执
- fn-ID: M05.F01.I02
- 文件: scripts/acceptance.py 增证据产出 + tests/test_acceptance.py 增 schema 断言
- 测试先行: 证据 JSON schema 断言（四能力逐项结论+回归汇总字段齐，落 _work/）
- 验证: python -m pytest -q 全量 → gate L0-L5 → 冒烟（mock 对话/拦截/记忆/对手重放/奇遇准入五探针）→ tag v3.0.0-YYYYMMDD
