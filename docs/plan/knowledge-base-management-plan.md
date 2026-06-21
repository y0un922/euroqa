# 知识库管理系统实现计划

## Context

### 项目背景
Eurocode QA 是一个中文问答系统，针对欧洲结构设计标准（EN 199x）。技术栈：
- **后端**: FastAPI (Python 3.12+, `uv` 工具链), 位于 `server/`
- **前端**: React 19 + Vite + Tailwind v4, 位于 `frontend/`
- **存储**: MinIO (PDF 文件), Milvus (向量检索), Elasticsearch (BM25 全文), 本地文件系统 (`data/parsed/`)
- **Pipeline**: PDF → MinerU 解析 → markdown → 分块 → 嵌入 → 索引到 Milvus + ES

### 当前状态
文档管理是**扁平列表**，没有分组概念：
- 文档用 `doc_id`（从文件名 sanitize 而来）标识，对应 chunk 索引中的 `source` 字段
- 上传只支持单文件，处理队列是单 worker 串行
- 前端在侧边栏展示文档列表，无搜索/筛选/分类
- 检索支持按 `source`/`sources`/`doc_type`/`standard_family` 过滤

### 为什么需要知识库
用户有多种规范（EN 1990/1991/1992…）、不同类型（标准/指南/示例）、同一规范的新旧版本共存。需要灵活的知识库（KB）分组机制来：
1. 逻辑组织文档（按项目、按规范族、按版本集）
2. 批量上传/删除
3. 检索时限定范围

### 核心设计决策
- 知识库是文档的**逻辑分组**，文档与 KB 是**多对多**关系（同一文档可归属多个 KB）
- 元数据存 SQLite（`aiosqlite`）— 轻量、无额外服务
- 检索隔离用**外部映射**：KB → doc_id 列表 → 展开为 `source in [...]` 过滤，**不改索引结构，不需重建**
- **删除 KB 默认只删分组元数据**，不删文档索引；删除文档索引是显式危险操作
- **空 KB / 无效 KB 返回空结果**，不退化为全库检索
- 前端新增独立的知识库管理页面

### 现有代码关键路径

| 职责 | 文件 | 说明 |
|------|------|------|
| 文档 API | `server/api/v1/documents.py` | 上传/删除/状态/预览等端点 |
| Pydantic 模型 | `server/models/schemas.py` | DocumentInfo, Chunk, ChunkMetadata, QueryRequest 等 |
| Pipeline 执行 | `server/services/pipeline_runner.py` | 单文档 4 阶段 pipeline (parse→structure→chunk→index) |
| 任务队列 | `server/services/task_manager.py` | FIFO 单 worker 队列 + SSE 广播 |
| MinIO 存储 | `server/services/minio_storage.py` | upload_pdf_to_minio / download_pdf_from_minio |
| DI 注入 | `server/deps.py` | get_config / get_retriever / get_conversation_manager |
| 服务器配置 | `server/config.py` | ServerConfig (pydantic-settings), 路径配置在 L95-101 |
| 应用启动 | `server/main.py` | lifespan 函数管理启动/关闭 |
| 路由注册 | `server/api/v1/router.py` | 所有 v1 路由聚合，含公开合约路由分离逻辑 |
| Agent 依赖 | `server/agents/deps.py` | QADeps dataclass (L16), 含 domain_filter 字段 (L24) |
| Agent 编排 | `server/agents/orchestrator.py` | _build_agent_deps (L118), dispatch_agent / dispatch_agent_streamed |
| 检索工具 | `server/agents/tools/retrieve.py` | _retrieve_impl, L115-116 使用 domain_filter |
| 检索过滤 | `server/core/retrieval_helpers.py` | _build_source_filter_clauses / _build_milvus_filter_expr |
| Milvus 索引 | `shared/milvus_schema.py` | 7 个字段: chunk_id, embedding, source, element_type, doc_type, standard_family, doc_version |
| ES 索引 | `shared/elasticsearch_client.py` | 30+ 字段映射 |
| 文档 sanitize | `server/api/v1/documents.py` L175 | `_sanitize_doc_id(filename)` → 安全 doc_id |
| Source 名称 | `server/api/v1/documents.py` L181 | `_source_names_for_doc_id(doc_id)` → `[doc_id, doc_id.replace("_", " ")]` |
| 前端类型 | `frontend/src/lib/types.ts` | DocumentInfo, DocumentStatus 等 |
| 前端 API | `frontend/src/lib/api.ts` | 文档相关 API 调用 |
| 上传 Hook | `frontend/src/hooks/useDocumentImport.ts` | 上传 + SSE 进度 + 删除 |
| 侧边栏 | `frontend/src/components/Sidebar.tsx` | 文档列表 UI |
| 状态徽章 | `frontend/src/components/DocumentStatusBadge.tsx` | 状态指示组件 |
| 应用入口 | `frontend/src/App.tsx` | AuthenticatedApp, 视图布局 |
| 顶部栏 | `frontend/src/components/TopBar.tsx` | 导航 + 统计信息 |

