# CLAUDE.md — harness-textrpg

> 书三第 7 案例仓：西游记章回文字冒险 RPG（3 回，突出点=剧情分支锁）。
> Python/FastAPI 引擎 + React 四态前端 + 部署五件套。schema 与锁契约真源=
> `docs/superpowers/specs/2026-11-20-textrpg-journey-west-design.md`（下称 spec）。

## 铁律

- TDD：每模块先写失败测试再实现；锁的断言先于锁的实现。
- 依赖钉死于 `version-lock.json`，不引入 lock 外的库；改版两处同 commit。
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

## 验收命令

```bash
pip install -e ./backend && pytest -q          # 后端全绿（无 Key 无网无 Docker）
cd frontend && npm run build && npm run test   # 前端双绿（tsc strict + vitest）
APP_PORT=8806 python -c "from text_rpg.webserver import main; main()"   # 冒烟：GET /api/health → {"ok":true,"mode":"mock"}（mode 随 LLM_MODE：mock/live）
# 注意：uvicorn CLI 形状不消费 APP_PORT（只读于 webserver.main()，会绑默认 8000）——起服/冒烟一律走 main() 入口。
```

## 数据驱动

章回包 `data/chapters/*.json` + `data/game-start.json` 是剧情唯一真源；
场景/抉择/锁/结局/初始状态一律出自数据文件，形状以 spec §5.1 为准。

## 锁契约

锁注册表=章包 locks 并集；启动自审查悬空引用/空 denial/锚覆盖；
锁评估只在后端求值一次。锚表 `backend/src/text_rpg/lock_anchors.py`
与锁断言测试一一对应，规则见 spec。
