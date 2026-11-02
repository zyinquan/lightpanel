# lightpanel (backend)

LightPanel 的 Python 后端：FastAPI + 端口适配器架构，同时对外提供 REST API 与前端 SPA 静态文件。

- 架构说明：[../docs/architecture.md](../docs/architecture.md)
- 配置项：[../docs/configuration.md](../docs/configuration.md)
- 开发与测试：[../docs/development.md](../docs/development.md)

本地开发：

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
pip install -e ".[dev]"
lightpanel --config ../config.example.yaml
```
