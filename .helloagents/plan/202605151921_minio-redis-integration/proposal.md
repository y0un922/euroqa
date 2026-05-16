# 变更提案: minio-redis-integration

## 元信息
```yaml
类型: 新功能
方案类型: implementation
优先级: P2
状态: 已确认
创建: 2026-05-15
```

---

## 1. 需求

### 背景
接口文档要求 MinIO 和 Redis 均由本系统部署，并由华科方共享使用。当前仓库只有 Milvus 内部使用的 `milvus-minio`，没有独立对外 MinIO，也没有 Redis 会话存储。

### 目标
- 部署独立 MinIO 与 Redis 服务。
- `/documents/parse` 根据 `minioPath=bucket/key` 从 MinIO 下载 PDF 到本地处理目录后入队。
- `/query` 与 `/query/stream` 按 `sessionId` 读取 Redis 历史，完成后追加本轮 Q&A，并更新 session 元数据的 `title` 与 `updatedAt`。

### 约束条件
```yaml
配置约定:
  minioPath: bucket/key
  env:
    - MINIO_ENDPOINT
    - MINIO_ACCESS_KEY
    - MINIO_SECRET_KEY
    - REDIS_URL
安全约束: 测试中 mock MinIO/Redis，不连接真实服务
兼容性约束: 保留现有内存 ConversationManager 作为 Redis 未配置或客户端不可用时的回退
```

### 验收标准
- [ ] `docker-compose.yml` 和 systemd search stack 包含独立 `minio` 与 `redis`。
- [ ] `ServerConfig` 包含 MinIO 和 Redis 配置。
- [ ] `/documents/parse` 支持从 MinIO 下载 `bucket/key` 对象。
- [ ] `/query` 与 `/query/stream` 使用 `sessionId` 读取和写入 Redis 会话。
- [ ] 单元测试覆盖 MinIO 下载、Redis 历史读取/写入、无 Redis 回退。

---

## 2. 方案

### 技术方案
- 使用 `minio` Python SDK 下载对象，封装在 `server/services/minio_storage.py`。
- 使用 `redis.asyncio` 封装 Redis 会话仓库，放在 `server/core/conversation.py`，保留现有内存 manager。
- `server/deps.py` 根据配置优先创建 RedisConversationManager，失败或未配置时回退内存 manager。
- `server/api/v1/documents.py` 把本地路径兼容逻辑升级为 MinIO 优先、本地文件回退。
- `server/api/v1/query.py` 把 `sessionId` 的历史传给生成层，并在完成后写入 Redis。

### 影响范围
```yaml
涉及模块:
  - server.config: MinIO/Redis 配置
  - server.core.conversation: Redis 会话持久化
  - server.services.minio_storage: MinIO PDF 下载
  - server.api.v1.documents: parse 下载并入队
  - server.api.v1.query: 会话历史读写
  - docker-compose.yml / deploy/systemd: 部署服务
预计变更文件: 8-10
```

### 风险评估
| 风险 | 等级 | 应对 |
|------|------|------|
| 外部服务不可用导致问答失败 | 中 | Redis 未配置或异常时回退内存 manager |
| MinIO 凭据泄露 | 中 | 只通过 env 配置，不硬编码真实凭据 |
| 生成层历史格式不一致 | 中 | 使用 `{question, answer}` 格式，与现有 prompt builder 兼容 |

---

## 3. 技术设计

### 数据流
```
MinIO bucket/key -> server/services/minio_storage.py -> data/pdfs/{docId}.pdf -> pipeline
sessionId -> Redis context:{sessionId} -> generation conversation_history -> Redis append
```

### Redis Key
- `context:{sessionId}`: List，每条为 JSON message。
- `user:{userId}:sessions`: Hash，field 为 `sessionId`，value 为 JSON metadata。
- `userId` 从 `sessionId` 的 `_` 前缀解析。

---

## 4. 核心场景

### 场景: 华科方上传 PDF 后触发解析
**模块**: server.api.v1.documents
**条件**: PDF 已存在于本系统 MinIO，`minioPath` 为 `bucket/key`。
**行为**: `/documents/parse` 下载对象到本地 `pdf_dir/{docId}.pdf` 并加入 pipeline 队列。
**结果**: 返回 `status=processing`，后续可通过批量状态接口查询进度。

### 场景: 华科方使用 sessionId 多轮问答
**模块**: server.api.v1.query
**条件**: 请求体包含 `sessionId=userId_uuid`。
**行为**: 后端读取 `context:{sessionId}` 历史并传给生成层，完成后追加本轮 Q&A。
**结果**: Redis 中更新会话上下文、`updatedAt`，首轮补齐 `title`。

---

## 5. 技术决策

### minio-redis-integration#D001: Redis 优先，内存回退
**日期**: 2026-05-15
**状态**: ✅采纳
**背景**: 接口文档要求 Redis 会话，但本地开发和测试不应强依赖外部 Redis。
**决策**: 配置了 `REDIS_URL` 时使用 Redis 会话管理，否则沿用内存 manager。
**影响**: `server.deps`、`server.core.conversation`、问答 API。
