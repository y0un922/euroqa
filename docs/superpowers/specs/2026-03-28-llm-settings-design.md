# Euro_QA LLM 设置功能 — 设计文档

> Version: 1.0
> Date: 2026-03-28
> Status: Draft

## 1. 目标概述

### 1.1 背景

当前系统的 LLM 配置仅来自服务端静态 `ServerConfig`。这意味着：

- 前端用户无法直接切换 `base_url`、`model`
- `enable_thinking` 只能通过服务端配置生效
- 若用户希望临时使用自己的 API Key，只能改后端环境变量或源码配置

这与 Demo 场景下的快速试验需求不匹配，尤其是在需要切换 DeepSeek / Qwen / DashScope 兼容接口时。

### 1.2 本次目标

为 Demo 前后端增加一套可立即生效的 LLM 设置能力，覆盖以下 4 个字段：

- `api_key`
- `base_url`
- `model`
- `enable_thinking`

用户可以在前端页面中修改这些设置，并让它们在下一次提问时立即生效。

### 1.3 非目标

本次不包含以下范围：

- embedding / rerank 配置切换
- 温度、最大输出长度等生成参数
- 多套配置模板管理
- 服务端数据库持久化配置
- 多用户权限隔离

---

## 2. 设计原则

### 2.1 请求级生效，而非服务端全局改写

LLM 设置应作为“当前浏览器会话的运行时覆盖项”，随问答请求一起发送。后端按“请求覆盖值 > 服务端默认值”的顺序构造本次请求实际使用的配置。

这样可以避免：

- 一个用户修改设置影响所有其他用户
- API Key 变成服务端全局共享状态
- 切换模型需要重启后端

### 2.2 前端本地持久化

设置保存到浏览器 `localStorage`，与现有 Demo 会话持久化策略保持一致。刷新页面后仍保留，但仅对当前浏览器生效。

### 2.3 服务端默认值可见，但敏感值不可回显

前端首次加载时可读取服务端默认的：

- `base_url`
- `model`
- `enable_thinking`
- `api_key_configured`

其中 `api_key_configured` 只反映“服务端是否已配置 API Key”，不返回明文 Key。

---

## 3. 用户体验设计

### 3.1 设置入口

在顶部栏 `TopBar` 右侧新增一个 LLM 设置按钮，建议使用齿轮图标。点击后展开一个轻量面板或弹层，避免改变主工作区布局。

### 3.2 设置项

面板内包含以下字段：

1. `API Key`
   - 输入框，密码样式显示
   - 占位提示：留空则沿用服务端默认 Key
2. `Base URL`
   - 文本输入框
   - 默认显示服务端值或本地已保存值
3. `Model`
   - 文本输入框
   - 默认显示服务端值或本地已保存值
4. `Enable Thinking`
   - 开关控件
   - 控制后端是否尝试向支持 reasoning 的模型请求思考流

### 3.3 生效规则

- 用户点击“保存”后，本地设置立即更新
- 不强制自动重跑当前问答
- 下一次点击提问时，自动携带设置覆盖项
- 用户可点击“恢复默认”清除本地覆盖项，回退到服务端默认值

### 3.4 状态提示

面板中应明确区分：

- 当前显示的是“服务端默认值”还是“本地覆盖值”
- `API Key` 是否由服务端已配置兜底

不在顶部栏常驻展示完整模型串，避免信息噪音过大。

---

## 4. 前端设计

### 4.1 新增状态模型

前端需要新增一份 `LlmSettings` 类型，包含：

- `apiKey`
- `baseUrl`
- `model`
- `enableThinking`

同时区分两类来源：

- `serverDefaults`
- `localOverrides`

最终请求发送时由前端合成“有效设置”。

### 4.2 会话持久化

在现有 `frontend/src/lib/session.ts` 的持久化结构上扩展 `llmSettings` 字段，保存本地覆盖值。

建议规则：

- `apiKey` 允许为空字符串
- 若用户点击恢复默认，则移除本地覆盖并清空持久化中的该字段
- 老版本 session 数据需要平滑迁移，不得因缺少新字段而报错

### 4.3 API 客户端扩展

前端 `query()` 和 `queryStream()` 两条链路都要支持发送可选的 `llm` 对象：

```json
{
  "question": "什么是设计使用年限",
  "llm": {
    "api_key": "sk-xxx",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3.5-plus",
    "enable_thinking": true
  }
}
```

同时新增一个读取默认值的接口调用：

- `GET /api/v1/settings/llm`

### 4.4 UI 组件拆分

建议新增一个独立组件，例如：

- `frontend/src/components/LlmSettingsPanel.tsx`

职责：

- 展示服务端默认值
- 编辑本地覆盖值
- 保存 / 恢复默认
- 通知 `useEuroQaDemo` 更新状态

