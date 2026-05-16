# 任务清单: frontend-minio-session-proxy

```yaml
@feature: frontend-minio-session-proxy
@created: 2026-05-15
@status: completed
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 5/5 (100%) | 更新: 2026-05-15 20:02:00
当前: 前端代理上传与 sessionId 联调逻辑已完成
<!-- LIVE_STATUS_END -->

## 任务列表

### 1. 后端代理上传
- [√] 1.1 增加 MinIO 上传 helper，支持 bucket 自动创建。
- [√] 1.2 增加 `/api/v1/documents/upload-to-minio` 并触发解析。

### 2. 前端上传流程
- [√] 2.1 增加 `uploadDocumentToMinio` API。
- [√] 2.2 文档导入 hook 改为单步代理上传。

### 3. 前端会话逻辑
- [√] 3.1 生成 `1001_UUID去横线` 格式会话 ID。
- [√] 3.2 流式问答 payload 改发 `sessionId`。

### 4. 测试
- [√] 4.1 补充后端代理上传 mock 测试。
- [√] 4.2 补充前端 API payload 测试。
- [√] 4.3 运行后端与前端测试。

### 5. 文档同步
- [√] 5.1 更新模块文档与 CHANGELOG。

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-05-15 19:57 | 核心实现 | in_progress | 后端代理上传与前端 sessionId 切换已编码 |
| 2026-05-15 20:02 | 验证完成 | completed | `tests/server` 216 passed，前端测试 92 passed，TypeScript 与 Ruff 通过 |
