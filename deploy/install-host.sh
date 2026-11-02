#!/usr/bin/env bash
# LightPanel · 宿主机直跑方案的安装与运维入口。
#
# 这条路径不需要容器，也不需要 lightpanel-agent：
#   * 面板进程与 docker daemon 共用同一个文件系统，compose 里的 ./src:/app
#     会被解析成真实宿主机路径；
#   * psutil 读到的是整机指标（全部网卡、全部磁盘）；
#   * 进程由 systemd 托管，退出后自动拉起。
#
# 每个子命令都是**独立且幂等**的，可以单独重跑，不需要每次从头来：
#
#   sudo ./deploy/install-host.sh all          # 完整安装 = deps + frontend + config + data + service
#   sudo ./deploy/install-host.sh deps         # 只建 venv / 装 Python 依赖
#   sudo ./deploy/install-host.sh frontend     # 只构建前端产物
#        ./deploy/install-host.sh config --port 9001 --stacks-root /ssd/app,/home/zyq/opt
#        ./deploy/install-host.sh data        # 只初始化 data/*.yaml
#   sudo ./deploy/install-host.sh service      # 只安装/更新 systemd 单元并启动
#        ./deploy/install-host.sh status       # 状态 + 端口 + 接口探活 + 登录令牌
#        ./deploy/install-host.sh logs         # 跟踪日志
#        ./deploy/install-host.sh restart      # 重启（等价 systemctl restart lightpanel）
#        ./deploy/install-host.sh stop         # 停止
#
# 选项（可出现在任意子命令后）：
#   --app-dir DIR       项目根目录，默认取本脚本的上一级
#   --user USER         服务运行身份，默认 sudo 之前的用户
#   --port N            监听端口，默认沿用已有配置，否则 9001
#   --stacks-root A,B   compose 扫描目录（逗号分隔），默认 /opt
#   --max-depth N       扫描递归深度，默认 3
#   --pypi-index URL    Python 源，默认阿里云
#   --force             覆盖已存在的 config.local.yaml（先备份、会换新令牌）
#   --no-build          前端产物缺失时报错，而不是自动构建
#
# 环境要求：Linux + systemd + Python 3.11+。前端构建需要 node 或 docker 二选一。

set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD=""
APP_DIR=""
RUN_USER=""
PORT=""
STACKS_ROOT=""
MAX_DEPTH=""
PYPI_INDEX="${PYPI_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
FORCE=0
NO_BUILD=0

say()  { printf '\n==> %s\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '警告: %s\n' "$*" >&2; }
die()  { printf '错误: %s\n' "$*" >&2; exit 1; }

usage() {
  awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "${BASH_SOURCE[0]}"
}

# ---------------------------------------------------------------- 参数解析

while [ $# -gt 0 ]; do
  case "$1" in
    all|deps|frontend|config|data|service|status|logs|restart|stop)
      CMD="$1"; shift ;;
    --app-dir)     [ -n "${2:-}" ] || die "--app-dir 缺值";     APP_DIR="$2"; shift 2 ;;
    --user)        [ -n "${2:-}" ] || die "--user 缺值";        RUN_USER="$2"; shift 2 ;;
    --port)        [ -n "${2:-}" ] || die "--port 缺值";        PORT="$2"; shift 2 ;;
    --stacks-root) [ -n "${2:-}" ] || die "--stacks-root 缺值"; STACKS_ROOT="$2"; shift 2 ;;
    --max-depth)   [ -n "${2:-}" ] || die "--max-depth 缺值";   MAX_DEPTH="$2"; shift 2 ;;
    --pypi-index)  [ -n "${2:-}" ] || die "--pypi-index 缺值";  PYPI_INDEX="$2"; shift 2 ;;
    -f|--force)    FORCE=1; shift ;;
    --no-build)    NO_BUILD=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) die "未知参数：$1（-h 看用法）" ;;
  esac
done

[ -n "$CMD" ] || CMD="all"

APP_DIR="${APP_DIR:-$(cd "$SELF_DIR/.." && pwd)}"
RUN_USER="${RUN_USER:-${SUDO_USER:-$(id -un)}}"
MAX_DEPTH="${MAX_DEPTH:-3}"

CONFIG="$APP_DIR/config.local.yaml"
VENV="$APP_DIR/backend/.venv"
UNIT_SRC="$SELF_DIR/lightpanel.service.in"
UNIT_DST="/etc/systemd/system/lightpanel.service"

