# 测试指南

测试策略的核心是一条：**所有测试都离线运行，不依赖真实 Docker、不依赖真实主机指标**。这靠"假适配器"实现——它们与真实适配器实现同一套端口协议，因此测试覆盖的是真实业务代码路径，而非 mock 出来的替身。

```
后端：pytest     187 个用例，覆盖率 ~89%
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

## CI 建议

```yaml
- run: pip install -e ".[dev]" && pytest --cov=lightpanel --cov-fail-under=85
- run: ruff check src tests && mypy src
- run: npm ci && npm run build && npm test
```

三个关卡分别守住：行为正确、静态质量、前端可构建与契约一致。
