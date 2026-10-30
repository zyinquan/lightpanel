.PHONY: help install dev fe be test lint fmt build docker clean

PYTHON ?= python
NPM    ?= npm

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

clean: ## 清理构建与缓存产物
	rm -rf frontend/dist backend/.pytest_cache backend/htmlcov backend/.coverage
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
