# 模块: server.api.v1.glossary

## 职责

- 提供 `/api/v1/glossary` 术语查询接口
- 提供 `/api/v1/suggest` 首页热门问题、领域和问法选项

## 行为规范

- `/api/v1/suggest` 的 `hot_questions` 必须优先选用当前已加载知识范围内可直接回答的问题，避免跨规范或依赖缺失文档的问题。
- 当系统当前仅演示 `EN 1992-1-1:2004` 单文档时，热门问题应聚焦混凝土材料、荷载分项系数、收缩徐变、钢筋特性、环境暴露等级、保护层、结构分析、板与截面设计假定等混凝土结构核心问答。
- 首页题库允许保留用户手工整理的问题顺序；当前题库中如存在重复或明显笔误，应优先保留语义正确的版本。
- `domains` 应与当前实际演示文档保持一致；单文档场景下不再返回整套 Eurocode 域列表，避免前端消费到过期范围。
- `/api/v1/glossary` 只做基于运行时术语表的简单过滤，不引入额外重写或推理逻辑。

## 依赖关系

- 依赖 `server.deps.get_glossary()` 加载运行时术语表
- 依赖 `server.models.schemas.GlossaryEntry` 约束 `/api/v1/glossary` 返回结构
- 被前端 `getSuggestions()` 和术语面板初始化流程消费
