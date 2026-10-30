# API 文档

所有端点以 `/api` 为前缀（可用 `server.api_prefix` 修改）。请求与响应均为 `application/json`。启动后用 `/docs` 可查看可交互的 OpenAPI 文档。

## 统一错误响应

```json
{ "code": "not_found", "message": "container not found: web", "details": {} }
```

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `validation_error` | 400 / 422 | 参数校验失败（422 的 `details.errors` 含字段级信息） |
| `command_rejected` | 400 | 命令被安全策略拒绝（不在白名单、含解释器或危险参数） |
| `unauthenticated` | 401 | 启用了鉴权但令牌缺失或不匹配 |
| `forbidden` | 403 | 拒绝访问 |
| `not_found` | 404 | 目标不存在 |
| `conflict` | 409 | 资源冲突（例如 id 重复） |
| `command_failed` | 502 | 命令已执行但退出码非 0 |
| `engine_unavailable` | 503 | Docker 引擎不可用 |
| `storage_error` | 500 | 目录/命令文件读写失败 |
| `internal_error` | 500 | 未预期异常 |

---

## 元信息与鉴权

### `GET /api/health`

```json
{ "status": "ok", "version": "0.1.0", "env": "dev" }
```

### `GET /api/auth/status`

```json
{ "enabled": true, "authenticated": false }
```

### `POST /api/auth/login`

请求 `{"token": "..."}` → 返回 `AuthStatus`。前端会把令牌写入 `localStorage`，并在后续请求的 `X-LightPanel-Token` 头携带。Cookie 与查询参数 `?token=` 同样被接受。

### `POST /api/auth/logout`

清除会话态（前端侧删除本地令牌）。

---

## 系统状态

### `GET /api/system`

```json
{
  "host": { "hostname": "nas", "os_name": "Ubuntu", "os_version": "24.04", "arch": "x86_64",
            "boot_time": 1700000000.0, "uptime_seconds": 86401.0, "uptime_human": "1d 0h 0m" },
  "cpu":  { "percent": 24.5, "logical_count": 8, "physical_count": 4,
            "per_cpu": [12.0, 30.0], "load_average": [0.5, 0.6, 0.7], "frequency_mhz": 3200.0 },
  "memory": { "total": 16777216000, "used": 8388608000, "available": 8388608000,
              "percent": 50.0, "total_human": "15.6 GB", "used_human": "7.8 GB",
              "swap_total": 0, "swap_used": 0, "swap_percent": 0.0 },
  "disks": [ { "device": "/dev/sda1", "mountpoint": "/", "fstype": "ext4",
               "total": 500107862016, "used": 250053931008, "free": 250053931008,
               "percent": 50.0, "total_human": "465.8 GB", "used_human": "232.9 GB" } ],
  "network": { "bytes_sent": 1024, "bytes_recv": 2048, "packets_sent": 10, "packets_recv": 20,
               "interfaces": { "eth0": { "bytes_sent": 1024, "bytes_recv": 2048 } } },
  "collected_at": "2026-10-30T05:00:00Z"
}
```

结果按 `metrics.cache_ttl` 缓存。

### `GET /api/system/history`

返回趋势采样点数组（最多 `metrics.history_size` 个）：

```json
[{ "timestamp": "2026-10-30T05:00:00Z", "cpu_percent": 24.5, "memory_percent": 50.0 }]
```

### `POST /api/system/invalidate`

丢弃缓存快照，下次请求强制重新采集。返回 `{"ok": true}`。

---

## 软件目录

### `GET /api/catalog`

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `tags` | string | 逗号分隔的标签列表 |
| `match_all` | bool | `true` 表示需同时命中所有标签 |
| `category` | string | 分类过滤 |
| `search` | string | 名称/描述/标签模糊搜索 |
| `enabled_only` | bool | 只返回启用条目 |
| `sort` | enum | `order`（默认）\| `name` \| `recent` |

```json
{
  "entries": [ { "id": "jellyfin", "name": "Jellyfin", "url": "http://nas:8096",
                 "description": "家庭影音库", "icon": "🎬", "color": "#ff5c8a",
                 "category": "影音", "tags": ["影音", "自建"], "enabled": true, "order": 0 } ],
  "tags": [ { "name": "影音", "count": 3 }, { "name": "自建", "count": 5 } ],
  "total": 12
}
```

### `GET /api/catalog/tags`

`[{ "name": "影音", "count": 3 }]`

### `POST /api/catalog/entries`（201）

请求体（`id` 可省略，由名称生成）：

