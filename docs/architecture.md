# 架构设计

LightPanel 采用**端口与适配器（Ports & Adapters / 六边形架构）**。目标是让"采集指标""读软件目录""控制 Docker""执行命令"这四类外部依赖都可替换，业务规则不被任何具体技术绑定。

## 分层

```
        HTTP / JSON            领域对象              外部世界
   ┌──────────────────┐   ┌──────────────┐   ┌────────────────────┐
   │  api/            │   │  domain/     │   │  adapters/         │
   │  路由 · DTO      │──▶│  模型 · 端口  │◀──│  psutil / Docker / │
   │  错误处理 · 鉴权 │   │  错误 · 时钟  │   │  Compose / YAML /  │
   └────────┬─────────┘   └──────▲───────┘   │  subprocess / fake │
            │                    │           └────────────────────┘
            ▼                    │
   ┌──────────────────┐          │
   │  services/       │──────────┘
   │  业务用例         │  只依赖 ports 里的 Protocol
   └──────────────────┘
            ▲
            │ 唯一的装配处
   ┌──────────────────┐
   │  composition.py  │
   └──────────────────┘
```

**依赖方向始终是向内的**：`adapters → domain ← services ← api`。`domain` 不 import 任何框架，`services` 不 import 任何适配器，`api` 不 import 任何适配器（只从 `composition` 拿到已装配好的容器）。

## 领域层（domain）

| 文件 | 内容 |
| --- | --- |
| `models.py` | 值对象与实体：`SystemSnapshot` `CpuMetrics` `MemoryMetrics` `DiskMetrics` `NetworkMetrics` `HostInfo` `SoftwareEntry` `ContainerInfo` `StackInfo` `CommandDefinition` `CommandResult` `CommandContext` |
| `ports.py` | 抽象协议（`typing.Protocol`）：`MetricsProvider` `CatalogRepository` `ContainerEngine` `StackEngine` `CommandExecutor` `Clock` |
| `errors.py` | 统一错误基类与子类：`NotFoundError` `ValidationError` `EngineUnavailableError` `CommandRejectedError` `CommandFailedError` `StorageError` |
| `clock.py` | `SystemClock` / `FixedClock`，让时间可注入，测试可确定 |

`ports.py` 里的协议是**结构化类型**：任何满足方法签名的对象都可以作为实现，无需继承。这是开闭原则的关键——新增适配器不需要修改端口定义，也不需要修改服务。

## 服务层（services）

每个服务对应一组用例，构造函数只接收端口：

```python
class ContainerService:
    def __init__(self, engine: ContainerEngine, clock: Clock | None = None) -> None: ...
```

| 服务 | 职责 |
| --- | --- |
| `SystemService` | 采集快照、写入趋势历史（`history_size` 环形缓冲）、快照缓存（`cache_ttl`） |
| `CatalogService` | 条目 CRUD、标签归一化与统计、过滤/搜索/排序、重排 |
| `ContainerService` | 容器列表/详情/生命周期动作/日志，动作名归一化与校验 |
| `StackService` | 栈发现、状态聚合（按成员容器推导 running/total）、Compose 动作 |
| `CommandService` | 命令注册、模板渲染、预览、执行、超时与结果封装 |
| `CommandPolicy` | 安全策略：二进制白名单、shell 解释器拦截、危险参数拦截、超时夹紧 |
| `builtin_commands` | 内置命令（与用户命令同构，仅 `builtin=True`） |

服务不认识 HTTP，也不认识 Docker；它们只"说领域语言"。

## 适配器层（adapters）

每个端口都有**真实实现**和**假实现**，假实现用于测试与无 Docker 环境的演示：

| 端口 | 真实实现 | 假实现 |
| --- | --- | --- |
| `MetricsProvider` | `PsutilMetricsProvider` | `FakeMetricsProvider` |
| `CatalogRepository` | `YamlCatalogRepository` | `InMemoryCatalogRepository` |
| `ContainerEngine` | `DockerApiContainerEngine`（Unix socket + httpx） | `FakeContainerEngine` / `NullContainerEngine` |
| `StackEngine` | `ComposeStackEngine`（`docker compose` 子进程） | 同上（fake 中一并实现） |
| `CommandExecutor` | `SubprocessCommandExecutor` | `FakeCommandExecutor`（可编程响应） |
| `Clock` | `SystemClock` | `FixedClock` |