`TopBar` 只负责展示按钮与开关状态，不承载大量业务逻辑。

---

## 5. 后端设计

### 5.1 请求模型扩展

在 `QueryRequest` 中新增可选字段：

```json
{
  "llm": {
    "api_key": "string?",
    "base_url": "string?",
    "model": "string?",
    "enable_thinking": "boolean?"
  }
}
```

要求：

- 所有字段都可选
- 缺省时沿用 `ServerConfig`
- 空字符串视为“未覆盖”，避免把默认值错误覆盖成空

### 5.2 运行时配置合成

新增一个轻量的请求级配置合成函数，例如：

- 输入：全局 `ServerConfig` + 请求中的 `llm` 覆盖项
- 输出：本次问答实际使用的 `ServerConfig` 副本

生成层与查询理解层继续消费 `ServerConfig` 形态，不改动底层调用方式。这样改造范围最小。

### 5.3 默认值接口

新增接口：

`GET /api/v1/settings/llm`

返回：

```json
{
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-chat",
  "enable_thinking": true,
  "api_key_configured": false
}
```

约束：

- 不返回 `api_key` 明文
- 该接口只用于前端展示默认值和回退基线

### 5.4 问答链路接入点

`/query` 与 `/query/stream` 都要在进入 `analyze_query()` 之前完成配置合成，并将运行时配置透传给：

- `analyze_query()`
- `generate_answer()`
- `generate_answer_stream()`

检索层仍沿用全局依赖，无需接入此设置，因为本次仅调整 LLM 调用，不调整 embedding / rerank / 检索服务。

---

## 6. 安全与边界

### 6.1 API Key 处理

- 服务端默认 API Key 不回传给前端
- 前端本地输入的 API Key 仅保存在浏览器本地存储
- 后端只在本次请求上下文中使用该值，不做持久化

### 6.2 多用户影响范围

请求级覆盖保证不同用户、不同浏览器、不同标签页的设置互不污染。即使多个前端同时访问同一后端，也不会共享运行时覆盖值。

### 6.3 兼容性

- 旧版前端不发送 `llm` 字段时，后端行为保持不变
- 旧版本地 session 数据中没有 `llmSettings` 时，应平滑迁移
- 不支持 reasoning 的模型在 `enable_thinking=true` 时也应静默降级，不报错

---

## 7. 测试策略

### 7.1 后端

至少覆盖：

- `GET /api/v1/settings/llm` 返回默认值且不泄露 API Key
- `/query` 请求携带 `llm` 覆盖项时，`analyze_query()` / `generate_answer()` 使用覆盖后的配置
- `/query/stream` 请求携带 `llm` 覆盖项时，流式链路使用覆盖后的配置
- 空字符串覆盖值不会抹掉默认配置

### 7.2 前端

至少覆盖：

- 本地设置的加载与保存
- 旧 session 数据迁移
- `query()` 和 `queryStream()` 会携带 `llm` 覆盖项
- 恢复默认后，不再发送本地覆盖字段

### 7.3 手工验收

手工验证路径：

1. 打开页面，查看设置面板是否能显示服务端默认 `base_url/model`
2. 输入新的 `base_url/model` 并保存
3. 发起一次普通问答，请求应带上新设置
4. 切换为支持 reasoning 的模型并打开 `enable_thinking`
5. 重新提问，确认深度思考面板可继续正常工作
6. 点击恢复默认，再次提问，请求应回退到服务端默认值

---

## 8. 变更清单

### 8.1 后端

- 修改 `server/models/schemas.py`
- 修改 `server/api/v1/query.py`
- 修改 `server/config.py`（如需补充配置辅助方法）
- 修改 `server/deps.py`（如需提供设置默认值依赖）
- 新增或修改 `server/api/v1/*` 中的设置接口
- 补测试 `tests/server/test_api.py`

### 8.2 前端

- 修改 `frontend/src/lib/types.ts`
- 修改 `frontend/src/lib/api.ts`
- 修改 `frontend/src/lib/session.ts`
- 修改 `frontend/src/hooks/useEuroQaDemo.ts`
- 修改 `frontend/src/components/TopBar.tsx`
- 新增 `frontend/src/components/LlmSettingsPanel.tsx`
- 补测试 `frontend/src/lib/api.test.ts`
- 补测试 `frontend/src/lib/session.test.ts`

---

## 9. 推荐实施顺序

1. 先补后端请求模型与默认值接口
2. 再补前端设置状态与持久化
3. 接上 `/query` 和 `/query/stream` 的运行时覆盖
4. 最后补 UI 和自动化测试

该顺序可以先把“设置能生效”打通，再补展示层，减少联调不确定性。
