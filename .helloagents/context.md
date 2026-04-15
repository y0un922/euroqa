# 项目上下文

## 基本信息

- 项目目标：围绕 Eurocode 文档提供检索、问答、来源溯源与前端演示能力。
- 主要运行形态：FastAPI 后端 + Vite/React 前端演示界面。

## 技术上下文

- 后端：Python，Pydantic，FastAPI，OpenAI-compatible LLM client
- 检索：Milvus 向量检索 + Elasticsearch BM25 + rerank
- 前端：React 19，TypeScript，Vite，Tailwind 风格体系

## 当前约束

- 工作区当前为脏状态，开发时只能在本次改动范围内增量修改。
- 前端来源面板已经具备 `source.translation` 展示位，优先从后端补齐数据，不新增前端翻译逻辑。
- 流式和非流式接口都需要对 `Source.translation` 保持一致行为。

## 最近一次同步

- 2026-03-27：补齐来源面板所依赖的 `Source.translation` 数据链路。
