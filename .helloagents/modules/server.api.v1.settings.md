# 模块: server.api.v1.settings

## 职责

- 向前端暴露只读的 LLM 默认配置
- 屏蔽服务端明文 `api_key`

## 行为规范

- `GET /api/v1/settings/llm` 只返回 `base_url`、`model`、`enable_thinking` 和 `api_key_configured`。
- `api_key_configured` 仅表示服务端是否已配置 Key，绝不返回明文值。
- 该接口用于前端设置面板展示默认值与回退基线，不承担写入职责。

## 依赖关系

- 依赖 `server.deps.get_config` 提供当前 `ServerConfig`
- 依赖 `server.models.schemas.LlmSettingsResponse` 约束返回结构