# 端口优先级：命令行 > 已有配置 > 默认值
configured_port() {
  [ -f "$CONFIG" ] || return 1
  local p
  p="$(sed -n 's/^[[:space:]]*port:[[:space:]]*\([0-9][0-9]*\).*/\1/p' "$CONFIG" | head -1)"
  [ -n "$p" ] && printf '%s' "$p"
}
if [ -z "$PORT" ]; then
  PORT="$(configured_port || true)"
  PORT="${PORT:-9001}"
fi

# 以服务用户身份执行，避免 root 把 venv / dist 变成 root 所有
run_as_user() {
  if [ "$(id -un)" = "$RUN_USER" ]; then
    "$@"
  elif command -v runuser >/dev/null 2>&1; then
    runuser -u "$RUN_USER" -- "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -u "$RUN_USER" -- "$@"
  else
    su -s /bin/sh -c "$(printf '%q ' "$@")" "$RUN_USER"
  fi
}

is_root() { [ "$(id -u)" -eq 0 ]; }

need_root() {
  is_root || die "「$CMD」需要 root：sudo $0 $CMD"
}

sanity() {
  [ -d "$APP_DIR/backend" ] || die "APP_DIR 不像项目根目录：$APP_DIR"
  id "$RUN_USER" >/dev/null 2>&1 || die "用户不存在：$RUN_USER"
}

find_python() {
  local py
  py="$(command -v python3 || true)"
  [ -n "$py" ] || die "找不到 python3"
  "$py" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "需要 Python 3.11+，当前 $("$py" -V 2>&1)"
  printf '%s' "$py"
}

# ---------------------------------------------------------------- 各步骤

step_deps() {
  sanity
  local py
  py="$(find_python)"

  if [ -x "$VENV/bin/python" ]; then
    say "venv 已存在：$VENV"
  else
    say "建 venv：$VENV"
    run_as_user "$py" -m venv "$VENV"
  fi

  # 清华源对 setuptools 会返回 403（pip 建隔离环境时要拉它），默认走阿里云
  local pip_args=()
  if [ -n "$PYPI_INDEX" ]; then
    pip_args=(--index-url "$PYPI_INDEX")
    case "$PYPI_INDEX" in
      http://*) pip_args+=(--trusted-host "$(printf '%s' "$PYPI_INDEX" | awk -F/ '{print $3}')") ;;
    esac
  fi

  say "装依赖（${PYPI_INDEX:-PyPI 默认源}）"
  run_as_user "$VENV/bin/pip" install -q --upgrade pip
  run_as_user "$VENV/bin/pip" install -q "${pip_args[@]}" -e "$APP_DIR/backend"
  "$VENV/bin/python" -c 'import lightpanel' >/dev/null 2>&1 \
    || die "依赖装完了但 import lightpanel 失败，检查 $APP_DIR/backend"
  info "lightpanel $("$VENV/bin/python" -c 'import lightpanel; print(lightpanel.__version__)')"
}

step_frontend() {
  sanity
  local dist="$APP_DIR/frontend/dist"

  if [ -f "$dist/index.html" ] && [ "$FORCE" -eq 0 ]; then
    say "前端产物已存在，跳过：$dist/index.html"
    info "强制重建：$0 frontend --force"
    return 0
  fi
  [ "$NO_BUILD" -eq 0 ] || die "前端产物缺失（$dist/index.html），且指定了 --no-build"

  say "构建前端产物"
  if command -v npm >/dev/null 2>&1; then
    info "用宿主机 node 构建"
    ( cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build )
  else
    command -v docker >/dev/null 2>&1 \
      || die "宿主机没有 node 也没有 docker，无法构建前端。请先装 node，或在有 docker 的机器上构建好后拷入 frontend/dist"
    info "宿主机没装 node，用一次性 node 容器构建"
    docker run --rm -v "$APP_DIR/frontend:/app" -w /app node:22-alpine \
      sh -c 'npm ci --no-audit --no-fund && npm run build'
    # 容器以 root 构建，产物需要还给服务用户，否则以后自己 npm 写不进去
    if is_root; then
      chown -R "$RUN_USER:$RUN_USER" "$dist"
    fi
  fi

  [ -f "$dist/index.html" ] || die "构建结束但没找到 $dist/index.html"
  info "产物就绪：$(du -sh "$dist" | awk '{print $1}')"
}

