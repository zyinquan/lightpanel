# 多阶段构建：前端产物与后端打进同一个镜像，单进程同时提供 API 与 SPA。
# 构建上下文必须是仓库根目录：
#   docker build -f deploy/Dockerfile -t lightpanel:latest .

# ---------- 阶段一：构建前端 ----------
FROM node:22-alpine AS frontend
# 内网或国内网络可覆盖：--build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org
WORKDIR /build/frontend
RUN npm config set registry "$NPM_REGISTRY"
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：取 docker CLI + compose 插件 ----------
# 栈管理（docker compose up/down）与内置命令都通过子进程调用 docker，
# 运行镜像里没有 CLI 时这两个功能会在容器内直接报 command not found。
FROM docker:cli AS dockercli

# ---------- 阶段三：运行时 ----------
FROM python:3.13-slim AS runtime

# 内网或国内网络可覆盖：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LIGHTPANEL_SERVER__HOST=0.0.0.0 \
    LIGHTPANEL_SERVER__PORT=9000 \
    LIGHTPANEL_CATALOG__PATH=/data/catalog.yaml \
    LIGHTPANEL_CATALOG__EXAMPLE_FILE=/app/data-examples/catalog.example.yaml \
    LIGHTPANEL_COMMANDS__EXTRA_FILE=/data/commands.yaml \
    LIGHTPANEL_COMMANDS__EXAMPLE_FILE=/app/data-examples/commands.yaml

WORKDIR /app

# backend 的 pyproject 用 readme = "README.md"，故后端 README 必须随源码一起进镜像
COPY backend/README.md ./backend/README.md
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src ./backend/src
RUN pip install --index-url "$PIP_INDEX_URL" ./backend

# 前端产物：后端检测到该目录存在即自动托管 SPA
COPY --from=frontend /build/frontend/dist /app/frontend/dist

# docker CLI 与 compose 插件（Go 静态二进制，跨发行版可用）。
# 只取 compose，buildx 这些面板用不到，能省 60MB 左右。
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose

# 出厂示例数据；首次启动若 /data 为空，应用会自动播种 catalog.yaml 与 commands.yaml
COPY backend/data /app/data-examples

RUN useradd --create-home --shell /bin/bash lightpanel \
    && mkdir -p /data \
    && chown -R lightpanel:lightpanel /data /app
USER lightpanel

EXPOSE 9000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/api/health').read()" || exit 1

CMD ["lightpanel"]
