# Euro QA 后端接口文档（v2）

> **范围**：本期对外接口如下。  
> - `POST /api/v1/documents/parse`：一次提交多个文件，本侧队列逐个解析  
> - `GET /api/v1/documents/parse-queue`：查询解析队列占用与剩余可提交数量  
> - `POST /api/v1/query/stream`：按华科传入的 `docIds` 过滤检索范围  
>
> 其余接口（status / delete / translate / 会话 Redis 约定等）仍按现网 `接口文档.md` 执行，本文不重复。  

---

## 0. 职责与约定

### 0.1 职责划分（与本期相关）

| 职责 | 华科方 | 本系统 |
|------|--------|--------|
| 知识库分组、文档归属、用户权限 | ✅ | ❌ |
| PDF 上传至 MinIO | ✅ | 解析时按 `minioPath` 读取 |
| PDF 解析 / 分块 / 索引 | ❌ | ✅（FIFO 队列串行） |
| 提示用户「还能上传多少」 | 调 parse-queue 展示 | ✅ 提供队列容量快照 |
| 计算「本次可检索文档」列表 | ✅ → 传入 `docIds` | ✅ 仅在该集合内检索 |

### 0.2 通用约定

| 项目 | 说明 |
|------|------|
| Base URL | `/api/v1` |
| 字段命名 | camelCase |
| 时间格式 | ISO 8601，如 `2026-05-07T10:30:00Z` |
| HTTP / 业务码 | 请求到达应用后 HTTP 恒为 `200`；业务结果看响应体 `code` |
| 错误响应 | `{ "code": number, "message": string, "detail": string \| null }` |
| `docId` | 华科生成的文档稳定主键；索引 `source`、删除、过滤均使用该值，**不用** `fileName` 替代 |
| `minioPath` | **`bucket/key` 格式**（与现网一致），例如 `eurocode/uploads/doc_001.pdf`；也接受可选 `s3://` 前缀 |

### 0.3 已确认决策摘要

| 项 | 结论 |
|----|------|
| 批量 parse 冲突 | 整批 `code=200`，单条 `already_processing`，其余照常入队 |
| 已成功文档再 parse | **允许覆盖重跑**（本系统负责替换/清理旧索引） |
| MinIO 校验时机 | 入队只做参数校验；worker 拉取失败 → 该文档 `failed` |
| `minioPath` | 沿用现网 `bucket/key` |
| parse 请求形态 | **仅批量 `files[]`**，不再兼容 v1 单对象 |
| `files` 上限 | **20**（单次请求上限，与队列总容量无关） |
| 队列总容量 | **100** 个未完成任务（排队中 + 正在解析）；可配置 |
| 队列反压 | 积压 ≥ 容量时，**新请求**整批 `429`；**已入队任务不丢** |
| 成功/失败文档 | **不占用**队列名额 |
| 队列查询 | 提供 `GET /documents/parse-queue`，返回 `remaining` 等字段 |
| query `docIds` | **必填**，长度 ≥ 1；空/缺省 → `400`，禁止全库 |
| query `docIds` 上限 | **100** |
| 交叉引用 | 可引用原文必须 ∈ `docIds`，不得漏出集合外正文 |
| 本系统知识库 API | 内部/新分支实现用，**华科无需对接** |

---

## 1. 触发 PDF 解析（批量）

华科将 PDF 上传至 MinIO 后调用本接口。解析流水线：

**PDF 文本提取 → 结构化 → 分块 → 上下文增强（可选）→ 向量化索引**

本系统 **FIFO 队列 + 单 worker 串行**：请求内合法文件先全部受理入队，再按序逐个解析。  
已返回受理成功的任务**不会**因后续新请求而丢弃。

```
POST /api/v1/documents/parse
Content-Type: application/json
```

### 1.1 请求体

