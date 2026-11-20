# harness-textrpg — API 容器（agent 家族 api 段 5413，host=container 单层）
#
# 家族 deploy 链同款（text-adventure-rpg / 三兄弟先例）：
#   VPS nginx 终结 TLS → /api/ proxy_pass http://127.0.0.1:5413 → 容器 uvicorn。
#   CI deploy job build & push（latest + tag 双份）→ VPS deploy/harness-textrpg.sh
#   拉镜像起容器。
#
# 端口是家族契约（docs/families/agent.md，本仓 5313/5413）；CMD 读 APP_PORT，
# 不写默认值——webserver.py 侧缺 APP_PORT 即 fail-fast，env-file 由 deploy 脚本自举。
# CMD 用 uvicorn CLI 直挂 webserver:app（webserver.py 的 127.0.0.1 dev 姿态不动，
# 容器侧 host 由这里覆盖）。
# 可编辑安装（-e）是承重墙：_data_dir() = webserver.py parents[3] / "data"，
# editable 安装下 src 留在 /app/backend/src，parents[3]=/app → 剧情数据落 /app/data，
# 与仓库布局一致；剧情数据烘焙进镜像（sessions 在内存，无数据卷）。
# 无 HEALTHCHECK（slim 无 wget）：探活由 deploy 脚本 host 侧 /api/health 完成。
FROM python:3.11-slim

WORKDIR /app

COPY backend/pyproject.toml ./backend/
COPY backend/src/ ./backend/src/
COPY data/ ./data/

RUN pip install --no-cache-dir -e ./backend

EXPOSE 5413
CMD ["sh", "-c", "set -eu; exec uvicorn text_rpg.webserver:app --host 0.0.0.0 --port \"$APP_PORT\""]
