# PDF 引用高亮增强与证据面板重做 — 设计文档

> Version: 1.0
> Date: 2026-03-31
> Status: Draft
> Supersedes: 2026-03-31-pdf-citation-location-design.md (Section 6 高亮策略 + Section 4.4 查看组件)

## 1. 问题陈述

当前 PDF 引用定位系统存在三个核心缺陷：

1. **高亮精度低**：完全依赖文本匹配（PDF.js 文本层 vs MinerU 重构文本），命中率不稳定
2. **检索文本与高亮内容不匹配**：pipeline 中间的文本变形（公式提取、占位符插入、跨页截断）导致 `highlight_text` 和 PDF 原文差异显著
3. **面板布局差**：PDF 区域固定 340px 太小、信息层级混乱、调试区块堆叠挤占空间

## 2. 目标

### 2.1 本次目标

1. 将 MinerU `content_list.json` 中的 `bbox` 坐标从 pipeline 解析阶段传播到前端 Source
2. 前端 PDF 高亮从纯文本匹配改为 **bbox 坐标覆盖层为主、文本匹配为兜底**
3. 右侧证据面板重做布局：PDF 占据主要空间，元信息紧凑化，翻译区底部折叠

### 2.2 非目标

- 不重做 MinerU PDF 解析流程
- 不重建 Elasticsearch 索引结构（bbox 作为新字段追加，兼容旧数据）
- 不改主回答区或引用编号逻辑
- 不做跨页连续高亮（每个 source 只高亮其主 bbox 所在页）
- 不做精确到字符级的 PDF 文本层标注

---

## 3. Pipeline bbox 全链路传播

### 3.1 当前状态

MinerU 的 `content_list.json` 为每个内容块输出 `bbox: [x0, y0, x1, y1]`（归一化到 0-1000）和 `page_idx`（0-indexed）。EN1990 数据中已有 1609 条带 bbox 的记录。

但 pipeline 只在 `content_list.py` 中提取了 `page_idx` 和 `text` 用于 section-page 匹配，`bbox` 被完全丢弃。`DocumentNode`、`ChunkMetadata` 均无 bbox 字段。唯一使用 bbox 的地方是 `server/core/generation.py` 中 `_resolve_table_source_geometry()`——但它在查询时重新遍历 content_list 做回溯匹配，而非从 pipeline 数据直接获取。

### 3.2 改造方案

**原则：bbox 在 pipeline 阶段就绑定到节点，而不是查询时回溯。**

#### 3.2.1 `pipeline/content_list.py`

`ContentListEntry` 新增字段：

```python
@dataclass(frozen=True)
class ContentListEntry:
    index: int
    page_idx: int
    text: str
    text_level: int
    bbox: list[float] = field(default_factory=list)      # 新增
    element_type: str = ""                                 # 新增
```

`_normalize_content_list()` 提取时同步读取 `bbox` 和 `type`。

#### 3.2.2 `pipeline/structure.py`

`DocumentNode` 新增字段：

```python
@dataclass
class DocumentNode:
    ...
    bbox: list[float] = field(default_factory=list)
    bbox_page_idx: int = -1
```

在 `resolve_section_page_metadata()` 匹配 heading 时，将匹配到的 `ContentListEntry.bbox` 和 `page_idx` 回填到对应 `DocumentNode`。

对于非 heading 的 body 文本节点和特殊元素（table/formula/image），在 `_extract_special_elements()` 阶段，通过 content_list 的 `page_idx` 和 `element_type` 做就近匹配，将 bbox 绑定到子节点。

#### 3.2.3 `pipeline/chunk.py`（即 `ChunkMetadata`）

`server/models/schemas.py` 中的 `ChunkMetadata` 新增：

```python
class ChunkMetadata(BaseModel):
    ...
    bbox: list[float] = []
    bbox_page_idx: int = -1
```

chunk 构建时从 `DocumentNode` 继承 bbox。对于 parent chunk（多个子节点合并），取第一个有 bbox 的子节点的值。

#### 3.2.4 `pipeline/index.py`

ES mapping 新增 `bbox`（`float` array）和 `bbox_page_idx`（`integer`）字段。旧索引中无此字段的文档在查询时视为空数组，兼容不受影响。

