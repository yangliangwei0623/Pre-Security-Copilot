# Pre-Security Copilot

北京场景的多模态行前安检排查 Demo。应用使用通义千问识别物品，由可追溯的 Python 规则引擎逐行程段判断 TSA/FAA、中国民航、中国铁路、北京地铁、故宫和天安门广场场景。

模型负责提取图片中的可见事实和选择已有报告证据，不负责决定物品是否放行。规则未覆盖、核验超期或属性不清楚时，结果为“需确认”。

## 本地运行

环境要求：Python 3.12、uv。真实照片识别需要阿里云百炼 API Key；不配置密钥时可使用明确标注的示例回放。

```bash
cp .env.example .env
uv python install 3.12
uv sync --frozen
uv run python -m app.cli init-demo
uv run uvicorn app.main:app --reload --port 8000
```

打开 `http://127.0.0.1:8000`。

`.env` 中常用配置：

- `DASHSCOPE_API_KEY`：百炼 API Key。
- `MODEL_BASE_URL`：默认北京地域兼容接口 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `MODEL_NAME`：默认 `qwen3-vl-plus`。
- `AMAP_API_KEY`：高德 Web 服务 Key；缺少时只展示虚构且有醒目标识的服务点卡片。
- `BOCHA_API_KEY`：可选的官方网页发现搜索。搜索结果不会自动修改规则。
- `DATA_DIR`：SQLite、LangGraph 检查点和清洗后图片目录。
- `COOKIE_SECURE`：通过 HTTPS 部署时设为 `true`。

使用一张不含敏感信息的测试图片检查模型配置：

```bash
uv run python -m app.cli check-model /absolute/path/to/test-image.jpg
```

## Docker

```bash
cp .env.example .env
docker compose up -d --build
curl http://127.0.0.1:8000/healthz
```

容器使用非 root 用户，仅暴露 8000 端口，数据写入命名卷 `copilot-data`。Compose 固定单个 Uvicorn worker，因为 SQLite 和进程内任务队列面向单机 Demo。

为常见 Linux AMD64 服务器导出离线镜像：

```bash
./scripts/export-image.sh
```

将 `dist/pre-security-copilot-amd64.tar`、`dist/compose.yaml`、`dist/.env.example` 上传到服务器。导出的 Compose 文件只引用已加载镜像，不要求服务器保留源代码或 Dockerfile：

```bash
docker load -i pre-security-copilot-amd64.tar
cp .env.example .env
# 编辑 .env，填写密钥；HTTPS 反向代理后将 COOKIE_SECURE=true
docker compose up -d
```

直接使用服务器 IP 演示时，可通过安全组开放映射端口。正式公开服务应放在 HTTPS 反向代理后，限制上传大小并备份 Docker volume。

## 规则维护

首批规则在 `app/data/rules.json`，保存官方来源、摘录、适用日期和人工核验日期。`scripts/build_seed.py` 是当前种子数据的可复现定义。更新规则时必须使用新的版本号：

```bash
uv run python -m app.cli import-rules /absolute/path/to/reviewed-rules.json
```

已发布的规则版本不可覆盖，历史报告保留运行时规则快照。默认核验窗口为 90 天，未来行程超出窗口时会显示“需确认”。

## 测试

```bash
uv run ruff check app scripts tests
uv run pytest -q
```

当前测试覆盖规则边界、来源超期、会话隔离、动态追问、示例回放、图片清洗和无模型密钥降级。真实千问与高德调用需要各自密钥，因此不在默认自动化测试中发送外部请求。

## 重要限制

- 这是行前参考，不是安检放行、法律认定或运输承诺。
- 高德 POI 只证明地点存在，不证明接受护照、危险品、寄存或寄送。
- 故宫和天安门广场是独立场景，预约、证件与临时管制需从各自官方渠道确认。
- Demo 不提供支付、真实快递下单或账号系统。
