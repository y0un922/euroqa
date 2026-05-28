# 模块: frontend.lib.auth

## 职责

- 管理浏览器端访问密码 token 的读取、写入和清理
- 在前端启动认证判断时识别过期或损坏的本地 token
- 派发 `euroqa:auth-expired` 事件，通知应用回到登录状态

## 行为规范

- token 存储键为 `euroqa_auth_token`，当前使用 `localStorage` 持久化
- `isAuthenticated()` 不能只判断 token 是否存在；必须校验 token payload 中的 `exp` 是否仍有效
- 过期、格式损坏或无法解析的本地 token 应立即清理，并返回未认证状态
- 服务端签名、密钥轮换等无法在前端完全验证的失败场景，继续由受保护 API 的 401 响应兜底清理
- 读取浏览器存储时应容忍不可用或抛错的 `localStorage` 环境，不能阻断前端初始化

## 依赖关系

- 被 `frontend/src/App.tsx` 用于启动时判断是否进入登录页
- 被 `frontend/src/lib/api.ts` 用于附加 bearer token，并在 401 时清理 token、派发认证过期事件
