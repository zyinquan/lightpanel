# 测试指南

测试策略的核心是一条：**所有测试都离线运行，不依赖真实 Docker、不依赖真实主机指标**。这靠"假适配器"实现——它们与真实适配器实现同一套端口协议，因此测试覆盖的是真实业务代码路径，而非 mock 出来的替身。

```
后端：pytest     202 个用例，覆盖率 ~89%
前端：vitest      56 个用例
```

---

## 后端

### 运行

```bash
cd backend
pytest                                            # 全量
pytest -q -k "command"                            # 按名称筛
pytest -q tests/unit tests/integration            # 分目录
pytest -q --cov=lightpanel --cov-report=term-missing
pytest -q --cov=lightpanel --cov-report=html      # 生成 htmlcov/
```

`pyproject.toml` 中已开启 `asyncio_mode = "auto"`，异步测试无需额外装饰器。

### 目录

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/conftest.py` | 全部 fixture：`clock` `metrics_provider` `catalog_repository` `container_engine` `executor` `stack_engine` `policy` `*_service` `test_config` `app` `client` |
| `unit/test_config.py` | 分层配置：YAML、环境变量嵌套覆盖、非法字段拒绝、类型强转 |
| `unit/test_system_service.py` | 快照缓存 TTL、历史环形缓冲上限、失效刷新 |
| `unit/test_catalog_service.py` | CRUD、标签归一化与统计、过滤（任意/全部命中）、搜索、排序、重排 |
| `unit/test_container_service.py` | 动作归一化、未知动作报错、引擎不可用传播、日志 |
| `unit/test_stack_service.py` | 栈发现、状态聚合、各 compose 动作的 argv 组装 |
| `unit/test_command_policy.py` | 白名单、解释器拦截、危险参数拦截、超时夹紧 |
| `unit/test_command_service.py` | 命令注册、模板渲染、预览、执行、超时与失败结果 |
| `unit/test_command_definitions.py` | YAML 命令定义加载与校验 |
| `unit/test_adapters.py` | psutil 归一化、YAML 仓储读写、subprocess/fake 执行器、时间戳解析 |
| `unit/test_docker_api.py` | Docker Engine API 适配器（用 httpx MockTransport，不发真实请求） |
| `unit/test_platform.py` | 平台相关分支（socket 路径、Windows 兼容） |
| `unit/test_schemas.py` | DTO 转换与格式化辅助函数 |
| `integration/test_api.py` | 通过 `TestClient` 打全量 HTTP 流程：健康检查、系统、目录、容器动作、栈动作、命令执行、404/400 错误形状 |
| `integration/test_auth.py` | 鉴权开关、令牌校验、受保护路由 |

### 关键设计

1. **假适配器是一等公民**：`FakeContainerEngine` 维护真实的容器状态机（start → running，stop → exited），`FakeCommandExecutor` 可编程地排队响应或按 argv 匹配返回。
2. **时钟可注入**：`FixedClock` 让缓存、历史、超时相关的断言完全确定。
3. **HTTP 集成测试不动真网络**：`TestClient` 直连 ASGI 应用；Docker API 适配器则用 `httpx.MockTransport` 验证 URL 与方法。
4. **测试配置永不触碰宿主机**：`test_config` fixture 强制 `metrics.provider=fake`、`docker.mode=fake`、`catalog.provider=memory`、`commands.executor=fake`。

### 新增测试的建议

- 服务层行为 → 放 `tests/unit/`，直接注入假适配器；
- 新增适配器 → 至少覆盖"正常路径 + 错误路径 + 边界解析"；
- 新增端点 → 在 `tests/integration/test_api.py` 补一条端到端用例，断言状态码与错误码。

---

## 前端

### 运行

```bash
cd frontend
npm test              # vitest run
npm run test:watch
npx vitest run --coverage
```

配置在 `vite.config.ts` 的 `test` 段：`jsdom` 环境、全局 API、覆盖 `src/**`。

### 目录

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/unit/format.spec.ts` | `formatBytes` `formatDuration` `formatDateTime` `usageColor` `stateColor/Label` `colorFromString` `initials` |
| `tests/unit/client.spec.ts` | URL 与查询参数拼接、token 请求头、JSON 序列化、404 → `ApiError{status, code}`、204 空响应、容器/栈/命令的路径与请求体 |
| `tests/unit/composables.spec.ts` | `usePolling` 立即取数、错误回调、`enabled` 开关、并发去重；`useToast` 推入/关闭/清空 |
| `tests/components/presentation.spec.ts` | `UsageBar` `StatCard` `SparkLine` `EmptyState` `OutputConsole` 的渲染与边界（空数据、越界百分比、stderr 合并） |
| `tests/components/interactive.spec.ts` | `SoftwareCard` `ContainerCard` `StackCard` `TagFilter` `ConfirmDialog` 的事件派发与状态（运行中/已停止的动作差异、高危确认的输入校验） |

### 约定

- 组件测试用 `@vue/test-utils` 的 `mount`，断言以**用户可见文本 / class / 派发事件**为准，不依赖内部实现细节。
- 涉及 `Teleport` 的组件（对话框）在测试中 stub 掉：`mount(C, { global: { stubs: { Teleport: true } } })`。
- 网络一律通过注入 `fetchImpl` 模拟；`Response` 每次调用都要新建（body 只能读一次），测试里用 `responder()` 工厂。

```ts
const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })))
const client = new ApiClient({ fetchImpl: fetchMock as unknown as typeof fetch })
```

---

## 真实环境联调（手动）

离线测试覆盖业务逻辑，但 Docker API 的流式响应、compose 退出码、端口发布这类问题只有真机才暴露。上线前建议跑一遍下面的手动清单。

准备：一个可用的 Docker 引擎（本机 socket 或开了 2375 的 TCP 端点）。

```bash
# 1) 起一个长跑容器当被控对象
docker run -d --name lpdemo python:3.13-slim sleep infinity

# 2) 用真实引擎启动后端（mode: api，host 指向 http://127.0.0.1:2375）
python -m lightpanel -c /path/to/lp-docker.yaml
```

逐项点检：

| 检查项 | 预期 |
| --- | --- |
| `GET /api/system` | 返回真实 CPU / 内存 / 磁盘，`uptime` 与系统一致 |
| `GET /api/containers` | 能列出 `lpdemo`，`state=running` |
| `POST /api/containers/lpdemo/stop` 后 `docker ps` | 容器真的停了 |
| `POST .../start`、`.../restart` | 状态切回 running |
| `GET /api/containers/lpdemo/logs` | 纯文本，**没有** `\x01\x00\x00\x00` 之类帧头 |
| `POST /api/stacks/<name>/up` / `down` | `docker compose ps` 与面板状态一致 |
| `POST /api/commands/<id>/run` | 自定义命令真实执行，`exit_code` 与 CLI 一致 |
| 刷新 `/containers` | 200 且返回 `index.html`（history 路由回退） |
| `GET /api/unknown` | 404，不能回退成 HTML |

容易踩的坑：

- **容器日志**：非 TTY 容器的 `/logs` 是多路复用流（每帧 8 字节头），直接当文本用会显示乱码，适配器做了拆帧。
- **Windows + Docker Desktop**：内置驱动器/Hyper-V 后端未开启文件共享时，宿主机目录挂载会卡住容器创建；`/var/run/docker.sock` 挂不进去时面板会降级成 `NullContainerEngine`（容器页显示"引擎不可用"），这是预期行为。

## 容器化部署联调（手动）

面板自己跑在容器里、控制宿主机引擎，这条路和"直接跑在宿主机"的差异最大，建议单独过一遍。
本机实测用 Docker Desktop（Hyper-V 后端）走 TCP API 模式：

```bash
docker run -d --name lpdemo python:3.13-slim sleep infinity
LIGHTPANEL_PORT=9021 docker compose -f deploy/docker-compose.api.yml up -d
docker cp ./some-compose-project lightpanel:/data/stacks      # 给面板一个它看得见的 compose 项目
```

| 检查项 | 预期 |
| --- | --- |
| `GET /api/containers` | 列出宿主机容器（含面板自身），`compose_project` 正确 |
| 容器 stop / start / restart | `docker ps` 状态与面板一致 |
| `GET /api/containers/<name>/logs` | 纯文本，无帧头 |
| 栈 `up`（项目在 `/data` 下） | 宿主机出现 `docker compose ps` 里的容器 |
| 栈 `down` / `restart`（项目在宿主机别处） | 正常执行 —— 按项目标签操作，不需要配置文件 |
| 栈 `up`（配置文件在宿主机别处） | 400 `not readable from this host`，并在 `hint` 里给处置建议 |
| 自定义命令 `stack.ps` | 传宿主机路径的 `working_dir` 时不再被拒（无 cwd 运行） |
| `GET /api/system` 磁盘列表 | 只有真实挂载目录，不出现 `/etc/hostname` 这类单文件挂载 |
| 无 socket / 无 `docker.host` 启动 | `/api/containers` 返回 503，消息里说明"mount /var/run/docker.sock 或设置 docker.mode = api" |
| 开启 `security.enabled` 后 | 无令牌 401、错误令牌 401、正确令牌 200；`/` 静态资源仍可访问 |
| 重建容器后 | `/data` 命名卷里的软件目录与自定义命令仍在 |
| 软件卡片点击 | 整张卡片（含空白区、图标）都能在**新窗口**打开条目地址；只填 `nas:8096` 这类无协议地址也能跳对 |
| 概览页口径条 | 容器内未配代理时显示黄色的「容器内指标」+ 原因；配了 `metrics.remote_url` 且代理在线时显示「宿主机指标 · 来自 <宿主机名> · 采集自宿主机代理」 |
| 停掉宿主机代理 | 面板不报错，自动回落到容器指标，提示条里写明「宿主机代理不可用」 |
| **compose 交给宿主机代理**（`compose.runner=agent`） | 宿主机 `lightpanel-agent --stacks-root E:/docker-test` 在线时，`/api/stacks` 里能看到该目录下的全部项目，`config_files` 是 `E:\...` 形式的宿主路径 |
| **带源码挂载的开发栈** | 面板点「启动」后 `docker inspect` 的挂载源是 `E:\docker-test\<项目>\src`，容器内 `/app` 能看到宿主机上的文件（对照：`runner=local` 时源路径会变成 `/data/...` 且 `/app` 为空） |
| 代理端口写成死端口 | `/api/stacks` 返回 503 `engine_unavailable`，消息里提示「连不上宿主机代理…请确认已启动 lightpanel-agent」；栈页显示红色提示条而不是「没有编排栈」 |

容易踩的坑：

- **容器内的系统指标口径是混的**：Linux 容器里 CPU / 内存 / 负载本来就是整机数字（内核不按容器隔离 `/proc`），但网络只算本容器、磁盘只含挂进容器的目录；Docker Desktop 上则整体是那台 Linux 虚拟机的数字。要统一口径就在宿主机跑 `lightpanel-agent`。
- **宿主机路径在容器内不可见**：栈的 `config_files` / `working_dir` 来自 compose 标签，属于引擎主机路径。`down`/`restart` 不依赖它，`up`/`pull` 依赖。要么把项目放到 `compose.search_paths`（默认含 `/data`）下，要么直接用 `compose.runner=agent` 交给宿主机代理。
- **容器内执行 compose 会把相对挂载解析错**：`./src:/app` 被解析成容器内绝对路径交给宿主机 docker，宿主机上不存在 → docker 建空目录顶上，容器起来了、代码没挂上，**不报错**。带源码挂载的开发栈必须用 `compose.runner=agent`。
- **Git Bash 会改写参数里的类 Unix 路径**：`docker cp x lightpanel:/data/y`、`docker exec ... /data/y` 都可能被转成 Windows 路径，前面加 `MSYS_NO_PATHCONV=1`。
- **内嵌预览里点卡片可能"没反应"**：沙箱化 iframe 会静默丢弃 `target="_blank"`。卡片现在自己接管开窗，被拦截时会把地址复制到剪贴板并提示；用独立浏览器打开面板即可正常新开标签页。

---

## CI 建议

```yaml
- run: pip install -e ".[dev]" && pytest --cov=lightpanel --cov-fail-under=85
- run: ruff check src tests && mypy src
- run: npm ci && npm run build && npm test
```

三个关卡分别守住：行为正确、静态质量、前端可构建与契约一致。
