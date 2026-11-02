.PHONY: help install dev fe be test lint fmt build docker clean agent

PYTHON ?= python
NPM    ?= npm
AGENT_HOST ?= 0.0.0.0
AGENT_PORT ?= 9101
# agent 允许管理的 compose 根目录，可留空（只提供指标）
STACKS_ROOT ?=
# 递归扫描深度（只在 STACKS_ROOT 非空时生效；面板侧的 compose.max_depth 在此模式下无效）
STACKS_DEPTH ?= 4

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk -F ':.*?## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## 安装后端与前端依赖
	cd backend && $(PYTHON) -m pip install -e ".[dev]"
	cd frontend && $(NPM) install

be: ## 启动后端（9000）
	cd backend && $(PYTHON) -m lightpanel --reload

fe: ## 启动前端（5273）
	cd frontend && $(NPM) run dev

test: ## 运行全部测试
	cd backend && $(PYTHON) -m pytest -q --cov=lightpanel --cov-report=term
	cd frontend && $(NPM) test

lint: ## 静态检查
	cd backend && $(PYTHON) -m ruff check src tests && $(PYTHON) -m mypy src
	cd frontend && $(NPM) run typecheck

fmt: ## 格式化
	cd backend && $(PYTHON) -m ruff format src tests

build: ## 构建前端产物
	cd frontend && $(NPM) run build

docker: ## 构建并启动容器
	docker compose -f deploy/docker-compose.yml up -d --build

agent: ## 在宿主机启动代理（指标 + compose；STACKS_ROOT 栈根目录，STACKS_DEPTH 扫描深度）
	cd backend && $(PYTHON) -m lightpanel.agent --host $(AGENT_HOST) --port $(AGENT_PORT) $(if $(AGENT_TOKEN),--token $(AGENT_TOKEN)) $(if $(STACKS_ROOT),--stacks-root $(STACKS_ROOT) --max-depth $(STACKS_DEPTH))

clean: ## 清理构建与缓存产物
	rm -rf frontend/dist backend/.pytest_cache backend/htmlcov backend/.coverage
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