```json
{ "name": "Jellyfin", "url": "http://nas:8096", "description": "...",
  "icon": "🎬", "color": "#ff5c8a", "category": "影音", "tags": ["影音"], "enabled": true, "order": 0 }
```

### `PUT /api/catalog/entries/{id}` · `DELETE /api/catalog/entries/{id}`（204）· `GET /api/catalog/entries/{id}`

### `PUT /api/catalog/entries/{id}/tags`

`{"tags": ["a", "b"]}` —— 覆盖式更新。

### `POST /api/catalog/reorder`

`{"ids": ["c", "a", "b"]}` → 按给定顺序重排并返回全部条目。

---

## 容器

### `GET /api/containers/status`

```json
{ "provider": "DockerApiContainerEngine", "available": true, "total": 6, "running": 4, "stopped": 2 }
```

### `GET /api/containers`

| 参数 | 说明 |
| --- | --- |
| `include_stopped` | 默认 `true` |
| `search` | 名称 / 镜像模糊匹配 |
| `project` | 按 compose 项目过滤 |
| `state` | 按状态过滤（`running` / `exited` / `paused` …） |

```json
[{ "id": "a1b2...", "short_id": "a1b2c3d4e5f6", "name": "nginx", "image": "nginx:1.27",
   "state": "running", "status": "Up 2 hours", "created_at": "2026-01-01T00:00:00Z",
   "ports": ["0.0.0.0:80->80/tcp"], "labels": {},
   "compose_project": "web", "compose_service": "nginx" }]
```

### `POST /api/containers/{id}/{action}`

`action` ∈ `start` `stop` `restart` `pause` `unpause` `remove`。请求体可选 `{"timeout": 10}`（0–600 秒）。

```json
{ "container": { "...": "刷新后的容器" },
  "result": { "ok": true, "exit_code": 0, "argv": ["container", "stop", "nginx"],
              "stdout": "stop ok", "stderr": "", "duration_ms": 120 } }
```

### `GET /api/containers/{id}/logs?tail=200`

```json
{ "container": "nginx", "tail": 200, "content": "..." }
```

---

## Compose 编排

### `GET /api/stacks` / `GET /api/stacks/{name}`

```json
[{ "name": "blog", "config_files": "/opt/blog/docker-compose.yml", "working_dir": "/opt/blog",
   "status": "running", "discovered_paths": ["/opt/blog"],
   "containers": [ { "...": "成员容器" } ], "running": 2, "total": 2 }]
```

`status` 取值：`running`（全部运行）`partial`（部分运行）`stopped` `unknown`。

### `POST /api/stacks/{name}/{action}`

`action` ∈ `up` `down` `restart` `stop` `pull` `build`。请求体：

```json
{ "extra_args": ["-d"] }
```

响应为 `{ "stack": {...}, "result": {...} }`。命令失败时返回 502 / `command_failed`，`result.stderr` 含原始输出。

---

## 命令

### `GET /api/commands?target=container`

```json
[{ "id": "container.logs.follow", "name": "跟踪日志", "target": "container", "kind": "shell",
   "action": "logs", "argv": ["docker", "logs", "-f", "{id}"], "description": "...",
   "confirm": false, "danger": false, "timeout": 60, "working_dir": null, "builtin": false }]
```

`target` 可省略（返回全部）或取 `container` / `stack` / `system`。

### `POST /api/commands/{id}/preview`

请求 `{"target_id": "nginx", "extra_args": ["--tail", "50"]}` → `{"id": "...", "argv": ["docker","logs","-f","nginx","--tail","50"]}`。预览只做模板渲染与安全校验，不执行。

### `POST /api/commands/{id}/run`

请求 `{"target_id": "...", "extra_args": [], "timeout": 60}` → 返回 `CommandResult`：

```json
{ "ok": true, "exit_code": 0, "argv": ["docker", "logs", "-f", "nginx"],
  "stdout": "...", "stderr": "", "duration_ms": 312 }
```

退出码非 0 时返回 **502 / `command_failed`**（结果体仍在 `details` 之外的响应中给出）。

### `POST /api/commands/run-adhoc`

```json
{ "argv": ["docker", "ps"], "cwd": null, "timeout": 30, "context": {} }
```

受 `commands.allowed_binaries` 与 `CommandPolicy` 约束；`commands.allow_ad_hoc_argv: false` 时该端点始终拒绝。

---

## 前端用法示例

```ts
import { api } from '@/api/client'

const page = await api.catalog({ tags: ['影音'], matchAll: false, sort: 'order' })
await api.containerAction('nginx', 'restart')
const preview = await api.previewCommand('stack.update', 'blog')
const result = await api.runCommand('stack.update', { targetId: 'blog' })
```