#### 3.2.5 `server/core/generation.py`

`_build_sources_from_chunks()` 改为统一使用 `ChunkMetadata.bbox`：

```python
bbox = list(meta.bbox) if meta.bbox else []
resolved_page = str(meta.bbox_page_idx + 1) if meta.bbox_page_idx >= 0 else ""
```

移除 `_resolve_table_source_geometry()` 的运行时 content_list 遍历——该逻辑作为兜底保留（当 `meta.bbox` 为空且 `element_type == TABLE` 时才触发），但不再是主路径。

---

## 4. 高亮策略

### 4.1 双层高亮：bbox 覆盖层为主，文本匹配为兜底

#### 主路径：bbox 坐标覆盖层

当 `Source.bbox` 非空（4 个有效浮点数）时：

1. 根据 PDF 页面的实际渲染尺寸，将 MinerU 0-1000 坐标转换为百分比定位
2. 在 PDF `<Page>` 组件上叠加一个 `position: absolute` 的半透明高亮层
3. 高亮层使用 `pointer-events: none`，不阻碍用户与 PDF 文本层的交互

坐标换算：

```
left   = (x0 / 1000) * 100%
top    = (y0 / 1000) * 100%
width  = ((x1 - x0) / 1000) * 100%
height = ((y1 - y0) / 1000) * 100%
```

MinerU 使用左上角原点、Y 轴向下，与浏览器 CSS 定位一致，无需翻转。

#### 兜底路径：文本匹配

当 `Source.bbox` 为空时（旧数据或 pipeline 未覆盖的场景），回退到现有的 `pdfLocator.ts` 文本匹配逻辑。不修改也不删除现有文本匹配代码。

#### 定位状态

状态机保持不变：`idle` → `highlighted` | `page_only` | `error`。bbox 覆盖层定位成功时直接报 `highlighted`。

### 4.2 页码策略

当 `Source.bbox` 可用时，使用 `bbox_page_idx + 1` 作为 PDF 跳转页（bbox 对应的精确页），而非 chunk 的 `page_numbers[0]`（可能是 section 起始页）。

---

## 5. 前端布局重做

### 5.1 整体结构

右侧 `EvidencePanel` 从当前的多 section 纵向堆叠改为三层结构：

```
┌─────────────────────────────┐
│ 顶栏 (48px)                 │  元信息 + 定位状态 + 翻译开关
├─────────────────────────────┤
│                             │
│   PDF 查看器 (flex: 1)       │  占据所有剩余空间
│                             │
│                             │
├─────────────────────────────┤
│ 翻译条 (auto, 可折叠)        │  引用翻译结果
└─────────────────────────────┘
```

### 5.2 顶栏 (48px)

左侧：

- 面板标题 "证据溯源"（带图标）
- 文档名（monospace，如 `EN 1990:2002`）
- Clause（如 `§2.3`）
- 页码（如 `p.18`）
- 定位状态标签（已高亮 / 仅跳页 / 失败）

右侧：

- "翻译"文字标签 + toggle 开关

### 5.3 PDF 查看器

- 使用 `flex: 1` 占满顶栏和翻译条之间的全部空间
- 深灰背景（`#404040`）+ 白色 PDF 页面居中
- 底部浮动页码导航（半透明黑底，含上下翻页箭头）
- bbox 高亮覆盖层叠加在 PDF 页面上方

### 5.4 翻译条

- 紧贴底部，高度由内容决定
- 翻译开关关闭时：显示一行提示 "引用翻译已关闭"
- 翻译加载中时：显示 spinner + "正在生成…"
- 翻译完成时：显示翻译文本，支持 Markdown 渲染
- 翻译失败时：显示错误信息

### 5.5 调试信息

当前的 "定位文本对照" section（含 highlight_text / locator_text / original_text 三个 tab）从面板主视图中移除。改为：

- 在顶栏增加一个开发者调试图标（仅开发环境显示或通过 URL 参数启用）
- 点击后以 popover 或底部抽屉展开，不占用面板常规空间

### 5.6 移除的元素

- 当前的元信息详情卡片（文档/Clause/Page/定位状态的表格式展示）→ 合并到顶栏一行
- 当前的 "原文引用的其他标准" section → 保留但从主视图移到调试 popover
- 当前的 `h-[340px]` PDF 固定高度 → 改为 flex-1

