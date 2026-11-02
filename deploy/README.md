# 部署指南

## 方式一：Docker Compose（推荐）

```bash
git clone <repo> lightpanel && cd lightpanel
cp backend/data/catalog.example.yaml deploy/data/catalog.yaml     # 首次初始化数据
cp backend/data/commands.yaml        deploy/data/commands.yaml
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml logs -f
```

面板访问 `http://<host>:9000`。`/data` 卷持久化软件目录与自定义命令。
镜像内已打包 docker CLI 与 compose 插件，栈管理不依赖宿主机是否装了 docker。

## 方式一 · B：TCP API 模式（Docker Desktop / 远程引擎）

宿主机挂不上 socket 时（Docker Desktop 的 Hyper-V 后端、面板要管另一台机器），
用这份配置让面板通过 Docker Engine API 控制引擎：

```bash
# 前置：引擎开放 TCP API。Docker Desktop → Settings → General →
#       "Expose daemon on tcp://localhost:2375 without TLS"
docker compose -f deploy/docker-compose.api.yml up -d
# 管另一台机器：DOCKER_API_HOST=192.168.1.10 DOCKER_API_PORT=2375 ...
```

它不挂 `/var/run/docker.sock`、不做宿主机目录挂载，`/data` 用命名卷；compose 子进程
通过 `DOCKER_HOST` 指向同一个引擎。

容器化运行时的行为差异（两种方式都一样）：

| 能力 | 说明 |
| --- | --- |
| 容器启停 / 日志 / 详情 | 正常，走 Engine API |
| 栈 `up` / `down` / `restart` / `pull` | 交给宿主机上的 `lightpanel-agent` 执行（`compose.runner=agent`，compose 文件默认就是这么配的）。为什么必须这样见下节 |
| 栈自动发现 | `agent` 模式下由宿主机代理扫描 `--stacks-root` 指定的目录，宿主机上任何位置的栈都能扫到；已在运行的栈另外还能靠 compose 标签发现 |
| 系统指标 | 跑在容器里时 CPU / 内存 / 负载取所在内核的数字（Linux 宿主机上即整机，Docker Desktop 上是其 Linux 虚拟机），网络只统计本容器、磁盘只含挂进容器的目录。在宿主机跑 `python -m lightpanel.agent --host 0.0.0.0` 后，面板会自动走 `host.docker.internal:9101` 取完整宿主机口径；代理没起来就回落并在概览页顶部说明 |
| 磁盘列表 | 只列真实挂载目录，`/etc/hostname` 之类的单文件挂载会被过滤掉 |

### 为什么容器里的 compose 要交给宿主机执行

`docker compose` 解析相对挂载（`./src:/app`）用的是**它自己所在文件系统**。面板在容器里时，解析出来的绝对路径是容器内的（比如 `/data/probe/src`），交给宿主机 docker 守护进程后该路径并不存在——守护进程会建一个空目录顶上。结果是：

```
栈状态：running
容器：  起来了
/app：  空的（源码没挂上）
报错：  没有
```

纯镜像栈（只有命名卷）不会碰到这个问题，带源码挂载或 `build: ./xxx` 的开发栈则必中。所以 `deploy/docker-compose.api.yml` 默认：

```yaml
LIGHTPANEL_COMPOSE__RUNNER: "agent"
LIGHTPANEL_COMPOSE__AGENT_URL: "http://host.docker.internal:9101"
```

### 让容器里的面板显示宿主机指标、并真正管理 compose 栈

容器里的 psutil 在网络和磁盘上只覆盖本容器（Windows / macOS 上整体是 Docker Desktop
的 Linux 虚拟机）。在宿主机跑自带的小代理即可，指标和 compose 由同一进程提供：

```bash
# 宿主机（与面板同一套代码，无需额外依赖）
python -m lightpanel.agent --host 0.0.0.0 --port 9101 \
  --stacks-root /opt/stacks \
  --stacks-root /home/me/projects \        # 可重复，agent 只允许操作这些目录下的项目
  --max-depth 4                            # 递归深度，默认 3
# 需要鉴权时： --token s3cret，并在 compose 里设 METRICS_AGENT_TOKEN=s3cret

# Windows 路径直接写盘符即可
python -m lightpanel.agent --host 0.0.0.0 --stacks-root E:/docker-test --max-depth 4

# 或者用 Makefile
make agent STACKS_ROOT=E:/docker-test STACKS_DEPTH=4
```

> `--stacks-root` / `--max-depth` 是 **agent 模式下唯一生效的扫描配置**。
> 面板侧的 `compose.search_paths` / `compose.max_depth` 在这条路径下不参与任何逻辑，
> 设了会打 WARNING 提示（避免“改了配置却毫无反应”）。