### 不能动的东西
- **公开合约路由**（`router.py` 中 `_include_public_contract_routes` 注册的）：`POST /query/stream`, `POST /documents/parse`, `POST /documents/status`, `POST /documents/delete`, `GET /sessions/{session_id}`, `POST /translate` — 这些是华科集成的外部接口，请求/响应结构不能改
- **Pipeline 核心** (`pipeline_runner.py`, `task_manager.py`) — KB 层是纯元数据，不改处理流程
- **索引结构** (Milvus/ES schema) — 不加字段，不需重建

---

## Phase 1: SQLite 元数据层

### 1.1 新增依赖
`pyproject.toml` 的 `dependencies` 加 `"aiosqlite>=0.20"`

然后运行 `uv sync` 安装。

### 1.2 ServerConfig 加路径
`server/config.py` → `ServerConfig` 类中（参考 L95-101 的 `glossary_path` / `parsed_dir` / `pdf_dir` 等字段）加：
```python
kb_db_path: str = "data/knowledge_bases.db"
```

### 1.3 新建 `server/services/kb_database.py`

表结构：
```sql
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,           -- Python 端生成 UUID4
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,       -- ISO 8601 字符串
    updated_at TEXT NOT NULL
);

-- 多对多关系：同一 doc_id 可以属于多个 KB
CREATE TABLE IF NOT EXISTS kb_documents (
    kb_id TEXT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    doc_id TEXT NOT NULL,           -- 同 _sanitize_doc_id 输出，即 chunk.metadata.source
    file_name TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    PRIMARY KEY (kb_id, doc_id)
);
CREATE INDEX IF NOT EXISTS idx_kb_documents_doc_id ON kb_documents(doc_id);
```

> **设计说明**：PK 是 `(kb_id, doc_id)`，允许同一文档归属多个 KB。这是有意为之——同一规范（如 EN 1990）可能同时出现在"欧洲规范"和"项目A参考资料"两个 KB 中。doc_id 上**不加 UNIQUE 约束**。

类 `KBDatabase`，使用**持久连接**（在 `initialize` 中打开，`close` 中关闭）：
```python
class KBDatabase:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
    
    async def initialize(self) -> None:
        """打开持久连接 + 建表 + PRAGMA journal_mode=WAL + PRAGMA foreign_keys=ON"""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(CREATE_TABLES_SQL)
    
    async def close(self) -> None:
        """关闭持久连接"""
        if self._db:
            await self._db.close()
            self._db = None
    
    # KB CRUD
    async def create_kb(self, name: str, description: str = "") -> dict:
        """返回 {"id", "name", "description", "created_at", "updated_at"}"""
    
    async def list_kbs(self) -> list[dict]:
        """含 document_count (LEFT JOIN + COUNT)"""
    
    async def get_kb(self, kb_id: str) -> dict | None: ...
    
    async def update_kb(self, kb_id: str, *, name: str | None = None, description: str | None = None) -> dict | None: ...
    
    async def delete_kb(self, kb_id: str) -> bool:
        """CASCADE 会自动删除 kb_documents 行。仅删分组元数据，不删文档索引。"""
    
    # 文档关联
    async def add_documents(self, kb_id: str, docs: list[tuple[str, str]]) -> int:
        """docs = [(doc_id, file_name), ...]，INSERT OR IGNORE，返回实际插入数"""
    
    async def remove_documents(self, kb_id: str, doc_ids: list[str]) -> int: ...
    
    async def list_documents(self, kb_id: str) -> list[dict]:
        """返回 [{"doc_id", "file_name", "added_at"}, ...]"""
    
    async def get_kb_doc_ids(self, kb_id: str) -> list[str]:
        """仅返回 doc_id 列表 — 检索过滤用"""
    
    async def kb_exists(self, kb_id: str) -> bool:
        """检查 KB 是否存在 — 用于检索前校验"""
    
    async def get_exclusive_doc_ids(self, kb_id: str) -> list[str]:
        """返回仅属于此 KB、不属于其他 KB 的 doc_id 列表 — 用于安全删除"""
```

