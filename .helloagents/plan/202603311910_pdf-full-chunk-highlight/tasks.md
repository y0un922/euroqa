# 任务清单: pdf-full-chunk-highlight

```yaml
@feature: pdf-full-chunk-highlight
@created: 2026-03-31
@status: pending
@mode: R3
```

<!-- LIVE_STATUS_BEGIN -->
状态: pending | 进度: 0/7 (0%) | 更新: 2026-03-31 19:12:00
当前: 方案设计已确认，待进入开发实施
<!-- LIVE_STATUS_END -->

## 进度概览

| 完成 | 失败 | 跳过 | 总数 |
|------|------|------|------|
| 0 | 0 | 0 | 7 |

---

## 任务列表

### 1. 后端 Source 建模与高亮文本生成

- [ ] 1.1 在 `server/models/schemas.py` 与 `frontend/src/lib/types.ts` 中新增 `highlight_text` 字段并同步相关类型/夹具 | depends_on: []
- [ ] 1.2 在 `server/core/generation.py` 中实现 `highlight_text` 生成逻辑，保留 `original_text` 为完整检索 chunk，并让 `locator_text` 退居兼容回退用途 | depends_on: [1.1]
- [ ] 1.3 在 `tests/server/test_generation.py` 与相关 API 测试中覆盖 `highlight_text` 语义、完整 `original_text` 保留和回退行为 | depends_on: [1.2]

### 2. 前端 PDF 完整段落高亮

- [ ] 2.1 在 `frontend/src/lib/pdfLocator.ts` 中将高亮算法从单个 text item 命中升级为整页 text item 序列匹配，输出整段命中范围与退化状态 | depends_on: [1.2]
- [ ] 2.2 在 `frontend/src/components/PdfEvidenceViewer.tsx` 中接入整段匹配结果，对完整段落进行高亮，并保留 `page_only/error` 退化 | depends_on: [2.1]
- [ ] 2.3 在 `frontend/src/lib/pdfLocator.test.ts` 中补充整段匹配、跨 item 命中和退化场景测试 | depends_on: [2.1]

### 3. 证据面板展示与联调验证

- [ ] 3.1 在 `frontend/src/components/EvidencePanel.tsx` 中继续展示完整 chunk，并把调试视图扩展为同时显示 `highlight_text`/长度信息 | depends_on: [1.1, 2.2]
- [ ] 3.2 运行前后端相关测试与 `pnpm build`，必要时同步更新 `.helloagents/CHANGELOG.md` 中的快速修改记录 | depends_on: [1.3, 2.3, 3.1]

---

## 执行日志

| 时间 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 2026-03-31 19:12 | 方案选择 | completed | 用户确认采用方案 A：双轨文本字段 + 整段序列高亮 |

---

## 执行备注

> 记录执行过程中的重要说明、决策变更、风险提示等
>
> - 当前已确认：`original_text` 继续承担“完整检索 chunk 展示”职责，不再直接作为 PDF 高亮主字段。
> - 当前已确认：完整高亮只承诺在单页连续文本场景稳定成立；多页或非连续块允许退化为 `page_only`。