step_config() {
  sanity

  if [ -f "$CONFIG" ] && [ "$FORCE" -eq 0 ]; then
    say "配置已存在，保留不动：$CONFIG"
    info "改端口 / 扫描目录：$0 config --force --port 9010 --stacks-root /ssd/app"
    info "当前令牌：$(sed -n 's/^[[:space:]]*api_token:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}.*/\1/p' "$CONFIG" | head -1)"
    return 0
  fi

  if [ -f "$CONFIG" ]; then
    local bak="$CONFIG.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$CONFIG" "$bak"
    say "已备份旧配置：$bak"
  fi

  say "生成配置：$CONFIG"
  local py token
  py="$(find_python)"
  token="lp_$(run_as_user "$py" -c 'import secrets; print(secrets.token_urlsafe(24))')"

  # search_paths 转成 YAML 列表；未指定时只放 /opt
  local roots="${STACKS_ROOT:-/opt}"
  local paths_yaml=""
  local IFS=','
  local r
  for r in $roots; do
    r="$(printf '%s' "$r" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$r" ] && paths_yaml="${paths_yaml}    - $r
"
  done

  cat > "$CONFIG" <<YAML
# LightPanel 宿主机直跑配置 —— 由 deploy/install-host.sh 生成
#
# 改完执行：sudo systemctl restart lightpanel
# 重新生成：$0 config --force [--port N] [--stacks-root A,B]
env: prod

server:
  host: 0.0.0.0
  port: $PORT
  docs: false            # 开鉴权后不暴露 /docs 与 /openapi.json

security:
  enabled: true
  api_token: "$token"
  header_name: X-LightPanel-Token

compose:
  enabled: true
  runner: local          # 与 daemon 同一文件系统，不需要 agent
  search_paths:          # 面板扫描 compose 项目的目录
$paths_yaml  max_depth: $MAX_DEPTH

catalog:
  provider: yaml
  path: data/catalog.yaml

commands:
  extra_file: data/commands.yaml
YAML

  if is_root; then
    chown "$RUN_USER:$RUN_USER" "$CONFIG"
  fi
  chmod 600 "$CONFIG"

  info "端口：$PORT"
  printf '    扫描目录：\n'
  printf '%s' "$paths_yaml"
  printf '\n    登录令牌（请自行保存）：%s\n' "$token"
}

step_data() {
  sanity
  say "初始化数据文件"
  mkdir -p "$APP_DIR/data"

  if [ -f "$APP_DIR/data/catalog.yaml" ]; then
    info "data/catalog.yaml 已存在，保留"
  else
    cp "$APP_DIR/backend/data/catalog.example.yaml" "$APP_DIR/data/catalog.yaml"
    info "data/catalog.yaml 已从示例创建"
  fi

  if [ -f "$APP_DIR/data/commands.yaml" ]; then
    info "data/commands.yaml 已存在，保留"
  elif [ -f "$APP_DIR/backend/data/commands.yaml" ]; then
    cp "$APP_DIR/backend/data/commands.yaml" "$APP_DIR/data/commands.yaml"
    info "data/commands.yaml 已创建"
  fi

  if is_root; then
    chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/data"
  fi
}

step_service() {
  need_root
  sanity
  [ -f "$UNIT_SRC" ] || die "缺少单元模板：$UNIT_SRC"

  say "安装 systemd 单元"
  # 端口被手工起的实例占着时 systemd 会直接起不来；已经在跑的服务不要动
  local pid=""
  if command -v ss >/dev/null 2>&1; then
    pid="$(ss -tlnp 2>/dev/null | sed -n "s/.*:$PORT .*pid=\([0-9]*\).*/\1/p" | head -1)"
  fi
  if [ -n "$pid" ] && ! systemctl is-active --quiet lightpanel; then
    info "端口 $PORT 被 PID $pid 占用，先停掉它"
    kill "$pid" 2>/dev/null || true
    sleep 2
  fi

  sed -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@RUN_USER@|$RUN_USER|g" "$UNIT_SRC" > "$UNIT_DST"
  systemctl daemon-reload
  systemctl enable --now lightpanel

  # 从进程起来到 bind 端口有 3~6 秒（读配置 + 挂 SPA），固定 sleep 会误报未监听
  local i=0
  while [ "$i" -lt 20 ]; do
    ss -tln 2>/dev/null | grep -q ":$PORT " && break
    systemctl is-active --quiet lightpanel || break
    i=$((i + 1))
    sleep 1
  done

  if ss -tln 2>/dev/null | grep -q ":$PORT "; then
    info "已监听 0.0.0.0:$PORT"
    info "运行身份：$RUN_USER    配置：$CONFIG"
  else
    warn "端口 $PORT 还没监听，看日志：journalctl -u lightpanel -n 50 --no-pager"
  fi
}