所有方法通过 `self._db` 访问持久连接。aiosqlite 内部序列化写操作，线程安全。

### 1.4 注册到 DI
`server/deps.py` — 参考现有的 `get_config` / `get_retriever` 模式，加全局单例：
```python
from server.services.kb_database import KBDatabase

_kb_database: KBDatabase | None = None

def get_kb_database() -> KBDatabase:
    global _kb_database
    if _kb_database is None:
        _kb_database = KBDatabase(get_config().kb_db_path)
    return _kb_database
```

### 1.5 启动时初始化
`server/main.py` 的 `lifespan` 函数中：
- startup 阶段（在 `yield` 之前）：`await get_kb_database().initialize()`
- shutdown 阶段（在 `yield` 之后）：`await get_kb_database().close()`

参考同文件中 TaskManager 的 `start()` / `stop()` 调用位置。

---

## Phase 2: Pydantic 模型

`server/models/schemas.py` 末尾追加（注意项目用 `CamelModel` 作为 camelCase JSON 的基类，定义在同文件顶部）：

```python
class KnowledgeBaseCreate(CamelModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)

class KnowledgeBaseUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)

class KnowledgeBaseInfo(CamelModel):
    id: str
    name: str
    description: str
    document_count: int = 0
    created_at: str
    updated_at: str

class KBDocumentInfo(CamelModel):
    doc_id: str
    file_name: str
    status: DocumentStatus = DocumentStatus.READY
    added_at: str

class KnowledgeBaseDetail(KnowledgeBaseInfo):
    documents: list[KBDocumentInfo] = Field(default_factory=list)
```

注意 `KBDocumentInfo` 引用了前面已有的 `DocumentStatus` 枚举。

---

## Phase 3: KB API 路由

### 3.1 新建 `server/api/v1/knowledge_bases.py`

```python
router = APIRouter(prefix="/knowledge-bases")
```

端点列表：

| 方法 | 路径 | 功能 | 复用的现有代码 |
|------|------|------|----------------|
| POST | `/` | 创建 KB | — |
| GET | `/` | 列出所有 KB (含 document_count) | — |
| GET | `/{kb_id}` | KB 详情 (含文档列表+实时状态) | `documents.py` 的文档状态查询逻辑 |
| PATCH | `/{kb_id}` | 修改名称/描述 | — |
| DELETE | `/{kb_id}` | 删除 KB 分组元数据 | — |
| DELETE | `/{kb_id}?delete_documents=true` | 危险：删除 KB + 独占文档的索引数据 | `documents.py` 的 `delete_document_chunks` |
| POST | `/{kb_id}/documents` | 关联已有文档到 KB | — |
| DELETE | `/{kb_id}/documents` | 取消关联 (不删索引) | — |
| POST | `/{kb_id}/upload` | 批量上传文件到 KB | `minio_storage.upload_pdf_to_minio`, `TaskManager.enqueue` |

关键实现细节：

**`GET /{kb_id}` (get_knowledge_base)**：
- 从 SQLite 查 KB 信息 + 文档列表
- 对每个 doc_id，查 TaskManager 获取实时状态（参考 `documents.py` 中 `list_documents` 的做法：先查 task_manager 状态，fallback 到 `.indexed` 文件）
- 返回 `KnowledgeBaseDetail` (含 documents 数组，每项有 status)

**`DELETE /{kb_id}` (delete_knowledge_base)**：

两种模式，通过 query param `delete_documents: bool = False` 控制：

**默认模式** (`delete_documents=false`)：仅删除分组元数据
1. 删除 SQLite 中的 KB 记录（CASCADE 清理 kb_documents 关联行）
2. 文档索引（Milvus/ES）和文件（MinIO/本地）完全不动
3. 返回 `{"deleted_kb": kb_id}`

