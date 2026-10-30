# 配置说明

配置分四层，**优先级从低到高**：

```
内置默认值  <  YAML 配置文件  <  环境变量 (LIGHTPANEL_*)  <  程序显式覆盖（测试用）
```

- 配置文件默认按 `config.yaml` → `config.yml` → `/etc/lightpanel/config.yaml` 顺序查找；也可用 `python -m lightpanel -c /path/to.yaml` 指定。
- 环境变量以 `LIGHTPANEL_` 开头，层级用**双下划线**分隔：`LIGHTPANEL_SERVER__PORT=8080` → `server.port`。
- 值会尝试按 JSON / 数字 / 布尔解析，其余作为字符串交给 pydantic 强转。
- 配置模型是 `extra="forbid"`，**写错字段名会直接报错**，避免静默失效。

> 完整示例见仓库根目录 `config.example.yaml`。

---

## server

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `host` | `0.0.0.0` | 监听地址 |
| `port` | `9000` | 监听端口 |
| `root_path` | `""` | 反向代理子路径部署时填写，例如 `/panel` |
| `api_prefix` | `/api` | API 前缀 |
| `cors_origins` | `["*"]` | CORS 允许来源；生产建议限定为前端域名 |
| `docs` | `true` | 是否暴露 `/docs` 与 `/openapi.json` |

## security

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `false` | 是否启用令牌鉴权。**公网部署必须开启** |
| `api_token` | `""` | 令牌明文（也可用环境变量注入） |
| `token_file` | `""` | 从文件读取令牌，适合 Docker secret |
| `header_name` | `X-LightPanel-Token` | 请求头名 |
| `cookie_name` | `lightpanel_token` | Cookie 名 |
| `query_param` | `token` | 查询参数名 |

令牌可通过**请求头 / Cookie / 查询参数**任一方式携带。前端会把令牌写入 `localStorage` 并在每次请求带上。

```bash
LIGHTPANEL_SECURITY__ENABLED=true LIGHTPANEL_SECURITY__API_TOKEN=$(openssl rand -hex 24) python -m lightpanel
```

## metrics

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | `psutil` | `psutil` 真实采集 / `fake` 假数据 |
| `cache_ttl` | `2.0` | 快照缓存秒数，防止前端高频轮询打爆采集 |
| `history_size` | `60` | 保留的采样点数量（趋势图长度），环形缓冲 |
| `disk_mounts` | `[]` | 只展示指定挂载点，空表示全部 |
| `disk_exclude_fs` | `squashfs, tmpfs, devtmpfs, overlay, iso9660` | 排除的文件系统类型 |
| `network_interfaces` | `[]` | 只统计指定网卡，空表示全部 |

## docker

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 关闭后容器/编排接口返回"引擎不可用" |
| `mode` | `auto` | `auto`：先试真实引擎，失败降级；`api`：强制真实；`fake`：强制假引擎 |
| `socket` | `/var/run/docker.sock` | Unix socket 路径 |
| `host` | `""` | 例如 `tcp://127.0.0.1:2375`，优先于 socket |
| `api_version` | `v1.44` | Docker Engine API 版本 |
| `timeout` | `10.0` | 单次 API 调用超时（秒） |
| `include_stopped` | `true` | 列表是否包含已停止容器 |

> Docker 部署需要挂载 `/var/run/docker.sock`，且进程用户要有读写权限（通常是加入 `docker` 组，或以 root 运行——注意这等同于授予宿主机 root 能力）。

## compose

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 是否启用 Compose 编排 |
| `binary` | `docker` | 可执行文件 |
| `subcommand` | `compose` | 使用 `docker-compose` 时置空并把 `binary` 改为 `docker-compose` |
| `search_paths` | `[/opt, /srv, /home, /data]` | 递归发现 compose 文件的根目录 |
| `max_depth` | `3` | 递归深度 |
| `timeout` | `600.0` | 单次 compose 命令超时（秒） |