`docker-compose.api.yml` 默认已把 `LIGHTPANEL_METRICS__REMOTE_URL` 指向
`http://host.docker.internal:9101/metrics`，`compose.runner` 指向 `agent`；不想要宿主机指标就
`METRICS_AGENT_URL= docker compose ... up -d` 置空。概览页顶部会显示
「宿主机指标 · 来自 <主机名> · 采集自宿主机代理」。

想退回容器内执行 compose（只有纯镜像栈才安全）：

```bash
COMPOSE_RUNNER=local docker compose -f deploy/docker-compose.api.yml up -d
```

长期运行：Linux 用 `deploy/lightpanel-agent.service`（systemd 单元，改好路径后
`systemctl enable --now lightpanel-agent`）；Windows 可用计划任务或把
`pythonw -m lightpanel.agent --host 0.0.0.0 --stacks-root E:/docker-test` 放进启动项。

### 构建参数（内网 / 国内网络）

镜像构建会从 npm 与 PyPI 拉依赖，GitHub、npmjs、pypi 直连不通时用参数换成镜像源：

```bash
# 直接 docker build
docker build -f deploy/Dockerfile -t lightpanel:latest \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple .

# 走 compose（build.args 已预留同名变量）
NPM_REGISTRY=https://registry.npmmirror.com \
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
docker compose -f deploy/docker-compose.yml up -d --build
```

不传则使用官方源，行为与之前一致。

### 关于 Docker Desktop（Windows / macOS）

`deploy/docker-compose.yml` 里的 `/var/run/docker.sock` 与 `/opt` 是**宿主机目录挂载**，在 Linux 宿主机上开箱可用；在 Docker Desktop 上实测：

- Hyper-V 后端未开启文件共享时，挂载宿主机目录会让容器卡在 `Creating`（不是面板的问题，`docker create -v /opt:/opt` 同样卡住）；
- 同样在这个后端下，`/var/run/docker.sock` 挂进容器后**容器内看不到该文件**，面板会降级成 `NullContainerEngine`（容器页显示"引擎不可用"）；
- 因此 Docker Desktop 上请改用 **方式一 · B（TCP API 模式）**，它不开任何宿主机挂载，实测可直接控制宿主机容器与栈；
- 只想验证面板本身时，也可以不带任何挂载先跑：
  `docker run -d -p 9000:9000 -v lp_data:/data lightpanel:latest`

## 方式二：直接跑在宿主机（单机推荐）

一个进程，不发容器镜像，**也不需要 `lightpanel-agent`**：面板进程与 docker daemon 看的是同一份文件系统，
compose 里的 `./src:/app` 会被解析成真实路径；psutil 读到的是整机指标，网络、磁盘都是全量。

```bash
sudo ./deploy/install-host.sh
```

脚本做的事：建 `backend/.venv` → 装依赖（默认阿里云源）→ `frontend/dist` 缺失时用一次性
node 容器构建 → 生成 `config.local.yaml`（随机 token、600 权限）→ 安装并启动 `lightpanel.service`。
结束时打印令牌与监听端口，浏览器打开 `http://<本机IP>:9001` 用令牌登录。

常用覆盖项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `PORT` | `9001` | 监听端口 |
| `RUN_USER` | sudo 之前的用户 | 服务运行身份 |
| `APP_DIR` | 脚本所在仓库根目录 | 项目路径 |
| `PYPI_INDEX` | 阿里云 | **清华源对 `setuptools` 返回 403**，照抄会装不上 |

改完配置：`sudo systemctl restart lightpanel`；日志：`journalctl -u lightpanel -f`。
单元模板在 `deploy/lightpanel.service.in`，`@APP_DIR@` / `@RUN_USER@` 由脚本替换。

