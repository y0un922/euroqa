# 任务清单: api_interface_contract

```yaml
@feature: api_interface_contract
@created: 2026-05-15
@status: in_progress
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: completed | 进度: 7/7 (100%) | 更新: 2026-05-15 18:10:00
当前: 接口文档契约已完成
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 7 | 0 | 0 | 7 |

---

## 任务列表

### 1. Schema 契约

- [x] 1.1 在 `server/models/schemas.py` 中新增接口文档请求/响应 DTO。

### 2. 文档接口

- [x] 2.1 在 `server/api/v1/documents.py` 中新增 `/documents/parse`、`/documents/status`、`/documents/delete`。
- [x] 2.2 将旧单文件处理和删除端点改为复用新契约逻辑。

### 3. 问答和翻译接口

- [x] 3.1 在 `server/api/v1/query.py` 中兼容 `sessionId` 并补齐 stream `done` camelCase 元数据。
- [x] 3.2 在 `server/api/v1/sources.py` 中新增 `/translate` 外部端点。

### 4. 测试

- [x] 4.1 在 `tests/server/test_api.py` 中补充接口文档契约测试。

### 5. 验收

- [x] 5.1 运行后端 API 测试并修复回归。

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-05-15 17:24 | 方案确认 | in_progress | 采用方案 B |
| 2026-05-15 18:10 | 代码实施与验证 | completed | `tests/server/test_api.py`、`tests/server/test_generation.py`、`tests/server` 全部通过 |

---

## 执行备注

> 批量删除实现和测试必须避免真实外部数据删除；测试中使用 mock 或临时目录。