**危险模式** (`delete_documents=true`)：删除分组 + 独占文档的索引
1. 获取 KB 下所有 doc_id
2. 检查是否有正在处理的文档（有则返回 409）
3. 调用 `kb_db.get_exclusive_doc_ids(kb_id)` 获取**仅属于此 KB** 的文档
4. 删除 SQLite 中的 KB 记录
5. 仅对独占文档调用 `delete_document_sources` 删除索引
6. 属于其他 KB 的共享文档只解除关联，索引保留
7. 返回 `{"deleted_kb": kb_id, "deleted_documents": [...], "kept_shared": [...]}`

> **为什么这样设计**：KB 是逻辑分组。"删分组"和"删数据"是不同的动作。默认安全（只删元数据），显式危险（加 `delete_documents=true`）。多 KB 共享文档时，只删独占文档避免误删。

**`POST /{kb_id}/upload` (batch_upload_to_kb)**：
```python
async def batch_upload_to_kb(
    kb_id: str,
    files: list[UploadFile] = File(...),
    context_summary_enabled: bool = Form(True),
    doc_type: DocType | None = Form(None),
    kb_db: KBDatabase = Depends(get_kb_database),
    config: ServerConfig = Depends(get_config),
):
```
对每个文件：
1. `_sanitize_doc_id(file.filename)` 得到 doc_id
2. **冲突检测**：检查该 doc_id 是否已在处理队列中（TaskManager 有活跃状态）→ 若是，跳过此文件并记入 `errors`（"doc_id 正在处理中"）
3. **已存在处理**：如果 doc_id 已存在于索引中（`data/parsed/{doc_id}/.indexed` 存在），视为**覆盖**——pipeline 的 Stage 4 (index) 会先删除旧 chunks 再写入新的，这是现有行为
4. 写入 MinIO (`upload_pdf_to_minio`) — 会覆盖同名文件
5. 保存 `parse_options.json`（参考 `documents.py` `upload_document_to_minio` 的做法）
6. `TaskManager.enqueue(doc_id)` 排入处理队列
7. `kb_db.add_documents(kb_id, [(doc_id, file.filename)])` — INSERT OR IGNORE

返回 `{ kb_id, uploaded: [...], errors: [...] }`

> **冲突规则**：正在处理中 → 跳过报错；已完成索引 → 覆盖（re-parse + re-index）；全新文档 → 正常流程。不使用自动后缀，因为 doc_id 就是 chunk.metadata.source，改名会破坏文档身份。

### 3.2 注册路由
`server/api/v1/router.py` — 在现有的 `router.include_router(glossary.router, ...)` 附近加：
```python
from server.api.v1 import knowledge_bases
router.include_router(knowledge_bases.router, tags=["Knowledge Bases"], dependencies=protected)
```

所有 KB 端点走 `require_auth`（受保护），**不走** `_include_public_contract_routes`。

---

## Phase 4: 检索集成（KB → source 过滤）

**核心思路**: 查询时 `kb_ids` → 查 SQLite 得 doc_id 列表 → 展开为 source 名称列表 → 注入现有 `sources` 过滤器

### 4.1 QueryRequest 加字段
`server/models/schemas.py` → `QueryRequest` (L149) 加：
```python
kb_ids: list[str] | None = Field(default=None, alias="kbIds")
```
`None` = 搜索所有文档（向后兼容）。**注意**：`None`（未传字段）和 `[]`（传了空列表）语义不同，见 4.5。

### 4.2 QADeps 加字段
`server/agents/deps.py` → `QADeps` dataclass (L16) 加：
```python
sources_filter: list[str] | None = None
```

### 4.3 retrieve 工具使用 sources_filter
`server/agents/tools/retrieve.py` — 在 L116 `domain_filter` 逻辑之后加：
```python
if ctx.context.sources_filter is not None:
    filters["sources"] = ctx.context.sources_filter
    _relax_automatic_metadata_filters(
        filters, soft_boosts,
        protected_keys={k for k, v in agent_overrides.items() if v is not None},
    )
```

