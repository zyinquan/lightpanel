# 部署指南

LightPanel 有两种跑法。**选一种，照着对应那一章从头做完**，两章之间没有依赖。

| | [方案 A · 宿主机直跑](#方案-a宿主机直跑) | [方案 B · 容器化](#方案-b容器化) |
| --- | --- | --- |
| 进程数 | 1 个（systemd 托管） | 1 个容器，栈要写操作时 +1 个 agent |
| 适用 | 面板管的栈就在同一台 Linux 上 | 有 Docker 的任何机器、要和宿主隔离、要管远程引擎 |
| 首次部署 | 一条命令，约 1~2 分钟 | 构建镜像 2~3 分钟 |
| 栈 `up` / `pull` | ✅ 直接可用 | ⚠️ 需要 agent（见 [B.4](#b4-可选件lightpanel-agent)） |
| 指标口径 | ✅ 全量（全部网卡、全部磁盘） | ⚠️ 网络/磁盘只含容器可见部分 |
| 升级 | `git pull` + `systemctl restart` | 重建镜像 |
| 典型端口 | 9001 | 9000 |

**一句话判断**：面板和它要管理的栈在同一台 Linux 上 → 方案 A；否则（Docker Desktop、面板管另一台机器、就是想要容器隔离）→ 方案 B。

两套可以并存（9000 和 9001 不冲突），便于对比后决定保留哪一个。

---

# 方案 A：宿主机直跑

一个 Python 进程，systemd 托管。不需要容器镜像，**也不需要 `lightpanel-agent`**——面板进程和 docker daemon 看的是同一份文件系统，compose 里的 `./src:/app` 会被解析成真实路径，psutil 读到的是整机指标。

## A.1 前置条件

| 要求 | 检查命令 | 说明 |
| --- | --- | --- |
| Linux + systemd | `systemctl --version` | macOS / Windows 不适用，走方案 B |
| Python ≥ 3.11 | `python3 -V` | 发行版自带通常够 |
| docker | `docker version` | 面板要能读 `/var/run/docker.sock` 或 TCP API |
| node **或** docker | `node -v` / `docker -v` | 构建前端产物二选一；有 docker 就不用装 node |
| 写 `/etc/systemd/system` | `sudo -v` | 只有装服务这一步需要 root |

## A.2 一键安装

```bash
git clone <repo> lightpanel && cd lightpanel
sudo ./deploy/install-host.sh
```

脚本按顺序跑五步，全部幂等：`deps` → `frontend` → `config` → `data` → `service`，最后打印状态与令牌。

结束时输出类似：

```
==> 服务
    状态：active（开机自启：enabled）
    PID：2785593    累计重启：0
==> 端口
    0.0.0.0:9001 已监听
==> 接口
    /api/health → 200
    /api/system（带令牌）→ 200
==> 登录
    令牌：lp_xxxxxxxx
    地址：http://<本机IP>:9001
```

浏览器打开该地址，粘贴令牌即可。

> **默认扫描目录是 `/opt`**。你的栈在别处时必须显式指定，否则栈列表是空的：
> `sudo ./deploy/install-host.sh config --force --stacks-root /ssd/app,/home/zyq/opt`

## A.3 分步安装（每一步都能单独重跑）

安装被拆成独立子命令。**装到一半失败、只想重建前端、只想改端口，都只跑那一步**，不用从头来。

| 子命令 | 做什么 | 需要 root | 幂等行为 |
| --- | --- | --- | --- |
| `deps` | 建 `backend/.venv`、装 Python 依赖 | 建议 | venv 已存在则复用，只更新依赖 |
| `frontend` | 生成 `frontend/dist` | 建议 | 产物已存在则跳过；`--force` 重建 |
| `config` | 生成 `config.local.yaml` | 否 | 已存在则**保留不动**，只打印当前令牌；`--force` 才覆盖（先备份、**换新令牌**） |
| `data` | 初始化 `data/catalog.yaml`、`data/commands.yaml` | 否 | 已存在则保留，不覆盖你加过的软件 |
| `service` | 渲染并安装 `lightpanel.service`，启动 | **是** | 重跑即更新单元文件并重启 |
| `status` | 服务状态 + 端口 + 接口探活 + 令牌 | 否 | 只读 |
| `logs` | `journalctl -u lightpanel -f` | 视权限 | 只读 |
| `restart` / `stop` | 重启 / 停止 | **是** | — |
| `all` | 上面五步全跑（默认） | 建议 | — |

典型用法：

```bash
# 第一次装
sudo ./deploy/install-host.sh

# 栈列表是空的：改扫描目录（会换令牌，记得重新登录）
sudo ./deploy/install-host.sh config --force --stacks-root /ssd/app,/home/zyq/opt
sudo ./deploy/install-host.sh restart

# 只改了前端代码
sudo ./deploy/install-host.sh frontend --force
sudo ./deploy/install-host.sh restart

# 只拉了新的后端代码
git pull && sudo ./deploy/install-host.sh deps && sudo ./deploy/install-host.sh restart

# 忘了令牌 / 看服务正不正常
./deploy/install-host.sh status
```

### 可用选项

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `--app-dir DIR` | 脚本上一级目录 | 项目根目录 |
| `--user USER` | `sudo` 之前的用户 | 服务运行身份，也是 venv / dist 的属主 |
| `--port N` | 已有配置里的值，否则 9001 | 监听端口 |
| `--stacks-root A,B` | `/opt` | compose 扫描目录，逗号分隔，可多个 |
| `--max-depth N` | `3` | 扫描递归深度 |
| `--pypi-index URL` | 阿里云 | **清华源对 `setuptools` 返回 403**，照抄会装不上 |
| `--force` | 关 | 覆盖已有配置 / 重新构建前端 |
| `--no-build` | 关 | 前端产物缺失时直接报错，不自动构建 |

## A.4 配置

生成的位置是项目根目录的 `config.local.yaml`（权限 600，被 `.gitignore` 的 `*.local.yaml` 覆盖，不会误提交）。关键字段：

```yaml
server:
  host: 0.0.0.0
  port: 9001
  docs: false            # 开鉴权后不暴露 /docs

security:
  enabled: true
  api_token: "lp_..."    # 登录令牌，config 子命令生成

compose:
  runner: local          # 与 daemon 同文件系统，不需要 agent
  search_paths:          # 扫描范围，按实际栈目录改
    - /ssd/app
    - /home/zyq/opt
  max_depth: 3

catalog:
  path: data/catalog.yaml          # 相对 WorkingDirectory（项目根）
commands:
  extra_file: data/commands.yaml
```

改完执行 `sudo systemctl restart lightpanel`（或 `sudo ./deploy/install-host.sh restart`）。

其余字段见 [`config.example.yaml`](../config.example.yaml) 与 [`docs/configuration.md`](../docs/configuration.md)。环境变量同样可用：`LIGHTPANEL_SERVER__PORT` 之类会覆盖配置文件（`__` 表示层级）。

## A.5 日常运维

```bash
./deploy/install-host.sh status       # 状态 + 令牌
./deploy/install-host.sh logs         # 跟踪日志
sudo ./deploy/install-host.sh restart # 重启
```

| 操作 | 命令 |
| --- | --- |
| 开机自启 | 安装时已 `systemctl enable`；`systemctl is-enabled lightpanel` 确认 |
| 崩溃自愈 | `Restart=always`，`RestartSec=3`；`systemctl show lightpanel -p NRestarts` 看次数 |
| 升级 | `git pull` → `deps` → `restart`（前端有改动再加 `frontend --force`） |
| 卸载服务 | `sudo systemctl disable --now lightpanel && sudo rm /etc/systemd/system/lightpanel.service` |
| 完全清除 | 再删 `backend/.venv`、`frontend/dist`、`config.local.yaml`、`data/` |

单元文件由 `deploy/lightpanel.service.in` 渲染（`@APP_DIR@` / `@RUN_USER@` 替换）。想改启动参数就直接改 `/etc/systemd/system/lightpanel.service`，再 `daemon-reload`——注意重跑 `service` 子命令会覆盖它。

## A.6 限制

| 限制 | 说明 / 解法 |
| --- | --- |
| 只有 Linux + systemd | macOS / Windows 用方案 B |
| 进程以服务用户身份跑 | 读得到该用户的所有文件。但管 compose 本来就要 docker socket（≈ root），这层隔离是心理安慰 |
| 宿主机不一定有 node | 脚本会用一次性 `node:22-alpine` 容器构建前端，不必装 node |
| 改前端要重建 | 同上，`frontend --force`，约 30 秒（首次装 npm 依赖更久） |
| 不做进程内隔离 | 一个 Python 进程挂了全部功能不可用；systemd 会在 3 秒后拉起 |

---

# 方案 B：容器化

面板跑在容器里，通过 Docker Engine API 或 socket 管理引擎。**栈的写操作需要额外一个 `lightpanel-agent`**（见 [B.4](#b4-可选件lightpanel-agent)），原因在那一节解释。

## B.1 先选模式

| | B-1 · socket 挂载 | B-2 · TCP API |
| --- | --- | --- |
| 文件 | `deploy/docker-compose.yml` | `deploy/docker-compose.api.yml` |
| 适用 | **Linux 宿主机** | Docker Desktop（Windows / macOS）、面板管**另一台**机器 |
| 挂载 | `/var/run/docker.sock` + `./data` + `/opt:ro` | 不挂任何宿主机路径，`/data` 用命名卷 |
| 前置 | 容器用户 GID = 宿主机 docker 组 | 引擎开放 2375（Docker Desktop：Settings → General → *Expose daemon on tcp://localhost:2375 without TLS*） |
| 端口 | 9000（固定） | `${LIGHTPANEL_PORT:-9000}` |

在 Docker Desktop 上用 B-1 会卡在 `Creating`（文件共享未开启时挂载卡死）或容器页显示"引擎不可用"——**这不是面板的问题**，改用 B-2。

## B.2 B-1：Linux 上的 socket 模式

```bash
git clone <repo> lightpanel && cd lightpanel
mkdir -p deploy/data
cp backend/data/catalog.example.yaml deploy/data/catalog.yaml
cp backend/data/commands.yaml        deploy/data/commands.yaml

# 关键：容器内用户必须与宿主机 docker 组同 GID，否则容器页空白
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) \
  docker compose -f deploy/docker-compose.yml up -d --build
```

访问 `http://<host>:9000`。

**这个模式下能做什么：**

| 能力 | 状态 |
| --- | --- |
| 概览指标 | CPU / 内存 / 负载是整机（Linux 内核不按容器隔离 `/proc`）；网络和磁盘只有容器自己的 |
| 容器启停 / 日志 / 详情 | ✅ 走 socket |
| 软件标签墙 | ✅ 数据在 `deploy/data/` |
| 栈列表 | ✅ 能看到（靠 compose 标签 + `search_paths`） |
| 栈 `up` / `pull` | ⚠️ **只有 `/opt` 下的栈可用**——`/opt` 是唯一挂进容器的目录，其余栈的 compose 文件容器里看不见，会返回 400 `not readable from this host` |
| 栈 `down` / `restart` | ✅ 按项目名查标签就行，不需要文件 |

要管 `/opt` 之外的栈，两条路：把目录加到 compose 的 `volumes:`（每加一个目录改一次），或者装 agent（[B.4](#b4-可选件lightpanel-agent)）。

关于 GID：`group_add: ["${DOCKER_GID:-999}"]` 已写在 compose 里，默认 999 只对部分发行版成立，**必须实测传入**。如果 `stat` 打印 `0`（socket 属 `root:root`，部分单板机 / rootless），`group_add` 无效，改用 `user: "0:0"`。

漏配的症状很容易误判：**概览页照常显示数字**（读 `/proc` 不需要 socket 权限），但容器页空白、启停和日志全失败，错误信息是「读不到 Docker socket（权限不足）」。

## B.3 B-2：TCP API 模式

```bash
docker compose -f deploy/docker-compose.api.yml up -d --build
```

默认连本机 `host.docker.internal:2375`。管另一台机器：

```bash
DOCKER_API_HOST=192.168.1.10 DOCKER_API_PORT=2375 \
  docker compose -f deploy/docker-compose.api.yml up -d
```

数据在命名卷 `lightpanel_data`，首次启动会自动写出厂软目录，不用手工 cp。

```bash
# 看数据卷实际落在宿主机哪里
docker volume inspect lightpanel_data --format '{{.Mountpoint}}'
```

> 2375 是明文、无鉴权的管理接口，等价于宿主机 root。只在内网或本机使用；跨公网必须走 TLS（2376）或 SSH 隧道。

这个模式默认 `COMPOSE_RUNNER=agent`：容器里看不到宿主机的栈目录，也没有引擎所在机器的文件系统，所以 compose 必须交给 agent 执行。**不装 agent 时栈列表还能显示，但 `up` / `pull` 会报"连不上宿主机代理"。**

## B.4 可选件：lightpanel-agent

### 它解决什么

两件事，都是容器这个形态造成的：

1. **compose 的路径语义**。`docker compose` 解析 `./src:/app` 用的是它自己所在文件系统的语义。容器里跑，`/ssd/app/spark/src` 会变成 `/app/...` 之类；宿主机 daemon 找不到这个路径就**建一个空目录顶上，容器照常起来，代码没挂上，还不报错**。agent 与 daemon 共用文件系统，命令行执行处和挂载解析处终于一致。
2. **完整宿主机指标**。容器里的网络只统计自己的 netns、磁盘只含挂进来的目录；agent 报的是整机。

### 什么时候需要

| 场景 | 需要 agent |
| --- | --- |
| 只用容器启停 / 日志 / 软件墙 | ❌ |
| 只有纯镜像栈（无 bind mount、无 build context） | ❌ |
| 栈带 `./xxx:/xxx` 或 `build: ./xxx` | ✅ 必须 |
| 栈文件不在容器挂载范围内 | ✅ 必须 |
| 想看到全机网络与磁盘 | ✅ 必须 |

### 安装（Linux，systemd）

```bash
# 1) 宿主机上装一份同样的代码（不需要前端产物）
git clone <repo> /opt/lightpanel

# 2) 建 venv 装依赖（agent 只需要后端包）
python3 -m venv /opt/lightpanel/backend/.venv
/opt/lightpanel/backend/.venv/bin/pip install -e /opt/lightpanel/backend

# 3) 改 deploy/lightpanel-agent.service 里的 User / WorkingDirectory / 栈目录，然后
sudo cp /opt/lightpanel/deploy/lightpanel-agent.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lightpanel-agent
```

单元里需要按实际情况改的是这几行（模板里的值是占位）：

```ini
[Service]
User=lightpanel                                          # 改成实际用户
WorkingDirectory=/opt/lightpanel/backend                 # 改成实际路径
# 与面板侧 METRICS_AGENT_TOKEN 保持一致；留空 = 不鉴权
Environment=LIGHTPANEL_AGENT_TOKEN=<口令>
ExecStart=/opt/lightpanel/backend/.venv/bin/python -m lightpanel.agent \
  --host 0.0.0.0 --port 9101 \
  --stacks-root /opt/stacks --stacks-root /home/me/projects \
  --max-depth 4
```

`--stacks-root` 可重复，**agent 只允许操作这些目录下的项目**（内部做 realpath + `commonpath` 校验，拒绝 `-f` / `--project-directory` 之类能跳出范围的参数）。一个都不传就只提供指标、不提供 compose。

不加 systemd 时可直接跑：

```bash
python -m lightpanel.agent --host 0.0.0.0 --port 9101 --stacks-root /opt/stacks --max-depth 4
make agent STACKS_ROOT=/opt/stacks STACKS_DEPTH=4        # 等价
```

> ⚠️ **`--stacks-root` / `--max-depth` 是 agent 模式下唯一生效的扫描配置。**
> 面板侧的 `compose.search_paths` / `compose.max_depth` 在这条路径下不参与任何逻辑，
> 设了会打 WARNING（避免"改了配置却毫无反应"）。

### 面板侧对接

```bash
COMPOSE_AGENT_URL=http://host.docker.internal:9101 \
METRICS_AGENT_URL=http://host.docker.internal:9101/metrics \
METRICS_AGENT_TOKEN=<口令> \
  docker compose -f deploy/docker-compose.api.yml up -d
```

`docker-compose.api.yml` 已默认指向 `host.docker.internal:9101`，通常只需设 token。

**性能与安全提醒**：agent 监听 `0.0.0.0:9101` 时，同网段任何人都能对你机器上的栈执行 up/down/pull。**务必加 `--token`**，面板侧同步配置 `METRICS_AGENT_TOKEN`。

## B.5 国内网络构建

镜像构建要从 npm 与 PyPI 拉依赖：

```bash
NPM_REGISTRY=https://registry.npmmirror.com \
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  docker compose -f deploy/docker-compose.yml up -d --build
```

`docker-compose*.yml` 的 `build.args` 已预留这两个变量。直接 `docker build` 则加 `--build-arg`。

> 清华源对 `setuptools` 会返回 403（pip 建隔离环境时要拉它），所以示例用的是阿里云。

## B.6 日常运维

```bash
# 日志
docker compose -f deploy/docker-compose.yml logs -f

# 升级
git pull
docker compose -f deploy/docker-compose.yml up -d --build

# 停 / 起
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml up -d
```

| 操作 | 命令 |
| --- | --- |
| 改配置 | 改 `deploy/docker-compose*.yml` 的 `environment:`，或写 `.env`（`DOCKER_GID` / `LIGHTPANEL_PORT` / `METRICS_AGENT_TOKEN` 等），然后 `up -d` |
| 换端口 | `LIGHTPANEL_PORT=9001 docker compose -f deploy/docker-compose.api.yml up -d`（B-1 的端口写死 9000，要改改文件） |
| 回滚 | `docker tag lightpanel:latest lightpanel:backup-$(date +%m%d)` 定期打标，出问题 `docker tag` 回去 |

---

# 通用部分

## 反向代理（Nginx + HTTPS）

```nginx
server {
    listen 443 ssl http2;
    server_name panel.example.com;

    ssl_certificate     /etc/letsencrypt/live/panel.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9001;       # 方案 B 改成 9000
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

子路径部署（`https://example.com/panel`）：设 `LIGHTPANEL_SERVER__ROOT_PATH=/panel`，Nginx 侧 `location /panel/ { proxy_pass http://127.0.0.1:9001/; }`。

## 备份与恢复

**只有两个文件需要备份**，但位置按方案不同：

| | catalog（软件墙） | commands（自定义命令） |
| --- | --- | --- |
| 方案 A | `<项目>/data/catalog.yaml` | `<项目>/data/commands.yaml` |
| 方案 B-1 | `<项目>/deploy/data/catalog.yaml` | `<项目>/deploy/data/commands.yaml` |
| 方案 B-2 | 命名卷 `lightpanel_data` 里 | 同左 |

```bash
# 方案 A / B-1：直接拷
cp data/catalog.yaml backup/catalog-$(date +%F).yaml
cp data/commands.yaml backup/commands-$(date +%F).yaml

# 方案 B-2：从卷里倒出来
docker run --rm -v lightpanel_data:/data -v "$PWD/backup:/backup" alpine \
  cp /data/catalog.yaml /data/commands.yaml /backup/
```

两者都是纯 YAML，可以直接手工编辑。恢复时拷回原位置并重启服务/容器。

> 这两个文件**不在 git 仓库里**（`data/` 与 `*.local.yaml` 都被忽略）。换机器时要单独带走，否则软件墙是空的。

## 上线前检查清单

- [ ] `security.enabled: true` 且设置了强令牌（`openssl rand -hex 24`）
- [ ] 启用 HTTPS，或仅在可信内网用 HTTP
- [ ] `server.docs: false`
- [ ] `cors_origins` 限定为前端域名，不要用 `*`
- [ ] `commands.allowed_binaries` 保持最小（默认仅 `docker` / `docker-compose`）
- [ ] 数据目录/卷已纳入备份
- [ ] 扫描范围最小化：方案 A 看 `compose.search_paths`，有 agent 时看 `--stacks-root`
- [ ] agent 若监听 `0.0.0.0`，必须带 `--token`

## 故障排查

### 方案 A（宿主机直跑）

| 现象 | 排查方向 |
| --- | --- |
| `systemctl status` 显示 `activating` 后退出 | `journalctl -u lightpanel -n 50`。常见：`WorkingDirectory` 不对导致 `data/catalog.yaml` 相对路径失效、venv 没装包、`config.local.yaml` 权限服务用户读不到 |
| `Address already in use` | 9001 被别的进程占了；`./deploy/install-host.sh status` 看端口，`ss -tlnp \| grep 9001` 找 PID |
| 页面能开但栈列表是空的 | `compose.search_paths` 没包含栈目录：`config --force --stacks-root ...` 后 `restart` |
| 栈 `up` 报 400 `not readable from this host` | 同一原因；或 compose 文件权限服务用户读不到 |
| 打开页面停在登录框 | 令牌在 `config.local.yaml` 的 `security.api_token`；`./deploy/install-host.sh status` 直接打印 |
| 前端页面 404 / 白屏 | `frontend/dist/index.html` 不存在：`sudo ./deploy/install-host.sh frontend --force` |
| 日志提示 `frontend build not found; API-only mode` | 同上 |
| 依赖装不上 | 换 `--pypi-index`；清华源对 `setuptools` 返回 403 |

### 方案 B（容器化）

| 现象 | 排查方向 |
| --- | --- |
| 容器页空白 / 日志接口报 `读不到 Docker socket（权限不足）` | 容器用户不在 docker 组：`DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) docker compose ... up -d`。此时**概览页仍正常显示数字**，因为读 `/proc` 不需要 socket 权限 |
| 页面提示"引擎不可用" | socket 没挂上 / `docker.mode` 是 `fake`；Docker Desktop 上改用 B-2 |
| 栈 `up` 报"连不上宿主机代理" | agent 没跑或地址不对：`curl http://host.docker.internal:9101/metrics` |
| 栈 `up` 报 400 `not readable from this host` | B-1 且栈不在 `/opt` 下 → 装 agent |
| 栈 `up` 成功但容器里目录是空的 | 最危险的一种：compose 在容器内执行，`./src` 被解析成容器路径，daemon 建了空目录顶上。装 agent |
| 找不到 compose 项目 | 有 agent：检查 `--stacks-root` 与 `--max-depth`；无 agent：检查 `compose.search_paths` 是否已挂进容器 |
| 系统指标与宿主机对不上 | 网络只算容器、磁盘只含挂载目录（Docker Desktop 上 CPU/内存也是虚拟机的）；要统一口径启动 agent 并配 `metrics.remote_url` |
| `compose up` 卡在 `Container ... Creating` | 宿主机目录挂载未被允许（Docker Desktop 文件共享 / SELinux 标签），或挂载路径不存在 |

### 两者都可能遇到

| 现象 | 排查方向 |
| --- | --- |
| 所有接口 401 | 开了鉴权但没登录。页面会停在令牌框；直接调接口需带 `X-LightPanel-Token` |
| 命令报 `command_rejected` | 可执行文件不在 `allowed_binaries`，或 argv 含解释器/危险参数 |
| 命令超时 | 调大 `compose.timeout` 或该命令的 `timeout`（上限 `commands.max_timeout`） |
| 刷新子页面 404 | 后端会把无扩展名路径回退到 `index.html`；仍 404 说明 `frontend/dist` 缺失 |

---

## 相关文件

| 文件 | 用途 |
| --- | --- |
| `deploy/install-host.sh` | 方案 A 的安装与运维入口（子命令见 A.3） |
| `deploy/lightpanel.service.in` | 方案 A 的 systemd 单元模板 |
| `deploy/docker-compose.yml` | 方案 B-1（socket） |
| `deploy/docker-compose.api.yml` | 方案 B-2（TCP API） |
| `deploy/lightpanel-agent.service` | 方案 B 的 agent systemd 单元 |
| `deploy/Dockerfile` | 镜像构建 |
| `config.example.yaml` | 全部配置字段与注释 |
