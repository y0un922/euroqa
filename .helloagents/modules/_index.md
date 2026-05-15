# 模块索引

## 已同步模块

- `data.glossary`: 运行时术语表，供查询理解层与术语接口使用
- `server.api.v1.glossary`: 热门问题、术语查询和首页引导项
- `server.api.v1.settings`: 前端 LLM 设置默认值接口
- `server.api.v1.query`: 问答入口，请求级合成运行时 LLM 配置
- `server.api.v1.documents`: 文档解析、批量状态、批量删除与兼容处理端点
- `server.api.v1.sources`: 来源翻译外部端点与兼容接口
- `server.core.retrieval`: 混合检索、去重聚合、重排序与原问题补召回
- `server.core.generation`: 回答生成、source 构造、流式 done 元数据
- `frontend.lib.session`: 前端当前会话与历史会话的本地持久化结构
- `frontend.hooks.useEuroQaDemo`: 前端工作台状态、LLM 设置加载与请求透传
- `frontend.components.Sidebar`: 左侧历史会话、文档区与热门问题入口
- `frontend.components.TopBar`: 顶部栏状态摘要与 LLM 设置入口
- `frontend.components.MainWorkspace`: 主回答区、引用来源和深度思考展示
- `frontend.components.EvidencePanel`: 来源面板展示原文、中文解释和文档预览
- `frontend.lib.pdfViewerPage`: PDF 阅读器页码夹紧、翻页和显示状态同步工具
