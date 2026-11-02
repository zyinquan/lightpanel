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
| 系统指标 | 默认是**面板所在环境**（容器 / Docker VM）的 CPU、内存与磁盘。在宿主机跑 `python -m lightpanel.agent --host 0.0.0.0` 后，面板会自动走 `host.docker.internal:9101` 取真实宿主机指标；代理没起来就回落并在概览页顶部说明 |
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

容器里的 psutil 只能看到容器（Windows / macOS 上是 Docker Desktop 的 Linux 虚拟机）。
在宿主机跑自带的小代理即可，指标和 compose 由同一进程提供：

```bash
# 宿主机（与面板同一套代码，无需额外依赖）
python -m lightpanel.agent --host 0.0.0.0 --port 9101 \
  --stacks-root /opt/stacks \
  --stacks-root /home/me/projects          # 可重复，agent 只允许操作这些目录下的项目
# 需要鉴权时： --token s3cret，并在 compose 里设 METRICS_AGENT_TOKEN=s3cret

# Windows 路径直接写盘符即可
python -m lightpanel.agent --host 0.0.0.0 --stacks-root E:/docker-test
```

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

## 方式二：直接跑在宿主机

```bash
cd frontend && npm install && npm run build && cd ..
cd backend && pip install .
cp ../config.example.yaml /etc/lightpanel/config.yaml
cp data/catalog.example.yaml data/catalog.yaml
python -m lightpanel -c /etc/lightpanel/config.yaml
```

后端发现 `frontend/dist/index.html` 会自动托管 SPA，无需额外的 Web 服务器。

建议用 systemd 托管，示例单元：

```ini
[Unit]
Description=LightPanel
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/opt/lightpanel/backend
ExecStart=/opt/lightpanel/backend/.venv/bin/lightpanel -c /etc/lightpanel/config.yaml
Restart=on-failure
Environment=LIGHTPANEL_SECURITY__ENABLED=true

[Install]
WantedBy=multi-user.target
```

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

## 上线前检查清单

- [ ] `security.enabled: true` 且设置了强令牌（`openssl rand -hex 24`）
- [ ] 启用 HTTPS，或仅在可信内网使用 HTTP
- [ ] `server.docs: false`（可选，减少信息暴露）
- [ ] `cors_origins` 限定为前端域名，不要用 `*`
- [ ] `commands.allowed_binaries` 保持最小（默认仅 `docker` / `docker-compose`）
- [ ] `/data` 已挂载到持久化卷，配置好备份
- [ ] 确认 `compose.search_paths` 只包含你希望被管理的目录

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
| 找不到 compose 项目 | 检查 `compose.search_paths` 是否包含项目目录且已挂载进容器、`max_depth` 是否足够 |
| 栈 `up` 返回 400 `not readable from this host` | compose 文件在引擎主机上，但面板看不到该路径：把项目放到 `/data` 下，或改用挂载 socket 的方式部署 |
| 系统指标看着像小机器 | 容器内 psutil 读的是容器/Docker VM，不是宿主机；要看宿主机指标请直接跑在宿主机上 |
| 命令报 `command_rejected` | 可执行文件不在 `allowed_binaries` 内，或 argv 含解释器/危险参数 |
| 命令超时 | 调大 `compose.timeout` 或该命令的 `timeout`（上限 `commands.max_timeout`） |
| `compose up` 卡在 `Container ... Creating` | 宿主机目录挂载未被允许（Docker Desktop 的文件共享 / SELinux 标签），或挂载路径不存在 |
| 刷新子页面 404 | 后端会自动把无扩展名路径回退到 `index.html`；若仍是 404，检查 `/app/frontend/dist/index.html` 是否存在 |
