import type { Source } from "./types";
import { hasUsablePdfBbox } from "./pdfLocator.ts";

export type EvidenceDebugField = {
  contentClassName: string;
  description: string;
  label: string;
  length: number;
  panelClassName: string;
  sectionKey: EvidenceDebugSectionKey;
  title: string;
  value: string;
};

export type EvidenceDebugSectionKey =
  | "bbox"
  | "chunk"
  | "element"
  | "highlight"
  | "locator";

type EvidenceDebugFieldConfig = {
  contentClassName: string;
  description: string;
  label: EvidenceDebugField["label"];
  panelClassName: string;
  sectionKey: EvidenceDebugField["sectionKey"];
  title: string;
  value: string;
};

function createEvidenceDebugField({
  contentClassName,
  description,
  label,
  panelClassName,
  sectionKey,
  title,
  value
}: EvidenceDebugFieldConfig): EvidenceDebugField {
  return {
    contentClassName,
    description,
    label,
    length: value.length,
    panelClassName,
    sectionKey,
    title,
    value
  };
}

export function buildEvidenceDebugFields(
  source: Pick<
    Source,
    "original_text" | "locator_text" | "highlight_text" | "element_type" | "bbox"
  >
): EvidenceDebugField[] {
  const chunk = source.original_text.trim();
  const highlight = source.highlight_text?.trim() ?? "";
  const locator = source.locator_text?.trim() ?? "";
  const elementType = source.element_type?.trim() ?? "text";
  const fields: EvidenceDebugField[] = [
    createEvidenceDebugField({
      contentClassName: "max-h-[160px]",
      description: "检索命中的原始 chunk。",
      label: "Chunk",
      panelClassName: "border-cyan-200 bg-cyan-50/40",
      sectionKey: "chunk",
      title: "PDF 原文",
      value: chunk || "未提供"
    })
  ];

  if (elementType !== "text") {
    fields.push(
      createEvidenceDebugField({
        contentClassName: "max-h-[96px]",
        description: "当前引用元素类型。",
        label: "Element",
        panelClassName: "border-stone-200 bg-white",
        sectionKey: "element",
        title: "Element 类型",
        value: elementType
      })
    );
  }

  if (hasUsablePdfBbox(source.bbox)) {
    const bboxValue = source.bbox.join(", ");
    fields.push(
      createEvidenceDebugField({
        contentClassName: "max-h-[96px]",
        description: "表格或块级元素的页内坐标。",
        label: "BBox",
        panelClassName: "border-stone-200 bg-white",
        sectionKey: "bbox",
        title: "BBox 坐标",
        value: bboxValue
      })
    );
  }

  if (elementType !== "table" && highlight && highlight !== chunk) {
    fields.push(
      createEvidenceDebugField({
        contentClassName: "max-h-[128px]",
        description: "PDF 高亮实际使用的文本。",
        label: "Highlight",
        panelClassName: "border-emerald-200 bg-emerald-50/40",
        sectionKey: "highlight",
        title: "Highlight 文本",
        value: highlight
      })
    );
  }

  if (locator && locator !== chunk && locator !== highlight) {
    fields.push(
      createEvidenceDebugField({
        contentClassName: "max-h-[128px]",
        description: "高亮失败时的定位回退文本。",
        label: "Locator",
        panelClassName: "border-amber-200 bg-amber-50/40",
        sectionKey: "locator",
        title: "Locator 文本",
        value: locator
      })
    );
  }

  return fields;
}

export function getDefaultEvidenceDebugSectionKey(
  fields: EvidenceDebugField[]
): EvidenceDebugSectionKey | null {
  return fields[0]?.sectionKey ?? null;
}

export function resolveActiveEvidenceDebugField(
  fields: EvidenceDebugField[],
  sectionKey: EvidenceDebugSectionKey | null | undefined
): EvidenceDebugField | null {
  if (fields.length === 0) {
    return null;
  }

  if (!sectionKey) {
    return fields[0];
  }

  return fields.find((field) => field.sectionKey === sectionKey) ?? fields[0];
}
