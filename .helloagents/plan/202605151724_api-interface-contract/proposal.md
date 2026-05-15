# 变更提案: api_interface_contract

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
根目录 `接口文档.md` 定义了对华科方开放的后端接口契约。当前 FastAPI 后端已有文档上传、单文档处理、单文档状态流、单文档删除、来源翻译和流式问答能力，但路径、字段命名和响应形状与接口文档不完全一致。

### 目标
按接口文档实施外部对接接口，并将单文件处理相关能力统一到接口文档契约：
- `POST /api/v1/documents/parse`
- `POST /api/v1/documents/status`
- `POST /api/v1/documents/delete`
- `POST /api/v1/query/stream`
- `POST /api/v1/translate`

### 约束条件
```yaml
兼容性约束: 保留现有前端仍在使用的旧路径作为 wrapper，内部复用新契约逻辑
安全约束: 批量删除测试必须 mock，不连接真实向量库或删除真实数据
业务约束: 外部契约使用 camelCase 和 code 字段
```

### 验收标准
- [ ] 新增接口文档要求的文档解析、批量状态、批量删除和翻译端点。
- [ ] 单文件处理旧端点复用新逻辑，行为与接口文档契约一致或保持兼容。
- [ ] `/query/stream` 支持 `sessionId` 请求字段，并在 `done` 事件中输出接口文档要求的 camelCase 元数据。
- [ ] 契约测试覆盖新增端点、错误分支和批量删除 mock 行为。

---

## 2. 方案

### 技术方案
采用方案 B：接口文档端点作为 canonical 实现，旧单文件接口作为兼容 wrapper。

实现策略：
- 在 `server/models/schemas.py` 增加接口文档专用 Pydantic 模型，并通过 alias 支持 camelCase。
- 在 `server/api/v1/documents.py` 提取文档排队、状态构造、删除索引数据的共享函数，供新旧端点复用。
- 在 `server/api/v1/sources.py` 增加 `/translate`，复用现有 LLM 翻译 helper。
- 在 `server/api/v1/query.py` 兼容 `sessionId`，stream `done` payload 增补 `code`、`questionType`、`answerMode`、`title` 等 camelCase 字段。
- 在 `tests/server/test_api.py` 增加契约测试，所有外部依赖用 mock 或临时目录替代。

### 影响范围
```yaml
涉及模块:
  - server/models/schemas.py: 新增请求/响应 DTO 和 alias 兼容
  - server/api/v1/documents.py: 新增接口文档文档管理端点并复用旧逻辑
  - server/api/v1/query.py: 流式问答请求/完成态契约兼容
  - server/api/v1/sources.py: 新增 /translate 外部翻译端点
  - tests/server/test_api.py: 补充契约测试
预计变更文件: 5
```

### 风险评估
| 风险 | 等级 | 应对 |
|------|------|------|
| 批量删除误连真实索引 | 高 | 单元测试 mock `delete_document_chunks`，实现只复用现有删除路径，不在开发中执行真实删除 |
| 旧前端依赖 snake_case | 中 | 保留旧路径和旧响应字段 wrapper，新增外部端点使用 camelCase |
| Pydantic alias 影响现有响应 | 中 | 新旧模型分离，尽量不改变既有 `QueryResponse` 和旧文档接口模型 |

---

## 3. 技术设计

### API设计
#### POST /api/v1/documents/parse
- **请求**: `docId`, `fileName`, `minioPath`
- **响应**: `code`, `docId`, `status`, `message`

#### POST /api/v1/documents/status
- **请求**: `docIds`，最多 50 个
- **响应**: `code`, `results[]`

#### POST /api/v1/documents/delete
- **请求**: `docIds`，最多 50 个
- **响应**: `code`, `results[]`

#### POST /api/v1/translate
- **请求**: `text`, `context`
- **响应**: `code`, `translation`

#### POST /api/v1/query/stream
- **请求**: 支持 `sessionId`，兼容旧 `conversation_id`
- **done 响应**: 增加 `code`, `questionType`, `answerMode`, `title`，同时保留现有字段。

---

## 4. 核心场景

### 场景: 华科方触发文档解析
**模块**: Documents API
**条件**: PDF 已上传到本系统可处理目录或 MinIO 路径由外部传入。
**行为**: 调用 `POST /api/v1/documents/parse`。
**结果**: 文档进入本系统解析队列，返回 `status=processing`。

### 场景: 华科方批量查询和删除文档索引
**模块**: Documents API
**条件**: 传入 `docIds`。
**行为**: 调用批量状态或删除接口。
**结果**: 每个文档独立返回成功、失败或冲突，不因单条失败影响整体响应。

---

## 5. 技术决策

### api_interface_contract#D001: 新契约 canonical，旧端点 wrapper
**日期**: 2026-05-15
**状态**: ✅采纳
**背景**: 用户要求按接口文档实施，并补充单文件处理也改成接口文档一样；同时现有前端和测试仍依赖旧路径。
**选项分析**:
| 选项 | 优点 | 缺点 |
|------|------|------|
| A: 仅新增外部端点 | 风险低 | 不满足单文件处理统一契约 |
| B: 新契约 canonical，旧端点 wrapper | 满足外部契约且保留兼容 | 需要维护少量 wrapper |
| C: 删除旧端点 | 契约最干净 | 破坏现有前端和回归测试 |
**决策**: 选择方案 B。
**理由**: 在满足接口文档的同时，把回归风险限制在 API 边界层。
**影响**: Documents API、Query API、Sources/Translate API、API 契约测试。