step_status() {
  say "服务"
  if ! command -v systemctl >/dev/null 2>&1; then
    warn "没有 systemctl，这不是 systemd 环境"
  else
    local active enabled mainpid restarts
    active="$(systemctl is-active lightpanel 2>/dev/null || true)"
    enabled="$(systemctl is-enabled lightpanel 2>/dev/null || true)"
    mainpid="$(systemctl show lightpanel -p MainPID --value 2>/dev/null || true)"
    restarts="$(systemctl show lightpanel -p NRestarts --value 2>/dev/null || true)"
    info "状态：${active:-未知}（开机自启：${enabled:-未知}）"
    info "PID：${mainpid:-—}    累计重启：${restarts:-0}"
  fi

  say "端口"
  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
    info "0.0.0.0:$PORT 已监听"
  else
    info ":$PORT 未监听"
  fi

  say "接口"
  local token=""
  if [ -f "$CONFIG" ]; then
    token="$(sed -n 's/^[[:space:]]*api_token:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}.*/\1/p' "$CONFIG" | head -1)"
  fi
  if command -v curl >/dev/null 2>&1; then
    local code
    code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health" || true)"
    info "/api/health → ${code:-无响应}"
    if [ -n "$token" ]; then
      code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' -H "X-LightPanel-Token: $token" \
        "http://127.0.0.1:$PORT/api/system" || true)"
      info "/api/system（带令牌）→ ${code:-无响应}"
    fi
  else
    info "没有 curl，跳过探活"
  fi

  if [ -n "$token" ]; then
    say "登录"
    printf '    令牌：%s\n' "$token"
    printf '    地址：http://<本机IP>:%s\n' "$PORT"
  else
    warn "没读到登录令牌（$CONFIG 不存在？）"
  fi
}

step_logs() {
  command -v journalctl >/dev/null 2>&1 || die "没有 journalctl"
  journalctl -u lightpanel -f -n 50
}

step_restart() {
  is_root || die "重启需要 root：sudo $0 restart"
  systemctl restart lightpanel
  local i=0
  while [ "$i" -lt 20 ]; do
    ss -tln 2>/dev/null | grep -q ":$PORT " && break
    i=$((i + 1))
    sleep 1
  done
  info "状态：$(systemctl is-active lightpanel)"
}

step_stop() {
  is_root || die "停止需要 root：sudo $0 stop"
  systemctl stop lightpanel
  info "已停止（开机自启仍保留，恢复：sudo systemctl start lightpanel）"
}

# ---------------------------------------------------------------- 分发

# `all` 的最后一步是装 systemd 单元，非 root 就没法完成。提前挡掉，
# 免得先把几分钟的依赖安装跑完，才在最后一步失败。
if [ "$CMD" = "all" ] && ! is_root; then
  die "「all」包含安装 systemd 服务，需要 root：sudo $0 all
只想准备运行环境：$0 deps && $0 frontend && $0 config && $0 data"
fi

case "$CMD" in
  all)
    step_deps
    step_frontend
    step_config
    step_data
    step_service
    step_status
    ;;
  deps)     step_deps ;;
  frontend) step_frontend ;;
  config)   step_config ;;
  data)     step_data ;;
  service)  step_service ;;
  status)   step_status ;;
  logs)     step_logs ;;
  restart)  step_restart ;;
  stop)     step_stop ;;
  *)        die "未知子命令：$CMD" ;;
esac

if [ "$CMD" = "all" ]; then
  printf '\n安装完成。常用命令：\n'
  printf '  %s status           查看状态与令牌\n' "$0"
  printf '  %s logs             跟踪日志\n' "$0"
  printf '  sudo %s restart     重启（改完配置后）\n' "$0"
fi