> **注意用 `is not None` 而非 truthy 判断**。`sources_filter=[]` 理论上不应到达这里（query 层会提前拦截空 KB），但作为防御：空列表仍然会注入 `filters["sources"] = []`。**重要**：当前 `retrieval_helpers.py` 的实现中，`_string_values([])` 返回 `[]`，然后 `if values:` (L254) 和 `if source_values_expr:` (L326) 都会跳过，**不会生成** `terms: []` 或 `source in []`，而是退化为全库检索。因此空 KB 的拦截**必须**在 query 层完成，不能依赖 retriever 兜底。如果未来有其他路径绕过 query 层传入空列表，应在 retriever 的入口处加显式检查：`if sources_filter is not None and not sources_filter: return empty result`。

用 `filters["sources"]`（复数，list 类型）— 现有的 `retrieval_helpers.py` 已经支持：
- `_build_source_filter_clauses` 处理 `filters.get("sources")` → ES `{"terms": {"source": [...]}}`
- `_build_milvus_filter_expr` 处理 `filters.get("sources")` → Milvus `source in [...]`

### 4.4 编排层传递
`server/agents/orchestrator.py` → `_build_agent_deps` (L118-133)：
- 函数签名加 `sources_filter: list[str] | None = None` 参数
- 传入 `QADeps(... sources_filter=sources_filter)`
- `_run_agent_dispatch` 和 `_stream_agent_dispatch` 同样加参数并传递

### 4.5 query.py 解析 kb_ids — 严格隔离语义
`server/api/v1/query.py` — 在调用 dispatch 之前解析：

```python
from dataclasses import dataclass
from server.deps import get_kb_database
from server.api.v1.documents import _source_names_for_doc_id

@dataclass(frozen=True)
class KBResolveResult:
    """KB 解析结果，区分三种状态。"""
    sources: list[str] | None  # None=全局搜索, []=空结果, [...]= scoped 搜索
    error: str | None = None   # 非 None 时应返回错误

async def _resolve_kb_sources(kb_ids: list[str] | None) -> KBResolveResult:
    """将 KB ID 列表展开为检索用的 source 名称列表。
    
    语义：
    - kb_ids is None → 全局搜索（向后兼容），返回 sources=None
    - kb_ids 中有不存在的 KB → 返回 error（不静默忽略）
    - 所有 KB 存在但全部为空 → 返回 sources=[]（空结果，不退化为全库）
    - 正常 → 返回去重后的 sources 列表
    """
    if kb_ids is None:
        return KBResolveResult(sources=None, error=None)
    
    kb_db = get_kb_database()
    
    # 校验所有 KB 都存在
    for kb_id in kb_ids:
        if not await kb_db.kb_exists(kb_id):
            return KBResolveResult(sources=None, error=f"知识库 {kb_id} 不存在")
    
    # 展开 KB → source 列表
    all_sources: list[str] = []
    for kb_id in kb_ids:
        for doc_id in await kb_db.get_kb_doc_ids(kb_id):
            all_sources.extend(_source_names_for_doc_id(doc_id))
    
    # 去重但保留顺序；空列表 = KB 存在但没有文档
    return KBResolveResult(
        sources=list(dict.fromkeys(all_sources)),  # 可能是 []
        error=None,
    )
```

在 `query()` 和 `query_stream()` 两个端点中调用，**按端点类型分别处理**：

**非流式 `query()`**：
```python
resolve = await _resolve_kb_sources(req.kb_ids)
if resolve.error:
    # 返回合法 QueryResponse，用 degraded=True 标记降级，避免前端解析异常
    return QueryResponse(
        answer=resolve.error,
        confidence=Confidence.NONE,
        degraded=True,
    )
if resolve.sources is not None and len(resolve.sources) == 0:
    return QueryResponse(
        answer="所选知识库中没有文档，请先添加文档到知识库。",
        confidence=Confidence.NONE,
        degraded=True,
    )
sources_filter = resolve.sources
# 传给 dispatch_agent
```

