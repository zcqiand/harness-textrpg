#!/bin/sh
# Usage: harness-textrpg.sh <DOCKER_USERNAME> <DOCKER_PASSWORD> [VERSION]
#
# 由 .github/workflows/ci.yml 的 deploy job 远程调用：
#   ssh deploy@vps -- cd /home/deploy/harness-textrpg
#                    && sh harness-textrpg.sh $DOCKER_USERNAME $DOCKER_PASSWORD $VERSION
# 环境变量：LLM_API_KEY 必填（CI 自 secret 转发），缺失 exit 2。
#
# agent 家族部署形态（docs/families/agent.md，2026-11-20 分配 5313/5413），
# harness 家族首个 web+api 双容器仓：
#   web 容器（nginx 静态，容器内 :80）→ host 127.0.0.1:5313（web 段）
#   api 容器（uvicorn，host=container）→ host 127.0.0.1:5413（api 段）
#   vhost htextrpg.xiangru.uk：/ → web 容器，/api/ → api 容器
#
# 与家族后端仓 deploy 脚本的差异：
#   - 一仓双镜像（harness-textrpg-api / -web），env-file 五键
#     （APP_PORT + LLM 四键，v2.0.1 起随后端 fail-fast 装配契约补齐）
#   - LLM_API_KEY 自 CI secret 转发，空值/占位即 fail-fast；
#     无数据卷（sessions 在内存，剧情数据已烘焙进 api 镜像）
#   - 探活 /api/health（{"ok":true,...}）+ web 静态首页（200），各 120s
#
# 前置: deploy 用户需在 docker 组中(sudo usermod -aG docker deploy)；
#       sudoers 放 nginx + systemctl reload + !requiretty（家族既有）。

set -eu

USERNAME="${1:-}"
PASSWORD="${2:-}"
VERSION="${3:-latest}"
IMAGE_API="${USERNAME}/harness-textrpg-api:${VERSION}"
IMAGE_WEB="${USERNAME}/harness-textrpg-web:${VERSION}"
BASE="/home/deploy/harness-textrpg"
API_PORT=5413
WEB_PORT=5313
CONTAINER_API="harness-textrpg-api"
CONTAINER_WEB="harness-textrpg-web"

NGINX_DOMAIN="${NGINX_DOMAIN:-htextrpg.xiangru.uk}"
NGINX_CERT_BASENAME="${NGINX_CERT_BASENAME:-xiangru-uk}"

if [ -z "$USERNAME" ] || [ -z "$PASSWORD" ]; then
  echo "Usage: $0 <DOCKER_USERNAME> <DOCKER_PASSWORD> [VERSION]" >&2
  exit 2
fi

# env-file 自举/补键：键集合 = APP_PORT（家族契约 prod 值 5413）+ LLM 四键
# （v2.0.0 后端 fail-fast 装配：LLM_MODE/LLM_BASE_URL/LLM_MODEL 内置 prod 值；
# LLM_API_KEY 自 CI secret 经 env 转发，空/占位即拒绝部署——禁 env 默认值兜底）。
# append-if-missing 教训：非密三键仅在「缺失或值为空/占位」时补写，
# 运维手工改过的实值保留。LLM_API_KEY 同规则补写（老占位行换新 secret）。
if [ -z "${LLM_API_KEY:-}" ]; then
  echo "ERROR: LLM_API_KEY 为空（CI secret 未配置或未转发），拒绝部署" >&2
  exit 2
