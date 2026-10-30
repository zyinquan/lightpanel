# 开发指南

## 环境要求

| 组件 | 版本 |
| --- | --- |
| Python | ≥ 3.11（开发用 3.13） |
| Node.js | ≥ 20（开发用 22） |
| Docker | 可选；没有也能完整开发（用 fake 适配器） |

## 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

常用命令：

```bash
python -m lightpanel --reload          # 热重载启动（9000）
python -m lightpanel -c config.yaml    # 指定配置
python -m lightpanel --port 8080       # 覆盖端口

pytest                                  # 全量测试
pytest -q tests/unit/test_config.py     # 单个文件
pytest -q --cov=lightpanel --cov-report=term-missing

ruff check src tests                    # 静态检查
ruff format src tests                   # 格式化
mypy src                                # 类型检查
```

### 目录约定

```
src/lightpanel/
├── domain/       # 只放模型、协议、错误 —— 不允许 import 框架或适配器
├── services/     # 用例编排 —— 只允许依赖 domain.ports
├── adapters/     # 具体技术实现 —— 每个端口至少一真一假两个实现
├── api/          # HTTP —— 只允许依赖 services 与 domain（经 DTO 转换）
└── composition.py
```

可以在 CI 里用一条 import 规则守住这条边界（`domain` 与 `services` 不得出现 `import psutil` / `import httpx` / `from fastapi`）。

## 前端

```bash
cd frontend
npm install
npm run dev          # 5273 端口，/api 已代理到 127.0.0.1:9000
npm run build        # vue-tsc 类型检查 + 生产构建
npm run typecheck
npm test             # vitest
npm run test:watch
```

若后端不在默认地址，用环境变量指定：`LIGHTPANEL_UPSTREAM=http://192.168.1.10:9000 npm run dev`。

### 目录约定

```
src/
├── api/          # client.ts（唯一发请求的地方）+ types.ts（后端契约）
├── components/   # 纯展示/交互，不直接发请求（除 CommandRunner 这类自包含组件）
├── views/        # 页面：负责取数、编排、状态
├── composables/  # usePolling / useToast
├── utils/        # 纯函数（格式化等）
└── styles/       # 全局原子类与主题变量
```

组件通信一律用 `props + emits`，不引入全局状态库——面板数据量小，取数集中在视图层足够。

---

## 如何扩展：新增一个适配器

以支持 Podman 为例（假设已有 CLI）：

1. **实现端口**（不改任何既有文件）：

```python
# src/lightpanel/adapters/docker/podman_engine.py
from ...domain.ports import ContainerEngine

class PodmanContainerEngine:
    async def list_containers(self, *, include_stopped: bool = True) -> list[ContainerInfo]: ...
    async def get_container(self, container_id: str) -> ContainerInfo: ...
    async def start(self, container_id: str) -> None: ...
    # ... 其余方法按 ports.ContainerEngine 实现
```

2. **加配置开关**：

```python
# config.py
class DockerConfig(_Base):
    mode: Literal["auto", "api", "podman", "fake"] = "auto"
```

3. **在组合根接线**（唯一需要修改的既有文件）：

```python
# composition.py
if config.docker.mode == "podman":
    return PodmanContainerEngine(...)
```

服务层、路由层、前端均无需改动。测试可以照抄 `tests/unit/test_docker_api.py` 的结构。

## 如何扩展：新增一个端点

1. 在 `services/` 写用例（或复用现有服务方法）；
2. 在 `api/schemas.py` 加 DTO 与 `from_domain()`；
3. 在 `api/routers/` 加路由模块，并在 `routers/__init__.py` 导出；
4. 在 `app.py` 挂载（若新建模块）；
5. 在 `frontend/src/api/types.ts` 与 `client.ts` 补类型与方法；
6. 补测试（后端集成测试 + 前端组件/客户端测试）。

## 如何扩展：新增一个前端页面

1. `src/views/XxxView.vue` 中用 `usePolling(() => api.xxx(), { interval })` 取数；
2. 在 `src/router/index.ts` 注册路由（含 `meta.title`）；
3. 在 `AppShell.vue` 的 `NAV` 数组加一项；
4. 视图测试参考 `tests/components/*.spec.ts`，用 `vi.mock('@/api/client')` 隔离网络。

## 代码风格

- Python：ruff（行长 100，启用 `E F W I UP B C4 SIM`），导入按 isort 规则分组；类型注解全覆盖，`mypy src` 应无错误。
- TypeScript：`strict` 模式开启，`noUnusedLocals` / `noUnusedParameters` 生效；`npm run build` 会先跑 `vue-tsc`。
- 提交前至少跑通：`pytest`、`ruff check`、`npm test`、`npm run build`。

## 调试小技巧

- 想看真实 Docker 行为但本机没有 Docker：`docker.mode: fake` + `commands.executor: fake`，接口与 UI 行为完全一致。
- 想让指标稳定便于对比截图：`metrics.provider: fake`。
- 想看命令到底拼成了什么：调 `POST /api/commands/{id}/preview`，或用前端命令页的预览行。
- 后端日志：`logging.level: DEBUG`；结构化采集用 `logging.format: json`。
