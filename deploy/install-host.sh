#!/usr/bin/env bash
# 把 LightPanel 装成宿主机上的 systemd 服务。
#
# 这条路径下**不需要容器，也不需要 lightpanel-agent**：面板进程和 docker daemon
# 看的是同一个文件系统，compose 里的 ./src:/app 会被解析成真实路径；
# psutil 读到的也是整机指标。
#
#   sudo ./deploy/install-host.sh
#
# 可覆盖的变量：
#   APP_DIR=/ssd/app/lightpanel     项目根目录（默认取脚本上一级）
#   RUN_USER=zyq                    服务运行身份（默认 sudo 前的用户）
#   PORT=9001                       监听端口
#   PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple/
#   SKIP_FRONTEND=1                 已有 frontend/dist 时跳过前端构建

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(id -un)}}"
PORT="${PORT:-9001}"
PYPI_INDEX="${PYPI_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
CONFIG="$APP_DIR/config.local.yaml"
VENV="$APP_DIR/backend/.venv"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '错误: %s\n' "$*" >&2; exit 1; }

# 以服务用户身份执行（避免 root 拥有 venv 目录）
as_user() {
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "$RUN_USER" -- "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -u "$RUN_USER" -- "$@"
  else
    su -s /bin/sh -c "$(printf '%q ' "$@")" "$RUN_USER"
  fi
}

[ "$(id -u)" -eq 0 ] || die "安装服务需要 root：sudo $0"
[ -d "$APP_DIR/backend" ] || die "APP_DIR 不像项目根目录：$APP_DIR"
id "$RUN_USER" >/dev/null 2>&1 || die "用户不存在：$RUN_USER"

PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "找不到 python3"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "需要 Python 3.11+，当前 $("$PY" -V 2>&1)"

say "① 准备 venv（$VENV）"
if [ ! -x "$VENV/bin/python" ]; then
  as_user "$PY" -m venv "$VENV"
fi
# 清华源对 setuptools 会返回 403，默认用阿里云；换源时注意这点
as_user "$VENV/bin/pip" install -q --upgrade pip
as_user "$VENV/bin/pip" install -q \
  --index-url "$PYPI_INDEX" --trusted-host "$(echo "$PYPI_INDEX" | awk -F/ '{print $3}')" \
  -e "$APP_DIR/backend"
"$VENV/bin/python" -c 'import lightpanel' || die "依赖安装失败"

say "② 准备前端产物"
if [ -f "$APP_DIR/frontend/dist/index.html" ] && [ -z "${SKIP_FRONTEND:-}" ]; then
  echo "已有 frontend/dist，跳过（要重建请删掉该目录后重跑）"
elif [ ! -f "$APP_DIR/frontend/dist/index.html" ]; then
  command -v docker >/dev/null 2>&1 || die "宿主机没有 node，也没有 docker，无法构建前端"
  echo "宿主机没装 node，用一次性 node 容器构建"
  docker run --rm -v "$APP_DIR/frontend:/app" -w /app node:22-alpine \
    sh -c 'npm ci && npm run build'
  chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/frontend/dist"
fi

say "③ 生成配置（$CONFIG）"
if [ -f "$CONFIG" ]; then
  echo "已存在，保留不动"
else
  TOKEN="lp_$(as_user "$PY" -c 'import secrets; print(secrets.token_urlsafe(24))')"
  cat > "$CONFIG" <<YAML
# LightPanel 宿主机直跑配置（由 deploy/install-host.sh 生成）
env: prod

server:
  host: 0.0.0.0
  port: $PORT
  docs: false            # 开鉴权后不暴露 /docs 与 /openapi.json

security:
  enabled: true
  api_token: "$TOKEN"

compose:
  enabled: true
  search_paths:          # 按实际栈目录改
    - /opt
    - /srv
    - /home
  max_depth: 3
  runner: local          # 与 daemon 同一文件系统，不需要 agent

catalog:
  provider: yaml
  path: data/catalog.yaml

commands:
  extra_file: data/commands.yaml
YAML
  chown "$RUN_USER:$RUN_USER" "$CONFIG"
  chmod 600 "$CONFIG"
  echo "已生成，访问令牌：$TOKEN"
fi

say "④ 准备数据目录"
mkdir -p "$APP_DIR/data"
[ -f "$APP_DIR/data/catalog.yaml" ] || cp "$APP_DIR/backend/data/catalog.example.yaml" "$APP_DIR/data/catalog.yaml"
[ -f "$APP_DIR/data/commands.yaml" ] || cp "$APP_DIR/backend/data/commands.yaml" "$APP_DIR/data/commands.yaml" 2>/dev/null || true
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/data"

say "⑤ 安装 systemd 单元"
# 端口被手工起的实例占着时，systemd 会直接起不来
PID=$(ss -tlnp 2>/dev/null | sed -n "s/.*:$PORT .*pid=\([0-9]*\).*/\1/p" | head -1)
if [ -n "$PID" ] && ! systemctl is-active --quiet lightpanel; then
  echo "端口 $PORT 被 PID $PID 占用，先停掉它"
  kill "$PID" 2>/dev/null || true
  sleep 2
fi
sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@RUN_USER@|$RUN_USER|g" \
  "$APP_DIR/deploy/lightpanel.service.in" > /etc/systemd/system/lightpanel.service
systemctl daemon-reload
systemctl enable --now lightpanel

# 启动到监听之间有 3~6 秒（加载配置 + 挂 SPA），固定 sleep 会误报"未监听"
i=0
while [ "$i" -lt 20 ]; do
  ss -tln 2>/dev/null | grep -q ":$PORT " && break
  systemctl is-active --quiet lightpanel || break
  i=$((i + 1))
  sleep 1
done

say "⑥ 结果"
systemctl --no-pager --full status lightpanel | head -12 || true
echo
if ss -tln 2>/dev/null | grep -q ":$PORT "; then
  echo "已监听 0.0.0.0:$PORT  用户：$RUN_USER  配置：$CONFIG"
  echo "浏览器打开 http://<本机IP>:$PORT ，用上面的令牌登录"
else
  echo "未监听，查看日志：journalctl -u lightpanel -n 50 --no-pager"
fi
