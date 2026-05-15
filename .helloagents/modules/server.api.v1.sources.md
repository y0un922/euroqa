# 模块: server.api.v1.sources

## 职责

- 提供来源原文翻译接口
- 向外部系统暴露按需翻译单条来源文本的能力

## 行为规范

- 保留既有 `/sources/translate` 兼容接口
- 新增 `/translate` 作为接口文档要求的外部端点
- 新端点接受 `text` 和可选 `context`，返回 `code` 和 `translation`
- `text` 为空时返回 400，翻译服务不可用时返回 503

## 依赖关系

- 依赖 `server.core.generation._fill_missing_source_translations()` 复用现有 LLM 翻译能力
- 依赖 `server.models.schemas.Source` 构造翻译输入
