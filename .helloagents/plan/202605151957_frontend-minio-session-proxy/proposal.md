# 方案: frontend-minio-session-proxy

```yaml
@feature: frontend-minio-session-proxy
@created: 2026-05-15
@status: in_progress
@mode: R3
```

## 1. 目标

让前端按华科方对接逻辑进行本地联调：
- PDF 由浏览器上传到后端代理接口，不暴露 MinIO 凭据。
- 后端写入本系统部署的 MinIO，再复用 `/documents/parse` 队列逻辑触发解析。
- 前端问答请求发送 `sessionId=userId_UUID去横线`，用于验证 Redis 会话上下文。

## 2. 数据流

浏览器 `multipart/form-data` PDF → `POST /api/v1/documents/upload-to-minio` → MinIO `eurocode/uploads/{docId}.pdf` → 本地 pipeline PDF 输入目录 → TaskManager 解析队列。

前端会话创建 → `1001_{uuidWithoutHyphens}` → `POST /api/v1/query/stream` 的 `sessionId` 字段 → 后端 Redis `context:{sessionId}` 与 `user:{userId}:sessions`。

## 3. 实施范围

- `server/services/minio_storage.py`: 增加上传 helper，并自动创建 bucket。
- `server/api/v1/documents.py`: 增加 `upload-to-minio` 代理接口。
- `server/models/schemas.py`: 增加代理上传响应模型。
- `frontend/src/lib/api.ts` / `types.ts`: 增加代理上传 API，问答 payload 改发 `sessionId`。
- `frontend/src/hooks/useDocumentImport.ts`: 上传流程从两步改为单步代理上传。
- `frontend/src/hooks/useEuroQaDemo.ts`: 生成并复用外部 `sessionId`。
- `tests/server/test_api.py` 与 `frontend/src/lib/api.test.ts`: 覆盖代理上传与 `sessionId` payload。

## 4. 验收标准

- [ ] 前端上传 PDF 只调用 `/documents/upload-to-minio`。
- [ ] 后端上传到 MinIO 的路径为 `eurocode/uploads/{docId}.pdf`。
- [ ] 代理上传成功后自动触发解析队列。
- [ ] 问答流式请求包含 `sessionId`，格式为 `1001_UUID去横线`。
- [ ] 后端与前端相关测试通过。

## 5. 决策

### frontend-minio-session-proxy#D001: 后端代理上传

浏览器不直接连接 MinIO，不下发 MinIO access key/secret key。前端只调用后端代理接口，由后端完成 bucket 创建、对象写入和解析触发。
