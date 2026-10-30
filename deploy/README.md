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
| 命令报 `command_rejected` | 可执行文件不在 `allowed_binaries` 内，或 argv 含解释器/危险参数 |
| 命令超时 | 调大 `compose.timeout` 或该命令的 `timeout`（上限 `commands.max_timeout`） |
| 页面 404 | 镜像内 `/app/frontend/dist` 是否存在；直接访问 `/api/health` 验证后端 |