fi
ENV_FILE="$BASE/harness-textrpg.env"
LLM_MODE_PROD="live"
LLM_BASE_URL_PROD="https://api.minimaxi.com/v1"
LLM_MODEL_PROD="MiniMax-M2.5"
upsert_env() {
  key="$1"
  val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    cur="$(sed -n "s/^${key}=//p" "$ENV_FILE" | head -n 1)"
    case "$cur" in
      ""|"changeme"|"placeholder")
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
        ;;
    esac
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}
if [ ! -f "$ENV_FILE" ]; then
  echo "→ bootstrapping $ENV_FILE（五键）"
  umask 077
  {
    printf 'APP_PORT=%s\n' "$API_PORT"
    printf 'LLM_MODE=%s\n' "$LLM_MODE_PROD"
    printf 'LLM_BASE_URL=%s\n' "$LLM_BASE_URL_PROD"
    printf 'LLM_MODEL=%s\n' "$LLM_MODEL_PROD"
    printf 'LLM_API_KEY=%s\n' "$LLM_API_KEY"
  } > "$ENV_FILE"
  chown deploy:deploy "$ENV_FILE" 2>/dev/null || true
  chmod 600 "$ENV_FILE"
else
  if ! grep -q '^APP_PORT=' "$ENV_FILE"; then
    echo "→ append APP_PORT to existing $ENV_FILE"
    umask 077
    printf 'APP_PORT=%s\n' "$API_PORT" >> "$ENV_FILE"
  fi
  umask 077
  upsert_env LLM_MODE "$LLM_MODE_PROD"
  upsert_env LLM_BASE_URL "$LLM_BASE_URL_PROD"
  upsert_env LLM_MODEL "$LLM_MODEL_PROD"
  upsert_env LLM_API_KEY "$LLM_API_KEY"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
fi

# nginx vhost 重渲染（每次 deploy 都跑；模板总从 main 拉最新——
# VPS 本地老模板会渲染出老端口全家族 502，2026-09-03 事故纪律）
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
NGINX_VHOST_FILE="${NGINX_SITES_AVAILABLE}/${NGINX_DOMAIN}"
NGINX_VHOST_LINK="${NGINX_SITES_ENABLED}/${NGINX_DOMAIN}"
NGINX_TEMPLATE="${BASE}/nginx-vps.conf.example"

echo "→ fetching nginx-vps.conf.example template (always fresh from main)"
curl -fsSL "https://raw.githubusercontent.com/zcqiand/harness-textrpg/refs/heads/main/deploy/nginx-vps.conf.example" -o "${NGINX_TEMPLATE}"

# 渲染到临时文件 —— sed 顺序：cert 归一化规则必须排在 <domain> 通配之前
# （先替换 <domain> 会把 cert 路径占位符一并吃掉，2026-09-03 事故根因）。
TMP_VHOST="$(mktemp -t vpstpl.XXXXXX)"
sed \
  -e "s|/etc/nginx/ssl/<domain>\.crt|/etc/nginx/ssl/${NGINX_CERT_BASENAME}.cert|g" \
  -e "s|/etc/nginx/ssl/<domain>\.key|/etc/nginx/ssl/${NGINX_CERT_BASENAME}.key|g" \
  -e "s|<domain>|${NGINX_DOMAIN}|g" \
  "${NGINX_TEMPLATE}" > "${TMP_VHOST}"

if [ -e "${NGINX_VHOST_FILE}" ] && diff -q "${TMP_VHOST}" "${NGINX_VHOST_FILE}" >/dev/null 2>&1; then
  echo "→ nginx vhost ${NGINX_VHOST_FILE} unchanged, skip"
  rm -f "${TMP_VHOST}"
else
  echo "→ rendering nginx vhost ${NGINX_VHOST_FILE} (domain=${NGINX_DOMAIN} cert=${NGINX_CERT_BASENAME})"
  if [ -w "${NGINX_SITES_AVAILABLE}" ]; then
    cp "${TMP_VHOST}" "${NGINX_VHOST_FILE}"
  else
    sudo cp "${TMP_VHOST}" "${NGINX_VHOST_FILE}" \
      || { echo "ERROR: sudo cp ${NGINX_VHOST_FILE} failed"; rm -f "${TMP_VHOST}"; exit 1; }
  fi
  if [ -w "${NGINX_SITES_ENABLED}" ]; then
    ln -sf "${NGINX_VHOST_FILE}" "${NGINX_VHOST_LINK}"
  else
    sudo ln -sf "${NGINX_VHOST_FILE}" "${NGINX_VHOST_LINK}" \
      || { echo "ERROR: sudo ln ${NGINX_VHOST_LINK} failed"; rm -f "${TMP_VHOST}"; exit 1; }
  fi
  rm -f "${TMP_VHOST}"
  echo "→ nginx -t"
  sudo nginx -t
  echo "→ systemctl reload nginx"
  sudo systemctl reload nginx
  echo "✓ nginx reloaded"