## catalog

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | `yaml` | `yaml` 持久化到文件 / `memory` 内存（重启丢失） |
| `path` | `data/catalog.yaml` | YAML 仓库路径 |
| `example_file` | `null` | 若 `path` 不存在，首次启动时从该文件复制一份 |

`catalog.yaml` 结构：

```yaml
entries:
  - id: jellyfin
    name: Jellyfin
    url: http://nas:8096
    description: 家庭影音库
    icon: 🎬
    color: "#ff5c8a"
    category: 影音
    tags: [影音, 自建]
    enabled: true
    order: 0
```

`id` 留空时会由名称生成 slug。`tags` 会做归一化（去空白、去重、保留原大小写）。

## commands

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `extra_file` | `data/commands.yaml` | 用户自定义命令定义文件 |
| `example_file` | `null` | 若 `extra_file` 不存在，首次启动时从该文件复制一份（Docker 镜像用它写出厂示例） |
| `include_builtin` | `true` | 是否注册内置命令（容器/栈生命周期） |
| `allow_ad_hoc_argv` | `true` | 是否允许"临时命令"接口直接传 argv |
| `allowed_binaries` | `[docker, docker-compose]` | 可执行文件白名单 |
| `default_timeout` | `120.0` | 默认超时（秒） |
| `max_timeout` | `1800.0` | 允许的最大超时（秒） |
| `executor` | `subprocess` | `subprocess` 真实执行 / `fake` 假执行 |

### 自定义命令定义

```yaml
commands:
  - id: container.logs.follow
    name: 跟踪日志
    target: container          # container | stack | system
    kind: shell                # shell | compose（预留）
    argv: ["docker", "logs", "-f", "--tail", "100", "{id}"]
    description: 实时跟踪容器日志
    confirm: false
    danger: false
    timeout: 60

  - id: stack.update
    name: 拉取并重启
    target: stack
    argv: ["docker", "compose", "pull"]
    working_dir: "{path}"
    confirm: true
    danger: true
```

可用占位符：`{id}` `{name}` `{image}` `{project}` `{path}`（Compose 工作目录）等，取决于目标类型；渲染发生在 `CommandService.preview()` / `run()`，未提供的变量保持原样。

### 安全守卫

`CommandPolicy` 对每条 argv 做三重检查，任一不通过即抛 `CommandRejectedError`（HTTP 400）：

1. **白名单**：首个参数必须在 `allowed_binaries` 内；
2. **解释器拦截**：`sh` `bash` `zsh` `python` `python3` `perl` `ruby` `node` 等不得作为参数出现；
3. **危险参数拦截**：`rm -rf /`、`--privileged`、`-v /:/` 等模式。

超时会被夹紧到 `[1, max_timeout]`。

## logging

| 键 | 默认值 | 说明 |
| --- | --- | --- |
| `level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `format` | `plain` | `plain` 人类可读 / `json` 结构化（便于采集） |

---

## 常用环境变量速查

```bash
LIGHTPANEL_SERVER__PORT=8080
LIGHTPANEL_SERVER__ROOT_PATH=/panel
LIGHTPANEL_SECURITY__ENABLED=true
LIGHTPANEL_SECURITY__API_TOKEN=xxx
LIGHTPANEL_METRICS__PROVIDER=fake
LIGHTPANEL_METRICS__CACHE_TTL=2
LIGHTPANEL_DOCKER__MODE=fake
LIGHTPANEL_DOCKER__SOCKET=/var/run/docker.sock
LIGHTPANEL_COMPOSE__SEARCH_PATHS='["/opt","/data"]'
LIGHTPANEL_CATALOG__PATH=/data/catalog.yaml
LIGHTPANEL_COMMANDS__ALLOWED_BINARIES='["docker"]'
LIGHTPANEL_LOGGING__LEVEL=DEBUG
```
