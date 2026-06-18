# Euro_QA

Euro_QA 是面向 Eurocode 文档的本地问答系统，包含 FastAPI 后端、React 前端、PDF 解析与检索索引流水线。新成员拿到代码后，按本文档完成环境配置、索引构建和前后端启动。

## 目录结构

- `server/`: FastAPI 后端服务与 API。
- `frontend/`: React + Vite 前端。
- `pipeline/`: PDF 解析、结构化、切块、向量索引和 Elasticsearch 索引流水线。
- `shared/`: 后端与 pipeline 共享的模型客户端、检索客户端和工具代码。
- `data/pdfs/`: 默认 PDF 数据目录。
- `data/parsed/`: PDF 解析后的中间产物目录。
- `data/glossary.json`: 术语库数据。
- `scripts/`: 本地启动脚本。
- `tests/`: 后端、pipeline 和共享模块测试。

## 环境要求

- Python 3.12+
- `uv`
- Node.js 20+
- `pnpm`
- Docker / Docker Compose

## 1. 配置后端环境变量

在项目根目录执行：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写 LLM 配置：

```bash
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

如果本机不适合加载 embedding 或 rerank 模型，建议使用远程服务：

```bash
EMBEDDING_PROVIDER=remote
EMBEDDING_API_URL=your-embedding-endpoint
EMBEDDING_API_KEY=your-api-key

RERANK_PROVIDER=remote
RERANK_API_URL=your-rerank-endpoint
RERANK_API_KEY=your-api-key
```

默认数据路径：

```bash
PDF_DIR=data/pdfs
PARSED_DIR=data/parsed
GLOSSARY_PATH=data/glossary.json
MILVUS_HOST=localhost
MILVUS_PORT=19530
ES_URL=http://localhost:9200
```

不要把个人 `.env` 发给别人；新成员应从 `.env.example` 自己复制并填写。

## 2. 启动检索依赖

问答和索引构建依赖 Milvus、Elasticsearch 和 Redis：

```bash
docker compose up -d milvus-etcd milvus-minio milvus elasticsearch redis
```

也可以使用项目脚本启动 Milvus 和 Elasticsearch，再单独启动 Redis：

```bash
./scripts/start-search-stack.sh
docker compose up -d redis
```

确认容器状态：

```bash
docker compose ps
```

## 3. 安装后端依赖

```bash
uv sync
```

## 4. 构建检索索引

首次运行需要把 `data/pdfs/` 中的 PDF 解析、切块并写入 Milvus / Elasticsearch：

```bash
uv run euro-pipeline --pdf-dir data/pdfs
```

流水线阶段：

- Stage 1: PDF 解析为 Markdown。
- Stage 2: Markdown 结构化。
- Stage 3: 文档切块。
- Stage 3.5: 可选上下文增强。
- Stage 4: 写入 Milvus 和 Elasticsearch。

如果已经有 `data/parsed/` 和历史 debug 产物，只想重建索引，可以尝试从 Stage 4 开始：

```bash
uv run euro-pipeline --start-stage 4
```

## 5. 启动后端

```bash
./scripts/start-backend.sh
```

后端默认地址：

```text
http://localhost:8080
```

## 6. 配置并启动前端

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev
```

前端默认地址：

```text
http://localhost:4173
```

前端默认连接：

```bash
VITE_API_BASE_URL=http://localhost:8080
```

## 常用命令

后端测试：

```bash
uv run pytest
```

前端类型检查：

```bash
cd frontend
pnpm run lint
```

前端构建：

```bash
cd frontend
pnpm run build
```

## 交付给新成员时的打包建议

可以包含：

- 源码目录：`server/`、`shared/`、`pipeline/`、`frontend/src/`、`tests/`、`scripts/`
- 配置和锁文件：`pyproject.toml`、`uv.lock`、`docker-compose.yml`、`Dockerfile`、`.env.example`、`frontend/.env.example`
- 可运行数据：`data/pdfs/`、`data/parsed/`、`data/glossary.json`
- 文档：`README.md`、`docs/`、接口文档和必要业务资料

不要包含：

- `.env`
- `.venv/`
- `frontend/node_modules/`
- `frontend/dist/`
- `.git/`
- `.pytest_cache/`
- `.ruff_cache/`
- `__pycache__/`
- `.codex/`
- `.ace-tool/`
- `.helloagents/plan/`
- `.trellis/.runtime/`
- `.trellis/workspace/`
- `outputs/`

示例打包命令：

```bash
zip -r "/tmp/euro_qa_code_runnable_data_$(date +%Y%m%d_%H%M%S).zip" . \
  -x "./.git/*" \
  -x "./.env" \
  -x "./.venv/*" \
  -x "./frontend/node_modules/*" \
  -x "./frontend/dist/*" \
  -x "./.pytest_cache/*" \
  -x "./.ruff_cache/*" \
  -x "./**/__pycache__/*" \
  -x "./.codex/*" \
  -x "./.ace-tool/*" \
  -x "./.helloagents/plan/*" \
  -x "./.trellis/.runtime/*" \
  -x "./.trellis/workspace/*" \
  -x "./outputs/*"
```

## 常见问题

- 后端能启动但问答没有结果：先确认 Milvus 和 Elasticsearch 已启动，并且 `uv run euro-pipeline --pdf-dir data/pdfs` 已成功完成。
- 本地模型加载慢或显存不足：把 `EMBEDDING_PROVIDER` 和 `RERANK_PROVIDER` 改成 `remote`，并填写对应 API 地址和 key。
- 前端请求失败：确认后端在 `http://localhost:8080`，并检查 `frontend/.env` 中的 `VITE_API_BASE_URL`。
- 认证问题：`.env` 中 `ACCESS_PASSWORD` 为空时禁用登录；需要开启登录时填写密码，并把 `AUTH_SECRET_KEY` 改为随机字符串。