`docker.mode: auto` 时组合根会尝试真实引擎，连接失败自动降级为 `NullContainerEngine`（接口仍可用，返回"引擎不可用"），避免启动崩溃。

## 组合根（composition.py）

唯一知道"哪个实现配哪个端口"的地方：

```python
def build_container(config: AppConfig) -> AppContainer:
    engine = _build_engine(config)          # auto / api / fake
    return AppContainer(
        config=config,
        metrics_provider=_build_metrics(config),
        catalog_repository=_build_catalog(config),
        container_engine=engine,
        stack_engine=_build_stack(config),
        command_executor=_build_executor(config),
        command_definitions=_load_command_definitions(config),
        auth=_build_auth(config),
    )
```

`create_app(container=...)` 允许测试直接注入容器，生产则由 `create_app(config=...)` 内部调用组合根。**新增一种实现只需改这一个文件**（配置驱动时甚至不用改代码）。

## 开闭原则的具体体现

| 想做的事 | 需要改动的地方 |
| --- | --- |
| 支持 Podman 而非 Docker | 新增 `adapters/docker/podman_engine.py` + `composition.py` 一处分支 |
| 把软件目录换成 SQLite | 新增 `adapters/catalog/sqlite_repository.py` + `composition.py` 一处分支 |
| 指标改为从 Prometheus 拉取 | 新增 `adapters/metrics/prometheus_provider.py` + 配置枚举 |
| 容器里的面板要看宿主机指标 | 已内置：`adapters/metrics/remote_provider.py`（取代理）+ `fallback_provider.py`（回落），配置 `metrics.remote_url` 即启用 |
| 容器里的面板要真正管理 compose 栈 | 已内置：`adapters/docker/agent_compose.py`（面板侧）+ `services/host_compose.py`（代理侧），配置 `compose.runner=agent` 即启用；两套实现都实现/使用同一组 `ComposeBackend` 接口 |
| 新增一个 REST 端点 | 新增路由模块 + `routers/__init__.py`；服务与领域不动 |
| 新增一种命令 | 往 `data/commands.yaml` 追加一条，无需改代码 |

一句话：**扩展靠新增，修改靠配置**。

## HTTP 层（api）

- `app.py`：应用工厂，负责中间件、错误处理、路由挂载、静态资源挂载、生命周期。
- `routers/*`：一个模块一个资源，只做参数解析、调用服务、DTO 转换。
- `schemas.py`：Pydantic DTO，`XxxOut.from_domain()` 承担领域对象 → JSON 的转换，序列化知识不外溢。
- `errors.py`：把 `domain.errors` 映射为 HTTP 状态码与统一响应体 `{code, message, details}`。
- `dependencies.py`：类型化的依赖注入快捷方式（`SystemDep` / `CatalogDep` / ...）。
- `security.py`：可选单令牌鉴权，支持请求头 / Cookie / 查询参数三种携带方式。

## 前端架构

- `src/api/client.ts` 是唯一知道 HTTP 细节的地方，其余组件只调用函数。这样后端路径或协议变化时只改一处。
- `src/api/types.ts` 与后端 `schemas.py` 一一对应，是前后端的契约。
- `usePolling` 统一处理轮询、可见性暂停、并发去重与错误回调；页面只声明"要什么数据、多久一次"。
- 视图（views）负责数据编排，组件（components）只负责渲染与事件派发，因此组件可在无网络环境下单测。

## 贯穿全局的几个决策

1. **时间可注入**：所有涉及时间的服务接收 `Clock`，测试用 `FixedClock` 得到确定性结果。
2. **错误分类而非字符串匹配**：领域错误 → HTTP 状态码的映射集中在 `api/errors.py`。
3. **假实现是一等公民**：fake 适配器与真实适配器实现同一协议，行为尽量一致（例如 fake 引擎也维护容器状态机）。
4. **危险操作默认需要确认**：`CommandDefinition.confirm/danger` 会驱动前端二次确认，删除类操作还要求输入名称。
