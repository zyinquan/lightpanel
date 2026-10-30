# LightPanel

轻量级自托管服务器面板 —— 对标 SunPanel，用最小的依赖做三件事：**看服务器状态**、**管软件标签墙**、**控 Docker 与 Docker Compose（含自定义命令）**。

后端 Python + FastAPI，前端 Vue 3 + TypeScript + Vite，整体按**端口与适配器（六边形）**架构组织：业务服务只依赖抽象协议，Docker / 指标 / 存储 / 命令执行器全部可插拔，新增实现不需要改动既有代码（开闭原则）。

---

## 功能

| 能力 | 说明 |
| --- | --- |
| **服务器状态** | CPU（含每核、负载、频率）、内存与 Swap、磁盘分区、网络收发、启动时间；带快照缓存与趋势历史 |
| **软件标签** | 软件条目的增删改查、标签过滤（任意命中 / 全部命中）、搜索、自定义排序、主题色与图标 |
| **容器控制** | 启动 / 停止 / 重启 / 暂停 / 继续 / 删除，日志查看，按名称 / 镜像 / 状态 / 项目筛选 |
| **Compose 编排** | 自动发现 `docker-compose.yml`，支持 up / down / restart / stop / pull / build，附加参数透传 |
| **自定义命令** | YAML 声明式命令模板（`{id}` `{name}` 等占位符渲染），危险命令需确认，临时命令受白名单与参数守卫约束 |
| **安全** | 可选单令牌鉴权；命令执行有二进制白名单、shell 解释器拦截、危险参数拦截与超时控制 |

---

## 快速开始

### 1. 本地开发（前后端分离）

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../config.example.yaml config.yaml
python -m lightpanel --reload            # http://127.0.0.1:9000

# 前端（另开一个终端）
cd frontend
npm install
npm run dev                              # http://127.0.0.1:5273，已代理 /api 到 9000
```

### 2. 生产（单一进程同时提供 API 与前端静态资源）

```bash
cd frontend && npm run build             # 产出 frontend/dist
cd ../backend && pip install .
python -m lightpanel -c /etc/lightpanel/config.yaml
```

后端检测到 `frontend/dist/index.html` 存在时会自动挂载 SPA，无需 Nginx。

### 3. Docker 部署

```bash
cd deploy
docker compose up -d                     # 详见 deploy/README.md
```

### 无 Docker 环境也能跑

把 `docker.mode` 设为 `fake`、`metrics.provider` 设为 `fake`，面板会使用内存中的假引擎与假指标，界面与接口行为完整可演示——这也是 CI 与本地开发默认采用的方式。

```bash
LIGHTPANEL_DOCKER__MODE=fake LIGHTPANEL_METRICS__PROVIDER=fake python -m lightpanel
```

---

## 目录结构

```
lightpanel/
├── backend/
│   ├── src/lightpanel/
│   │   ├── domain/            # 领域模型、端口协议（Protocol）、错误体系、时钟
│   │   │   ├── models.py      #   SystemSnapshot / ContainerInfo / StackInfo / CommandDefinition ...
│   │   │   ├── ports.py       #   MetricsProvider / ContainerEngine / StackEngine / CommandExecutor ...
│   │   │   └── errors.py      #   统一错误类型
│   │   ├── services/          # 业务服务：只依赖 ports，不依赖任何具体适配器
│   │   ├── adapters/          # 具体实现：psutil / Docker API / Compose CLI / YAML / subprocess / fake
│   │   ├── api/               # FastAPI 应用工厂、路由、DTO、错误处理、鉴权
│   │   ├── composition.py     # 组合根：唯一的装配处（依赖注入）
│   │   └── config.py          # 分层配置：默认值 < YAML < 环境变量 < 显式覆盖
│   ├── data/                  # catalog.yaml / commands.yaml 示例数据
│   └── tests/                 # unit + integration，187 个用例
├── frontend/
│   ├── src/api/               # 类型定义与 API 客户端（唯一知道 HTTP 的地方）
│   ├── src/components/        # 展示与交互组件
│   ├── src/views/             # 五个页面：概览 / 软件 / 容器 / 编排 / 命令
│   ├── src/composables/       # usePolling（轮询）· useToast（提示）
│   └── tests/                 # vitest，56 个用例
├── deploy/                    # Dockerfile、compose、反向代理示例
├── docs/                      # 架构 / API / 配置 / 开发 / 测试 文档
└── config.example.yaml
```

---

## 接口一览

| 分组 | 端点 |
| --- | --- |
| 元信息 | `GET /api/health` |
| 鉴权 | `GET /api/auth/status` · `POST /api/auth/login` · `POST /api/auth/logout` |
| 系统 | `GET /api/system` · `GET /api/system/history` · `POST /api/system/invalidate` |
| 软件 | `GET /api/catalog` · `GET /api/catalog/tags` · `GET|POST|PUT|DELETE /api/catalog/entries[/{id}]` · `PUT /api/catalog/entries/{id}/tags` · `POST /api/catalog/reorder` |
| 容器 | `GET /api/containers/status` · `GET /api/containers` · `GET /api/containers/{id}` · `POST /api/containers/{id}/{action}` · `GET /api/containers/{id}/logs` |
| 编排 | `GET /api/stacks/status` · `GET /api/stacks` · `GET /api/stacks/{name}` · `POST /api/stacks/{name}/{action}` |
| 命令 | `GET /api/commands` · `GET /api/commands/{id}` · `POST /api/commands/{id}/preview` · `POST /api/commands/{id}/run` · `POST /api/commands/run-adhoc` |

启动后访问 `/docs` 查看完整 OpenAPI 文档（可用 `server.docs: false` 关闭）。

---

## 文档

- [架构设计](docs/architecture.md) —— 分层、端口与适配器、开闭原则如何落地
- [配置说明](docs/configuration.md) —— 全部配置项、环境变量映射、示例
- [API 文档](docs/api.md) —— 端点、参数、响应与错误码
- [开发指南](docs/development.md) —— 环境搭建、目录约定、如何新增适配器
- [测试指南](docs/testing.md) —— 测试策略、运行方式、覆盖率
- [部署指南](deploy/README.md) —— Docker、反向代理、安全建议

---

## 安全提醒

LightPanel 能够启动和停止容器，**等同于对宿主机的部分控制权**。非本机部署时请务必：

1. `security.enabled: true` 并设置 `security.api_token`；
2. 通过反向代理启用 HTTPS；
3. 不要放宽 `commands.allowed_binaries`，也不要关闭临时命令的参数守卫。

---

## 许可

MIT
