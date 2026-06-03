# 模块索引

## 已同步模块

- `data.glossary`: 运行时术语表，供查询理解层与术语接口使用
- `server.api.v1.glossary`: 热门问题、术语查询和首页引导项
- `server.api.v1.settings`: 前端 LLM 设置默认值接口
- `server.api.v1.query`: 问答入口，请求级合成运行时 LLM 配置
- `server.api.v1.sessions`: 会话恢复与 Redis-backed 用户会话摘要列表
- `server.api.v1.documents`: 文档解析、批量状态、批量删除与兼容处理端点
- `server.api.v1.sources`: 来源翻译外部端点与兼容接口
- `server.services.minio_storage`: MinIO 对象路径解析、PDF 上传与下载
- `server.agents.qa_agent`: OpenAI Agents SDK 问答 agent、对话历史压缩与工具事件流
- `server.agents.tools.retrieve`: agent `retrieve` 工具、grounded 拦截与检索 Observation 摘要
- `frontend.lib.auth`: 前端访问密码 token 的本地存储、过期判定与认证过期事件
- `frontend.lib.api`: 前端后端 API 封装，包含代理上传、流式问答和引用翻译请求
- `server.core.conversation`: Redis/内存会话状态管理、完整会话恢复与会话摘要枚举
- `server.core.retrieval`: 混合检索、去重聚合、重排序与原问题补召回
- `server.core.generation`: 回答生成、source 构造、流式 done 元数据
- `frontend.lib.session`: 前端当前会话轻量指针的本地持久化结构
- `frontend.hooks.useEuroQaDemo`: 前端工作台状态、LLM 设置加载与请求透传
- `frontend.components.Sidebar`: 左侧历史会话、文档区与热门问题入口
- `frontend.components.TopBar`: 顶部栏状态摘要与 LLM 设置入口
- `frontend.components.MainWorkspace`: 主回答区、引用来源和深度思考展示
- `frontend.components.EvidencePanel`: 来源面板展示原文、中文解释和文档预览
- `frontend.lib.pdfViewerPage`: PDF 阅读器页码夹紧、翻页和显示状态同步工具