fi

echo "→ image: $IMAGE_API / $IMAGE_WEB"
echo "→ docker login"
printf '%s' "$PASSWORD" | docker login -u "$USERNAME" --password-stdin

echo "→ docker pull (api + web)"
docker pull "$IMAGE_API"
docker pull "$IMAGE_WEB"

echo "→ docker stop & rm $CONTAINER_API $CONTAINER_WEB"
docker stop "$CONTAINER_API" 2>/dev/null || true
docker rm "$CONTAINER_API" 2>/dev/null || true
docker stop "$CONTAINER_WEB" 2>/dev/null || true
docker rm "$CONTAINER_WEB" 2>/dev/null || true

echo "→ docker run api (host=container=$API_PORT, env-file 五键, 无数据卷)"
docker run -d \
  --name "$CONTAINER_API" \
  --restart unless-stopped \
  -p "127.0.0.1:${API_PORT}:${API_PORT}" \
  --env-file "$ENV_FILE" \
  "$IMAGE_API"

echo "→ docker run web (容器 :80 → host $WEB_PORT)"
docker run -d \
  --name "$CONTAINER_WEB" \
  --restart unless-stopped \
  -p "127.0.0.1:${WEB_PORT}:80" \
  "$IMAGE_WEB"

echo "→ docker image prune"
docker image prune -f

echo "→ docker ps"
docker ps --filter name="$CONTAINER_API"
docker ps --filter name="$CONTAINER_WEB"

# 健康检查：/api/health 探 200 且 body 含 "ok":true（家族探活契约）。
# 容器死亡提前终止循环，立刻报失败。
i=0
while [ $i -lt 120 ]; do
  if wget --tries=1 --timeout=3 -qO- "http://127.0.0.1:${API_PORT}/api/health" 2>/dev/null | grep -q '"ok":true'; then
    echo "→ /api/health {\"ok\":true,...} (host 127.0.0.1:${API_PORT}) after ${i}s"
    break
  fi
  if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_API" 2>/dev/null | grep -q true; then
    echo "→ api container not running, logs:"
    docker logs --tail 30 "$CONTAINER_API"
    exit 1
  fi
  i=$((i+1))
  sleep 1
done
if [ $i -ge 120 ]; then
  echo "→ /api/health 仍未 {\"ok\":true}（120s 上限）, logs:"
  docker logs --tail 30 "$CONTAINER_API"
  exit 1
fi

# web 静态探活：同款 120s 循环
i=0
while [ $i -lt 120 ]; do
  if wget --tries=1 --timeout=3 -q "http://127.0.0.1:${WEB_PORT}/" -O /dev/null 2>/dev/null; then
    echo "→ web / 200 (host 127.0.0.1:${WEB_PORT}) after ${i}s"
    break
  fi
  if ! docker inspect --format='{{.State.Running}}' "$CONTAINER_WEB" 2>/dev/null | grep -q true; then
    echo "→ web container not running, logs:"
    docker logs --tail 30 "$CONTAINER_WEB"
    exit 1
  fi
  i=$((i+1))
  sleep 1
done
if [ $i -ge 120 ]; then
  echo "→ web / 仍未 200（120s 上限）, logs:"
  docker logs --tail 30 "$CONTAINER_WEB"
  exit 1
fi

echo "→ deploy done at $(date -u)"