**流式 `query_stream()`** — 必须通过 SSE 事件返回，不能用 JSONResponse（前端按 `text/event-stream` 解析）：
```python
resolve = await _resolve_kb_sources(req.kb_ids)

# 在 event_generator() 之前检查，如果有错误/空 KB，生成一个只 yield 错误事件的 generator
if resolve.error:
    async def error_generator():
        yield _error_sse_event(code=400, message=resolve.error)
    return EventSourceResponse(error_generator())

if resolve.sources is not None and len(resolve.sources) == 0:
    async def empty_kb_generator():
        started = time.perf_counter()
        empty_answer = "所选知识库中没有文档，请先添加文档到知识库。"
        # 先发 chunk 事件让前端渲染正文
        yield {
            "event": "chunk",
            "data": json.dumps({"text": empty_answer}, ensure_ascii=False),
        }
        # 再发 done 事件，带 normalized_answer 确保 onDone 覆盖正确
        yield {
            "event": "done",
            "data": json.dumps({
                "answer": empty_answer,
                "normalized_answer": empty_answer,
                "sources": [],
                "confidence": "none",
                "question_type": None,
                "related_refs": [],
                "retrieval_context": None,
                "engineering_context": None,
            }, ensure_ascii=False),
        }
    return EventSourceResponse(empty_kb_generator())

sources_filter = resolve.sources
# 正常进入 event_generator()，传给 dispatch_agent_streamed
```

> **SSE 合约对齐**：`_error_sse_event` 和 `_progress_sse_event` 是项目现有的 SSE 事件构造函数（定义在 `server/api/v1/_progress.py`），前端已有对应的 `onError` / `onProgress` 处理逻辑。空 KB 走 `done` 事件而非 `error`，因为这不是系统错误而是业务空结果。

> **关键区别**：`sources=None` 表示用户没选 KB（全局搜索）；`sources=[]` 表示用户选了 KB 但 KB 是空的（返回空结果）。绝不能让 `[]` 退化为全局搜索。

---

## Phase 5: 前端

前端当前无路由库（`package.json` 中无 react-router），用 **React state 切换视图**。

### 5.1 TypeScript 类型
`frontend/src/lib/types.ts` 加：
```typescript
export type KnowledgeBaseInfo = {
  id: string;
  name: string;
  description: string;
  documentCount: number;
  createdAt: string;
  updatedAt: string;
};

export type KnowledgeBaseDetail = KnowledgeBaseInfo & {
  documents: KBDocumentInfo[];
};

export type KBDocumentInfo = {
  docId: string;
  fileName: string;
  status: DocumentStatus;
  addedAt: string;
};
```

`QueryRequestPayload` 类型（如果存在）加可选字段 `kbIds?: string[]`。

### 5.2 API 层
`frontend/src/lib/api.ts` 加以下函数（参考同文件中 `listDocuments` / `deleteDocument` 等的 pattern）：

```typescript
// KB CRUD
listKnowledgeBases(): Promise<KnowledgeBaseInfo[]>
getKnowledgeBase(kbId: string): Promise<KnowledgeBaseDetail>
createKnowledgeBase(name: string, description?: string): Promise<KnowledgeBaseInfo>
updateKnowledgeBase(kbId: string, data: { name?: string; description?: string }): Promise<KnowledgeBaseInfo>
deleteKnowledgeBase(kbId: string): Promise<void>

// 批量上传
uploadToKnowledgeBase(kbId: string, files: File[], contextSummaryEnabled?: boolean): Promise<{...}>
```

### 5.3 知识库管理页
新建 `frontend/src/components/KnowledgeBasesPage.tsx`

用内部 state 管理两个子视图：

**KB 列表视图** (`selectedKbId === null`)：
- 卡片网格/列表，每张卡片显示 name, description, documentCount, updatedAt
- "创建知识库" 按钮 → 打开创建 modal（输入名称+描述）
- 点击卡片 → 进入详情视图

**KB 详情视图** (`selectedKbId !== null`)：
- 返回按钮 + KB 名称（可编辑）
- 文档列表表格：
  - 列: 文件名, 状态 (复用 `DocumentStatusBadge`), 添加时间, 操作(删除)
  - 正在处理的文档显示进度条
- 多文件拖拽上传区（扩展 `DocumentUpload` 的 pattern，`<input multiple accept=".pdf" />`）
- 批量上传时对每个文件订阅 SSE（复用 `subscribeToPipelineStatus` from `api.ts`）
- "删除知识库" 按钮（确认对话框）

### 5.4 视图切换
`frontend/src/App.tsx`：
```typescript
const [currentView, setCurrentView] = useState<"chat" | "knowledge-bases">("chat");
```
条件渲染：`currentView === "chat"` → 现有聊天 UI；`"knowledge-bases"` → `<KnowledgeBasesPage />`。

