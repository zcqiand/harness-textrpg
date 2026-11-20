# harness-textrpg — 西游记章回文字冒险

书三第 7 案例仓：西游记章回文字冒险 RPG（3 回：两界山前 / 三打白骨精 / 火焰山，突出点 = 剧情分支锁）。
FastAPI 引擎 + React 四态前端（建局 / 探索 / 结局图 / 解锁高亮）+ 部署五件套（web+api 双容器，家族首例）。
剧情数据驱动：3 章回 / 12 把锁 / 4 个结局全部出自 `data/chapters/*.json`，代码零硬编码剧情。

## 快速开始

后端（Python 3.11+，pytest 无 Key 无网无 Docker 全绿）：

```bash
pip install -e ./backend
pytest -q                # 74 例全绿（含 12 锚 ×2 参数化）

APP_PORT=8806 python -c "from text_rpg.webserver import main; main()"
# APP_PORT 必填 fail-fast（缺省即 RuntimeError，无默认端口兜底）
# 冒烟：curl http://127.0.0.1:8806/api/health → {"ok":true,"mode":"local"}
# 注意：`uvicorn text_rpg.webserver:app`（CLI 形状）不消费 APP_PORT，会绑 uvicorn 默认 8000——
# APP_PORT 只在 webserver.main() 里读，起服/冒烟一律走上面 main() 入口。
```

前端（Node ≥20；npm 依赖一律走 npmmirror，仓内 `frontend/.npmrc` 已钉 `registry=https://registry.npmmirror.com`）：

```bash
cd frontend
npm ci
npm run build            # tsc strict + vite build
npm run test             # vitest，15 例全绿
```

依赖钉版：Python 侧见 `version-lock.json` 与 `backend/pyproject.toml`（两处同 commit），前端以 `frontend/package-lock.json` 为准。

## 突出点：剧情分支锁

本仓的核心不是剧情文本，而是锁机制的可测试性。每条分支抉择可挂一把锁（`data/chapters/*.json` 的 `lock` 字段），锁条件支持三类（flag 旗标 / attr 属性阈值 / item 物品，列表全 AND），条件不满足时后端返回结构化 `missing` 明细（type/key/have/need）与人读 `denial` 文案，锁评估只在后端求值一次。围绕它有四层保障：

1. **锁注册表**（`backend/src/text_rpg/locks.py`）——各章包 locks 的并集，全服唯一的锁字典；
2. **启动自审**——服务起来先查三件事：悬空 `choice.lock` 引用、空 denial 文案、缺测试锚，任何一条成 error 即拒绝启动（`webserver.py::_audit_gate`），坏数据根本起不了服；
3. **ANCHORS 断言框架**（`backend/src/text_rpg/lock_anchors.py`）——每把注册锁在锚表登记正反两条 pytest 用例 id，`tests/test_lock_assertions.py` 按 12 锚 ×2 参数化逐锁断言放行与锁死，锚覆盖不全测试保持红；
4. **数据驱动实证**（`tests/test_data_driven.py`）——把 `data/` 复制进临时目录、只改一处章包 JSON（`lock_ch03_fan_gate` 的 requires 换成不存在的 key），同一把锁对同一状态的裁决即从放行翻成锁死、missing 直接点名被改的 key——证明锁行为完全由数据驱动，测试与引擎未硬编码任何锁逻辑。

功能规格（逐条验收标准点名真实测试）见 `docs/功能规格.md`。
