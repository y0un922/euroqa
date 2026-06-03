# 模块: server.logging_config

## 职责

- 配置后端 structlog 处理器链。
- 统一 JSON 日志和本地控制台日志的时间戳、日志级别、上下文和异常格式。

## 行为规范

- 后端日志 `timestamp` 使用 `Asia/Shanghai` 时区，ISO 8601 格式中必须带 `+08:00` 偏移。
- 日志时区仅影响后台日志输出，不改变业务接口、Redis 会话、文档状态等数据 payload 的 UTC 时间戳。
- JSON 日志和控制台日志共用同一套 timestamp processor。

## 依赖关系

- 被 `server.main` 在应用启动时调用。
- 依赖 Python 标准库 `zoneinfo.ZoneInfo` 提供 `Asia/Shanghai` 时区。