`frontend/src/components/TopBar.tsx`：加导航 tab 按钮（"问答" / "知识库"），调用 `onViewChange` 回调。

### 5.5 聊天界面 KB 选择器
`frontend/src/components/MainWorkspace.tsx`（或输入区域组件）：
- 在输入框上方加 KB 多选下拉（从 `listKnowledgeBases()` 加载选项）
- 选中的 KB IDs 随查询请求发送 (`kbIds` 字段)
- 不选 = 搜索全部文档

需要在查询发送逻辑中（`useEuroQaDemo.ts` 或对应 hook）把 `kbIds` 加入请求 payload。

---

## Phase 6: 测试

### `tests/server/test_kb_database.py`
- 创建/列出/获取/更新/删除 KB
- 添加/移除/列出文档
- 同一文档添加到多个 KB（多对多）
- `get_kb_doc_ids` 返回正确列表
- `get_exclusive_doc_ids` 正确区分独占/共享文档
- `kb_exists` 对存在/不存在的 KB 返回正确结果
- 删除 KB 级联清理 kb_documents（但不删共享文档的关联）
- name 唯一约束（重复创建报错）

### `tests/server/test_knowledge_bases_api.py`
- 用 `httpx.AsyncClient` + `app` 做端到端 API 测试
- CRUD 端点返回正确 shape
- 批量上传：正常上传 + doc_id 冲突时返回 errors
- 删除 KB 默认模式：只删元数据，索引不变
- 删除 KB 危险模式（`delete_documents=true`）：独占文档删索引，共享文档保留

### `tests/server/test_kb_retrieval_isolation.py` — **检索隔离链路测试**
- `_resolve_kb_sources` 传入有效 KB → 返回正确 sources 列表
- `_resolve_kb_sources` 传入不存在的 KB → 返回 error
- `_resolve_kb_sources` 传入空 KB（存在但无文档） → 返回 `sources=[]`（非 None）
- `_resolve_kb_sources` 传入 `None` → 返回 `sources=None`（全局搜索）
- `_resolve_kb_sources` 传入多个 KB → sources 去重合并
- `POST /query` 携带 `kbIds` 时，`sources_filter` 正确传递到 retriever
- `POST /query/stream` 同上（流式一致性）
- 空 KB 查询返回空结果提示，不触发 LLM 调用
- **空 KB 短路断言**：空 KB 查询（非流式和流式）必须断言 `dispatch_agent` / `dispatch_agent_streamed` **未被调用**（mock + assert_not_called），防止未来改动绕过 query 层短路进入 retriever 全库检索

---

## 实现顺序

```
Phase 1 (SQLite 基础) → Phase 2 (模型) → Phase 3 (API) → Phase 4 (检索集成) → Phase 5 (前端) → Phase 6 (测试)
```

每个 Phase 内按上述编号顺序实现。Phase 3 依赖 1+2，Phase 4 依赖 1，Phase 5 依赖 3+4。

## 验证方式

1. `uv sync` — 安装 aiosqlite 依赖
2. `uv run pytest tests/server/test_kb_database.py` — 验证 SQLite 层
3. `uv run pytest tests/server/test_knowledge_bases_api.py` — 验证 API
4. 启动后端 `./scripts/start-backend.sh`，curl 测试：
   ```bash
   # 创建 KB
   curl -X POST http://localhost:8080/api/v1/knowledge-bases \
     -H "Content-Type: application/json" -H "Authorization: Bearer <token>" \
     -d '{"name": "欧洲规范", "description": "EN 199x 系列标准"}'
   
   # 批量上传
   curl -X POST http://localhost:8080/api/v1/knowledge-bases/<kb_id>/upload \
     -H "Authorization: Bearer <token>" \
     -F "files=@EN_1990.pdf" -F "files=@EN_1991.pdf"
   
   # 查看 KB 详情
   curl http://localhost:8080/api/v1/knowledge-bases/<kb_id> \
     -H "Authorization: Bearer <token>"
   ```
5. 启动前端 `cd frontend && pnpm dev`，浏览器验证知识库管理页
6. 在聊天界面选择 KB 后提问，验证检索范围正确隔离
