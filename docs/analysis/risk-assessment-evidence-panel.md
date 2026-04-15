# PDF 证据面板优化 — 风险评估

## 视觉设计问题 (10 项)

| # | 问题 | 严重度 | 位置 |
|---|---|---|---|
| V1 | 双 ShieldCheck 图标, 标题栏浪费 56px 空间 | 中 | EvidencePanel.tsx:93-94,114 |
| V2 | 元数据栏 9px 字体, 信息密度过高, 不符合 WCAG | 高 | EvidencePanel.tsx:112-150 |
| V3 | PDF 背景 bg-neutral-600 过暗, 与浅色 UI 不协调 | 中 | EvidencePanel.tsx:153 |
| V4 | "Loading PDF..." 英文提示, 无骨架屏 | 低 | PdfEvidenceViewer.tsx:110 |
| V5 | 翻译区高度不稳定, 导致 PDF 区域抖动 | 高 | EvidencePanel.tsx:182-213 |
| V6 | 空状态图标过大, 文案排版僵硬 | 低 | EvidencePanel.tsx:216-223 |
| V7 | bbox 叠加层 25% 透明青色遮挡文字, 无过渡动画 | 中 | PdfEvidenceViewer.tsx:192-196 |
| V8 | xl 以下完全隐藏, 无抽屉回退 | 中 | evidencePanelLayout.ts:3-10 |
| V9 | mark 使用浏览器默认黄色, 与青色品牌色冲突 | 低 | PdfEvidenceViewer.tsx:3 |
| V10 | toggle 无 hover/focus-visible 状态 | 低 | EvidencePanel.tsx:134-148 |

## 匹配失败模式 (27 项, 按优先级排序)

### 高优先级 (高频 + 高影响)

| ID | 阶段 | 问题 | 频率 |
|---|---|---|---|
| FM-9 | pdfLocator | `isStrongHighlightCandidate` 阈值过高, 短条款体被拒绝 → page_only | 高 |
| FM-21 | pipeline | 纯子标题的节使用标题 bbox, 非内容位置 | 高 |
| FM-22 | pipeline | 父 chunk bbox 只取第一个子 chunk, 常定位到错误位置 | 高 |
| FM-6 | citations | 页码硬过滤, 跨页 chunk 的第二页引用被淘汰 | 中 |
| FM-27 | UX | 无滚动到高亮行为, 高亮在视口外用户以为没找到 | 高 |
| FM-5 | citations | 标准 ID 回退选错文档部件(EN 1997 vs EN 1997-2) | 中 |

### 中优先级

| ID | 阶段 | 问题 | 频率 |
|---|---|---|---|
| FM-16 | generation | LaTeX/Markdown 标记残留在 highlight_text 中 | 中 |
| FM-12 | render | 1-based PDF 页 vs 文档页码偏移 | 中 |
| FM-8 | pdfLocator | 连字符在独立 span 中时不触发合并 | 中 |
| FM-10 | pdfLocator | findBestContainedWindow 不处理短 highlight 在长 item 中的情况 | 中 |
| FM-13 | render | bbox 模式不验证叠加层是否在正确页面 | 中 |
| FM-17 | generation | 无标题表格 bbox 评分 < 5 被丢弃 | 中 |
| FM-23 | pipeline | 特殊元素回退到节区 bbox, 位置偏移 | 中 |
| FM-3 | citations | 无文件前缀的附录引用不被 regex 匹配 | 中 |
| FM-15 | generation | locator_text 240 字符截断可能在非区分位置 | 中低 |

### 低优先级

| ID | 阶段 | 问题 | 频率 |
|---|---|---|---|
| FM-1 | citations | 非 `|`/`·` 分隔符导致文件匹配失败 | 低 |
| FM-2 | citations | 子条款字母后缀 `(1)a` 未剥离 | 低 |
| FM-4 | citations | 多条款评分平局按数组索引决定 | 低 |
| FM-7 | citations | 非 EN 裸括号引用被静默丢弃 | 低 |
| FM-11 | pdfLocator | 非标准 Unicode 连字符未归一化 | 低 |
| FM-14 | render | bbox 叠加和文本高亮同时渲染无协调 | 低 |
| FM-18 | generation | document_id 不匹配 → 错误 PDF URL | 低(但致命) |
| FM-19 | retrieval | 单 chunk 获取失败静默跳过 | 低 |
| FM-20 | pipeline | 标题级别不匹配 → bbox=[] | 中 |
| FM-24 | pipeline | MinerU 坐标范围变化 → 全部 bbox 被拒 | 低(回归风险) |
| FM-25 | render | getTextSuccess / renderTextLayerSuccess 竞态 | 低 |
| FM-26 | render | itemIndex 跨重渲染过期 | 低 |

## 架构风险

| # | 风险 | 严重度 | 缓解方案 |
|---|---|---|---|
| R1 | useEuroQaDemo 630 行 god-hook, 15 状态切片 | 极高 | 提取 usePdfEvidencePanel 子 hook |
| R2 | PdfEvidenceViewer 5 值 key 导致全量 remount | 高 | key 仅含 fileUrl+page, 高亮作为后渲染效果 |
| R3 | evidencePanelLayout.test.ts 硬编码宽度断言 | 高 | 改为语义断言 |
| R4 | 无浏览器端渲染测试 | 高 | 后续可加 Playwright |
| R5 | react-pdf v9 Worker URL 模块级绑定 | 中 | 不拆分 lazy chunk |
| R6 | EvidencePanel 无本地状态, 新功能只能加到 god-hook | 中 | 建立状态边界 |
| R7 | xl 以下面板完全隐藏 | 中 | 考虑抽屉模式 |
| R8 | AnimatePresence 包裹整个内容区, 切换引用时 PDF 全量重载 | 中 | 拆分动画范围 |
| R9 | sync-conflict 残留文件 | 低 | 删除 |

## 安全修改边界

**可自由修改** (仅视觉, 不破坏逻辑):
- EvidencePanel.tsx 内部 CSS 类
- 三层布局结构
- pdfLocator.ts 内部逻辑(保持 22 个测试通过)

**需协调修改** (跨文件):
- EvidencePanel 新增 prop → App.tsx + useEuroQaDemo
- PdfEvidenceViewer prop 接口 → EvidencePanel + pdfLocator
- evidencePanelLayout 尺寸 → 同步更新测试

**高危操作** (需完整回归):
- Page key 组成 (PdfEvidenceViewer:125)
- AnimatePresence key (EvidencePanel)
- buildReferenceRecords ID 方案 (api.ts)
