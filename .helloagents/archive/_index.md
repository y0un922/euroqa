# 方案归档索引

> 通过此文件快速查找历史方案
> 历史年份: [2024](_index-2024.md) | [2023](_index-2023.md) | ...

## 快速索引（当前年份）

| 时间戳 | 名称 | 类型 | 涉及模块 | 决策 | 结果 |
|--------|------|------|---------|------|------|
| 202604282221 | pdf-page-number-sync-fix | implementation | frontend.components.EvidencePanel, frontend.lib.pdfViewerPage | pdf-page-number-sync-fix#D001 | ✅完成 |
| 202604282002 | thinking-panel-collapse-fix | implementation | frontend.components.MainWorkspace | thinking-panel-collapse-fix#D001 | ✅完成 |
| 202604191218 | layout-hot-questions-session-history | implementation | frontend.components.Sidebar, frontend.hooks.useEuroQaDemo, frontend.lib.session, server.api.v1.glossary | layout-hot-questions-session-history#D001,#D002 | ✅完成 |
| 202604112241 | remove-chat-history | implementation | server.api.v1.query, frontend.hooks.useEuroQaDemo, frontend.components.Sidebar | remove-chat-history#D001 | ✅完成 |
| 202604112032 | glossary-json-from-xlsx | implementation | data.glossary | glossary-json-from-xlsx#D001 | ✅完成 |
| 202604112019 | glossary-xlsx-runtime-backfill | implementation | external glossary, data.glossary | glossary-xlsx-runtime-backfill#D001 | ✅完成 |
| 202604012034 | frontend-en1992-copy-refresh | - | - | - | ✅完成 |
| 202603281812 | citation-anchor-ui | - | - | - | ✅完成 |
| 202603271903 | glossary-sync-from-xlsx | implementation | data.glossary | glossary-sync-from-xlsx#D001 | ✅完成 |
| 202603271755 | thinking-panel-evidence-markdown | implementation | generation, workspace, evidence | thinking-panel-evidence-markdown#D001,#D002 | ✅完成 |
| 202603271643 | source-translation-panel | - | - | - | ✅完成 |

## 按月归档

### 2026-04
- [202604282221_pdf-page-number-sync-fix](./2026-04/202604282221_pdf-page-number-sync-fix/) - 修复右侧 PDF 翻页后页码显示不同步
- [202604282002_thinking-panel-collapse-fix](./2026-04/202604282002_thinking-panel-collapse-fix/) - 修复流式生成中深度思考面板无法手动折叠
- [202604191218_layout-hot-questions-session-history](./2026-04/202604191218_layout-hot-questions-session-history/) - 左栏移除术语预览并恢复本地历史会话归档/查看
- [202604112241_remove-chat-history](./2026-04/202604112241_remove-chat-history/) - 删除前后端 history 记忆与侧边栏最近提问
- [202604112032_glossary-json-from-xlsx](./2026-04/202604112032_glossary-json-from-xlsx/) - 按 xlsx 直接重建运行时术语表 JSON
- [202604112019_glossary-xlsx-runtime-backfill](./2026-04/202604112019_glossary-xlsx-runtime-backfill/) - 回填外部术语库中缺失的运行时术语

### 2026-03
- [202603271903_glossary-sync-from-xlsx](./2026-03/202603271903_glossary-sync-from-xlsx/) - 从 Excel 同步更新运行时术语表
- [202603271755_thinking-panel-evidence-markdown](./2026-03/202603271755_thinking-panel-evidence-markdown/) - 深度思考折叠面板与证据译文 Markdown 渲染
- [202603271643_source-translation-panel](./2026-03/202603271643_source-translation-panel/) - 来源面板补齐中文解释

## 结果状态说明
- ✅ 完成
- ⚠️ 部分完成
- ❌ 失败/中止
- ⏸ 未执行
- 🔄 已回滚
- 📄 概述