```json
{
  "contextSummaryEnabled": true,
  "files": [
    {
      "docId": "doc_20260728_001",
      "fileName": "EN 1992-1-1.pdf",
      "minioPath": "eurocode/uploads/doc_20260728_001.pdf"
    },
    {
      "docId": "doc_20260728_002",
      "fileName": "EN 1990.pdf",
      "minioPath": "eurocode/uploads/doc_20260728_002.pdf",
      "contextSummaryEnabled": false
    }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| contextSummaryEnabled | boolean | 否 | 批次默认是否做上下文增强，默认 `true`；单文件可覆盖 |
| files | object[] | 是 | 待解析列表，长度 **1～20** |
| files[].docId | string | 是 | 文档唯一标识（华科生成） |
| files[].fileName | string | 是 | 原始文件名（含扩展名）；引用展示优先用该值 |
| files[].minioPath | string | 是 | MinIO 路径，`bucket/key` |
| files[].contextSummaryEnabled | boolean | 否 | 覆盖批次默认 |

> **不再接受** v1 顶层单对象形态（`{ docId, fileName, minioPath }`）。请统一使用 `files[]`。

### 1.2 受理规则

| 场景 | 行为 | 该条 `status` |
|------|------|----------------|
| 参数合法的新任务 / 可重跑任务 | 写入解析选项并**入队** | `queued` 或 `processing` |
| 同一 `docId` 已在排队或解析中 | **不重复入队**，不中断原任务 | `already_processing` |
| 文档已 `success`，再次提交 | **允许**，覆盖重跑（清理并替换旧索引） | `queued` / `processing` |
| 文档上次 `failed`，再次提交 | 允许重新入队 | `queued` / `processing` |
| 同一请求内重复 `docId` | 仅首次入队；后续重复项拒绝 | `rejected`（`DUPLICATE_IN_REQUEST`） |
| 单条参数缺失 / 格式非法 | 该条不入队 | `rejected` |
| MinIO 当时不存在 | **仍可入队**；worker 执行时拉取失败 → 状态接口见 `failed` | 入队时为 `queued`/`processing` |
| `files` 为空或超过 20 | 整请求失败，全部不入队 | —（整批 `code=400`） |
| 系统排队已满（`used >= capacity`） | 整请求拒绝，**已在队列中的任务不受影响** | —（整批 `code=429`） |

**与队列容量的关系（给华科前端）**

- 单次最多传 **20** 个文件（接口硬上限）。
- 同时受队列剩余名额约束：建议先调 §2 查询 `remaining`，再决定本次提交数量。
- 建议：`本次 files.length ≤ min(20, remaining)`。
- 若 `remaining = 0`，请提示用户稍后再试，不要调用 parse。

### 1.3 响应 200

采用**逐文件结果**。`code=200` 表示请求已被处理；个别文件 `rejected` / `already_processing` 不改变整批业务码。

```json
{
  "code": 200,
  "results": [
    {
      "docId": "doc_20260728_001",
      "status": "queued",
      "message": "已加入解析队列"
    },
    {
      "docId": "doc_20260728_002",
      "status": "already_processing",
      "message": "该文档正在解析中，未重复入队"
    },
    {
      "docId": "doc_20260728_003",
      "status": "rejected",
      "message": "minioPath 不能为空",
      "error": {
        "type": "VALIDATION_ERROR",
        "detail": "files[2].minioPath is required"
      }
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| code | number | 整批入口码；请求体整体合法时为 `200` |
| results | object[] | 与请求 `files` 顺序对应（含重复项的 rejected 说明） |
| results[].docId | string | 文档 ID |
| results[].status | string | `queued` / `processing` / `already_processing` / `rejected` |
| results[].message | string | 人类可读说明 |
| results[].error | object | 仅 `rejected` 时可选；含 `type`、`detail` |

**`results[].status` 含义**

| status | 含义 |
|--------|------|
| `queued` | 已入队，等待 worker |
| `processing` | 已入队且可能即将/已经开始处理（客户端可统一当作「受理成功，去查 status」） |
| `already_processing` | 该 doc 已在队列或解析中，本次未重复入队 |
| `rejected` | 本条未入队（参数错误、请求内重复等） |

### 1.4 整批级错误码

| 响应体 `code` | 说明 |
|---------------|------|
| 400 | `files` 缺失、为空、超过 20，或 JSON 无法解析 |
| 429 | 解析队列已满（`used >= capacity`）；新请求拒绝，已入队不丢 |
| 503 | 任务队列或关键依赖不可用 |

> 单文档进度、成功/失败详情请继续调用现网 **`POST /api/v1/documents/status`** 轮询。  
> 排队中的文档在 status 接口中外部 `status` 仍为 `processing`，`stage` 可为 `pending`。

### 1.5 索引元数据（联调理解用）

| 键 | 来源 | 用途 |
|----|------|------|
| `source` | `docId` | 删除、过滤、引用关联 |
| `source_title` | `fileName` | 回答展示名 |

---

## 2. 查询解析队列容量

供华科在上传页展示「当前还可提交多少个解析任务」。

```
GET /api/v1/documents/parse-queue
```

无请求体、无查询参数。

### 2.1 响应 200

```json
{
  "code": 200,
  "capacity": 100,
  "used": 15,
  "remaining": 85,
  "active": 1,
  "queued": 14,
  "maxFilesPerRequest": 20
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| code | number | 成功为 `200` |
| capacity | number | 队列总容量：允许同时存在的**未完成**解析任务上限，默认 **100** |
| used | number | 当前占用数 = `active + queued`（仅未完成任务） |
| remaining | number | 剩余可新提交名额 = `max(capacity - used, 0)`。**华科提示「还能上传多少」优先用此字段** |
| active | number | 正在解析中的文档数（当前实现为 0 或 1，单 worker） |
| queued | number | 已入队、等待执行的文档数 |
| maxFilesPerRequest | number | 单次 `parse` 的 `files` 上限，固定 **20**（与队列容量独立） |

### 2.2 计数规则（重要）

| 文档状态 | 是否计入 `used` |
|----------|-----------------|
| 排队等待（pending） | ✅ 计入 → 体现在 `queued` |
| 正在解析（parsing … indexing） | ✅ 计入 → 体现在 `active` |
| 已成功（success / ready） | ❌ 不计入 |
| 已失败（failed / error） | ❌ 不计入 |
| 从未提交 | ❌ 不计入 |

因此：解析失败或成功后，名额会自动释放；对失败文档重新 `parse` 会再次占用 1 个名额。

### 2.3 华科侧推荐用法

```
1. 打开上传页 / 选文件前：GET /documents/parse-queue
2. 展示：还可提交 remaining 个（同时单次最多 maxFilesPerRequest 个）
3. 用户实际可选数量建议：
     allowCount = min(用户想传的数量, remaining, maxFilesPerRequest)
4. 上传 MinIO 后：POST /documents/parse（files.length ≤ allowCount）
5. 提交后再调一次 parse-queue 刷新展示（可选）
```

**并发说明（务必知晓）**

- 本接口返回的是**查询瞬间的快照**，不是名额预留。
- 若多用户/多请求同时查到 `remaining=10` 并同时提交，后到的请求仍可能收到 parse 的 `429`。
- 前端应：以 `remaining` 做提示与默认限制；若 parse 返回 `429`，提示「解析队列繁忙，请稍后重试」，并重新拉取 parse-queue。

### 2.4 错误码

| 响应体 `code` | 说明 |
|---------------|------|
| 503 | 任务管理器不可用（罕见） |

### 2.5 与两个「上限」的区别

| 上限 | 值 | 含义 |
|------|----|------|
| `maxFilesPerRequest` | 20 | **一次 HTTP 请求**里 `files` 最多几个 |
| `capacity` | 100 | 系统里**同时未完成**的解析任务最多几个 |
| `remaining` | 动态 | 现在还能再提交几个新任务进队 |

例：`remaining=5` 时，即使用户想一次传 20 个，也只应提交 5 个；等前面完成、`remaining` 回升后再传下一批。

---

## 3. 流式问答（SSE）

在华科传入的 **`docIds` 权限集合内**做检索与生成。

```
POST /api/v1/query/stream
Content-Type: application/json
```

### 3.1 请求体

```json
{
  "sessionId": "1001_abc123def456",
  "question": "EN 1992 中混凝土保护层最小厚度是多少？",
  "docIds": ["doc_20260728_001", "doc_20260728_002", "doc_20260728_010"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sessionId | string | 是 | 华科生成的会话 ID；本系统据此读 Redis 多轮历史 |
| question | string | 是 | 用户问题，上限 500 字符 |
| docIds | string[] | **是** | 本次允许检索的文档 ID，长度 **1～100**。由华科按知识库与权限计算后传入 |

**`docIds` 规则**

| 情况 | 行为 |
|------|------|
| 缺失或 `[]` | **`code=400`**，不进行全库检索 |
| 长度 > 100 | **`code=400`** |
| 含未索引 / 不存在的 id | 忽略无效项；若有效集合为空 → 仍返回问答流，但无可用证据（低置信/说明无依据），**绝不**回退全库 |
| 与知识库的关系 | 华科把「当前知识库 ∩ 用户权限」展开为 `docIds`；本系统**不接收 `kbId`** |

> **废弃** v1 字段 `domain`。本期请改用 `docIds`。

### 3.2 权限保证

- 主检索范围：`source ∈ docIds`。
- 父块扩展、交叉引用扩展：命中 `docIds` 外的内容**不得**进入可引用证据与 `done.sources`（可提及规范名称，但不贴出库外原文）。

### 3.3 SSE 事件流

```
event: progress
data: {"stage": "retrieving", "message": "正在检索相关规范..."}

event: reasoning
data: {"text": "让我分析一下这个问题..."}

event: chunk
data: {"text": "根据 EN 1992"}

event: chunk
data: {"text": "-1-1 第 4.4.1 条..."}

event: done
data: {
  "code": 200,
  "sources": [...],
  "relatedRefs": ["Table 4.1"],
  "confidence": "high",
  "questionType": "parameter",
  "answerMode": "standard",
  "title": "混凝土保护层最小厚度"
}

event: error
data: {"code": 503, "message": "LLM 服务暂时不可用"}
```

| 事件 | 说明 |
|------|------|
| `progress` | 处理阶段进度 |
| `reasoning` | 思考过程片段 |
| `chunk` | 回答正文片段（前端拼接为 Markdown） |
| `done` | 生成完成 |
| `error` | 错误，含业务 `code` |

### 3.4 `done` 主要字段

| 字段 | 类型 | 说明 |
|------|------|------|
| code | number | 成功为 `200` |
| sources | array | 引用依据列表（见下表） |
| relatedRefs | array | 提及但未作为主引用的交叉引用 |
| confidence | string | `high` / `medium` / `low` |
| questionType | string | 如 `rule` / `parameter` / `calculation` / `mechanism` |
| answerMode | string | 回答策略模式 |
| title | string \| null | 仅首轮对话可能返回会话标题；后续为 `null` |

**`sources[]`**

| 字段 | 类型 | 说明 |
|------|------|------|
| docId | string | 来源文档 ID（= 解析时的 `docId`） |
| elementType | string | `text` / `table` / `figure` / `formula` |
| title | string | 展示标题（优先 fileName 链路） |
| section | string | 章节路径 |
| page | string | PDF 页码 |
| clause | string | 条款号 |
| originalText | string | 英文原文片段 |
| locatorText | string | 定位辅助文本 |
| highlightText | string | 高亮文本 |
| translation | string | 原文中文翻译 |

### 3.5 错误码

| 响应体 `code` | 说明 |
|---------------|------|
| 400 | `question` 为空/超长；`docIds` 缺失、为空或超过 100 |
| 503 | LLM 或检索依赖不可用 |

错误可出现在 SSE `event: error` 中，形如：

```json
{ "code": 400, "message": "参数错误", "detail": "docIds 不能为空" }
```

---

## 4. 推荐联调时序

```
1. 华科 GET /api/v1/documents/parse-queue
     → 展示 remaining / maxFilesPerRequest
2. 华科上传 PDF → MinIO（bucket/key）
3. 华科 POST /api/v1/documents/parse
     { "files": [...] }   // length ≤ min(20, remaining)
4. 华科轮询 POST /api/v1/documents/status（现网接口）
     直到各文档 success / failed
5. （可选）再次 GET parse-queue 刷新「还可上传」
6. 用户在华科「知识库」中提问
7. 华科按权限展开 docIds（1～100）
8. 华科 POST /api/v1/query/stream
     { "sessionId", "question", "docIds" }
```

---

## 5. 接口对照（本期）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/documents/parse` | 批量解析入队；`files` 1～20；队列满返回 429 |
| GET | `/api/v1/documents/parse-queue` | 查询 `capacity/used/remaining`，供前端提示还能传多少 |
| POST | `/api/v1/query/stream` | 必填 `docIds` 集合过滤；废弃 `domain` |

---

## 6. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1 | 现网 | 单文件 parse；query 使用可选 `domain` |
| v2 | 2026-07-28 | 批量 parse（上限 20）；query 必填 `docIds`（上限 100） |
| v2 | 2026-07-28 | 新增 `GET /documents/parse-queue`；队列容量默认 100 |
