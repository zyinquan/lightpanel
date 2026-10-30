# 多阶段构建：前端产物与后端打进同一个镜像，单进程同时提供 API 与 SPA。
# 构建上下文必须是仓库根目录：
#   docker build -f deploy/Dockerfile -t lightpanel:latest .

# ---------- 阶段一：构建前端 ----------
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：运行时 ----------
FROM python:3.13-slim AS runtime

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

# backend/pyproject.toml 里 readme = "../README.md"，所以 README 必须落在 /app/README.md
COPY README.md ./README.md
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src ./backend/src
RUN pip install ./backend

# 前端产物：后端检测到该目录存在即自动托管 SPA
COPY --from=frontend /build/frontend/dist /app/frontend/dist

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