---

## 6. 受影响的文件

### Pipeline

| 文件 | 改动 |
|------|------|
| `pipeline/content_list.py` | `ContentListEntry` 新增 `bbox`、`element_type` |
| `pipeline/structure.py` | `DocumentNode` 新增 `bbox`、`bbox_page_idx`；回填 bbox |
| `pipeline/chunk.py` | chunk 构建时继承 bbox |
| `pipeline/index.py` | ES mapping 新增 `bbox`、`bbox_page_idx` |

### Backend

| 文件 | 改动 |
|------|------|
| `server/models/schemas.py` | `ChunkMetadata` 新增 `bbox`、`bbox_page_idx` |
| `server/core/generation.py` | `_build_sources_from_chunks` 统一使用 metadata bbox |

### Frontend

| 文件 | 改动 |
|------|------|
| `frontend/src/components/EvidencePanel.tsx` | 布局重做：三层结构 |
| `frontend/src/components/PdfEvidenceViewer.tsx` | bbox 覆盖层为主、文本匹配为兜底 |
| `frontend/src/lib/pdfLocator.ts` | 新增 bbox → CSS 百分比换算工具函数 |
| `frontend/src/lib/evidenceDebug.ts` | 调试信息移到 popover |

### 测试

| 文件 | 改动 |
|------|------|
| `tests/pipeline/test_structure.py` | 验证 bbox 回填 |
| `tests/pipeline/test_chunk.py` | 验证 bbox 继承 |
| `tests/server/test_generation.py` | 验证 Source.bbox 来自 metadata |
| `frontend/src/lib/pdfLocator.test.ts` | 新增 bbox 换算测试 |

---

## 7. 兼容性

### 7.1 旧索引数据

已索引的文档不含 `bbox` 和 `bbox_page_idx` 字段。ES 查询时这些字段为空或缺失，`ChunkMetadata` 的默认值（`bbox=[]`、`bbox_page_idx=-1`）可安全处理。前端在 bbox 为空时自动回退到文本匹配，行为与改造前完全一致。

### 7.2 增量重建

要让旧文档获得 bbox 数据，需要重新运行 pipeline 的 structure + chunk + index 阶段。不需要重新运行 MinerU 解析——`content_list.json` 中已有 bbox。

### 7.3 前端向后兼容

后端 `Source.bbox` 已在 schema 中定义（`list[float]`，默认空列表），前端 `types.ts` 中也已有 `bbox?: number[]`。本次改动不新增前后端接口字段，只是使 bbox 从"只对 table 有值"变为"对所有 element type 都有值"。

---

## 8. 验收标准

### 8.1 高亮精度

- 对 text 类型 source：bbox 可用时，PDF 上显示坐标覆盖层高亮，状态为 `highlighted`
- 对 table 类型 source：行为与当前一致（bbox 覆盖层），但 bbox 改为从 metadata 直接获取
- bbox 缺失时：回退到文本匹配，行为与改造前一致
- 不出现高亮位置明显错误的情况（bbox 坐标换算正确）

### 8.2 面板布局

- PDF 查看器占据面板 80% 以上的可视空间
- 元信息浓缩到顶栏一行，不超过 48px
- 翻译区在底部，不挤占 PDF 空间
- 调试信息默认不可见，不占用空间

### 8.3 Pipeline 数据完整性

- 重新 index 后，ES 中 text/table/formula/image 类型的 chunk 均携带 bbox
- bbox 值与 content_list.json 中的对应条目一致
- 旧索引数据查询不报错，前端正常回退到文本匹配

---

## 9. 实施建议

按以下顺序推进：

1. **Pipeline 层**：content_list.py → structure.py → chunk.py → schemas.py → index.py
2. **后端层**：generation.py 统一使用 metadata bbox
3. **前端高亮**：PdfEvidenceViewer bbox 覆盖层 + pdfLocator bbox 换算
4. **前端布局**：EvidencePanel 三层重做
5. **重建索引**：对 EN1990 重新运行 structure + chunk + index
6. **端到端验证**：点击引用 → PDF 跳页 → bbox 高亮 → 翻译