不用脚本、手动装（等价操作）：

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e .
cp ../config.example.yaml ../config.local.yaml    # 改 port / security.api_token
.venv/bin/lightpanel -c ../config.local.yaml
```

后端发现 `frontend/dist/index.html` 会自动托管 SPA，无需额外的 Web 服务器。

> 这套方式下 `compose.runner` 保持默认的 `local` 即可。`agent` 模式是为「面板跑在容器里」
> 准备的补偿手段，宿主机直跑用它反而是多养一个进程。

## 反向代理（Nginx + HTTPS）

```nginx
server {
    listen 443 ssl http2;
    server_name panel.example.com;

    ssl_certificate     /etc/letsencrypt/live/panel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

子路径部署（例如 `https://example.com/panel`）时设置 `LIGHTPANEL_SERVER__ROOT_PATH=/panel`，并在 Nginx 里 `location /panel/ { proxy_pass http://127.0.0.1:9000/; }`。

---

## 关于 Docker socket 权限（重要）

面板通过 `/var/run/docker.sock` 控制容器，**能访问该 socket 等同于拥有宿主机 root 能力**。三种常见做法：

| 做法 | 说明 |
| --- | --- |
| 容器内用户 gid = 宿主机 docker 组 gid | 最常用。查 `getent group docker`，在 compose 里加 `group_add: ["<gid>"]` |
| 容器内以 root 运行 | 简单但权限最大，仅建议在完全可信的内网 |
| Docker Socket Proxy（如 tecnativa/docker-socket-proxy） | 只暴露容器只读/指定写操作，安全性最好 |

示例（对齐 docker 组）：

```yaml
services:
  lightpanel:
    # ...
    group_add:
      - "998"     # 替换为宿主机 docker 组 gid
```

`deploy/docker-compose.yml` 里已经写好了 `group_add: ["${DOCKER_GID:-999}"]`，
把真实 GID 传进去即可，不要靠猜：

```bash
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) \
  docker compose -f deploy/docker-compose.yml up -d
```

> 漏配置这一项的症状很容易被误判：**概览页指标照常显示**（读 `/proc` 不需要
> socket 权限），但容器列表空白、启停和日志全失败。若 socket 是 `root:root`
> （部分单板机 / rootless 配置），`group_add` 无效，改用 `user: "0:0"`。

## 上线前检查清单

- [ ] `security.enabled: true` 且设置了强令牌（`openssl rand -hex 24`）
- [ ] 启用 HTTPS，或仅在可信内网使用 HTTP
- [ ] `server.docs: false`（可选，减少信息暴露）
- [ ] `cors_origins` 限定为前端域名，不要用 `*`
- [ ] `commands.allowed_binaries` 保持最小（默认仅 `docker` / `docker-compose`）
- [ ] `/data` 已挂载到持久化卷，配置好备份
- [ ] 确认 `lightpanel-agent` 的 `--stacks-root` 只包含你希望被管理的目录（`runner=local` 时改看 `compose.search_paths`）

## 备份与恢复

需要备份的只有两个文件：

```bash
cp deploy/data/catalog.yaml  backup/catalog-$(date +%F).yaml
cp deploy/data/commands.yaml backup/commands-$(date +%F).yaml
```

恢复时拷回 `/data` 并重启容器即可；软件目录是纯 YAML，可直接手工编辑。

## 升级

```bash
docker compose -f deploy/docker-compose.yml pull     # 若使用远端镜像
docker compose -f deploy/docker-compose.yml up -d --build
```

## 故障排查

| 现象 | 排查方向 |
| --- | --- |
| 页面提示"引擎不可用" | 检查 socket 是否挂载、容器用户是否有权限、`docker.mode` 是否为 `fake` |
| 找不到 compose 项目 | `runner=agent`（默认）：检查 `lightpanel-agent` 是否在跑、启动参数 `--stacks-root` 是否包含项目目录、`--max-depth` 是否够深；`runner=local`：检查 `compose.search_paths` 是否已挂载进容器 |
| 栈 `up` 返回 400 `not readable from this host` | 这是 `runner=local` 才会出现的错误：compose 文件在引擎主机上但面板看不到该路径。改用 `COMPOSE_RUNNER=agent`（默认），或把项目放到容器内可见的 `/data` 下 |
| 容器页空白 / 日志接口报 `读不到 Docker socket（权限不足）` | 容器内用户不在宿主机 docker 组：`DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) docker compose -f deploy/docker-compose.yml up -d`。注意此时**概览页仍显示正常数字**，因为读 `/proc` 不需要 socket 权限 |
| 系统指标与宿主机对不上 | Linux 容器里 CPU / 内存 / 负载本来就是整机数值（内核不按容器隔离 `/proc`），但网络只算本容器、磁盘只含挂进容器的目录；Docker Desktop 上则是其 Linux 虚拟机的数字。要统一口径请启动 `lightpanel-agent` 并把 `metrics.remote_url` 指过去 |
| 命令报 `command_rejected` | 可执行文件不在 `allowed_binaries` 内，或 argv 含解释器/危险参数 |
| 命令超时 | 调大 `compose.timeout` 或该命令的 `timeout`（上限 `commands.max_timeout`） |
| `compose up` 卡在 `Container ... Creating` | 宿主机目录挂载未被允许（Docker Desktop 的文件共享 / SELinux 标签），或挂载路径不存在 |
| 刷新子页面 404 | 后端会自动把无扩展名路径回退到 `index.html`；若仍是 404，检查 `/app/frontend/dist/index.html` 是否存在 |
| 所有接口 401 `Invalid or missing API token` | 开了 `security.enabled` 但没登录。页面会停在令牌输入框；令牌在 `config.local.yaml` 的 `security.api_token`（或 `token_file`）里。直接调接口需带 `X-LightPanel-Token` 头 |
| 宿主机直跑时报 `Address already in use` | 9000 上可能还跑着容器版：`docker compose -f deploy/docker-compose.yml down`，或把 `server.port` 换一个 |
| systemd 起来就退出 | `journalctl -u lightpanel -n 50`。常见原因：`WorkingDirectory` 不对导致 `data/catalog.yaml` 相对路径失效、venv 里没装包、`config.local.yaml` 权限过严（服务用户读不到） |
