# 任务清单: minio-redis-integration

```yaml
@feature: minio-redis-integration
@created: 2026-05-15
@status: in_progress
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 6/6 (100%) | 更新: 2026-05-15 19:50:00
当前: MinIO 与 Redis 集成已完成
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 6 | 0 | 0 | 6 |

---

## 任务列表

### 1. 配置与依赖
- [√] 1.1 更新 `pyproject.toml` 增加 MinIO/Redis 客户端依赖。
- [√] 1.2 更新 `server/config.py` 增加 MinIO/Redis 配置。

### 2. MinIO 文档读取
- [√] 2.1 新增 MinIO 下载服务。
- [√] 2.2 `/documents/parse` 从 `bucket/key` 下载 PDF 后入队。

### 3. Redis 会话
- [√] 3.1 实现 RedisConversationManager。
- [√] 3.2 `/query` 与 `/query/stream` 读取历史并写入本轮 Q&A。

### 4. 部署
- [√] 4.1 更新 `docker-compose.yml` 与 systemd search stack。

### 5. 测试
- [√] 5.1 补充 MinIO/Redis mock 测试并跑服务端测试。

### 6. 文档同步
- [√] 6.1 更新 `.helloagents` 模块文档与 CHANGELOG。

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-05-15 19:21 | 方案确认 | in_progress | 采用完整补齐方案 |
| 2026-05-15 19:50 | 实施与验证 | completed | `tests/server` 214 passed，局部 ruff 通过 |

---

## 执行备注

> 本轮只改代码、配置和测试，不连接真实生产 MinIO/Redis。
