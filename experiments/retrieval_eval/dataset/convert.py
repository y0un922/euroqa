"""Convert golden_dataset_reviewed.xlsx → test_questions_v2.json.

数据源：
- 「修订版基线建议」表：编号 / 推荐检索章节 / 推荐回答要点 / 注意事项（金标主源）
- 「逐题审查」表：审查等级 → review_bucket
- 「golden_dataset」表（原始）：问题、关键概念（注意：第3列「应检索到的点-章节」未审查，仅放 notes.raw_sections）

输出：v2 JSON，每题含 expected_documents:[{doc, sections, objects}]、expected_sections (flat)、
expected_keywords、expected_concepts、expected_answer_points、expected_formulas、review_bucket、notes。

用法：
    uv run python -m experiments.retrieval_eval.dataset.convert \\
        --input golden_dataset_reviewed.xlsx \\
        --output experiments/retrieval_eval/dataset/test_questions_v2.json
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import openpyxl

# 让脚本既能 python -m 也能 python <path> 运行
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from experiments.retrieval_eval.dataset.schema import (  # noqa: E402
    ExpectedDoc,
    QuestionV2,
    save_questions,
)

# ----------------------------------------------------------------------
# 解析正则
# ----------------------------------------------------------------------

# 文档前缀：EN1992 / EN 1992-1-1 / EN206-1 / DG_EN1992
DOC_RE = re.compile(r"\b(EN\s*\d{4}(?:-\d+(?:-\d+)?)?|DG_EN\d{4})", re.IGNORECASE)

# Section: §<num>[(sub-ref)]，可能带 P 后缀；可能是范围 §x.x-§y.y 或 §x.x-y.y
SECTION_RE = re.compile(
    r"§\s*"                                              # §
    r"(\d+(?:\.\d+)*"                                    # 主章节号
    r"(?:\([^)]+\))?P?)"                                 # 可选 (子号)P
    r"(?:\s*-\s*§?\s*(\d+(?:\.\d+)*(?:\([^)]+\))?P?))?"  # 可选 range 终点
)

# 裸数字章节（用于 "5.4-5.8" 这种已知前面有 § 上下文的范围；本项目数据中
# range 一般是 §...-§...，所以 fallback 较少触发）
BARE_SECTION_RANGE_RE = re.compile(r"(\d+(?:\.\d+)*)\s*-\s*(\d+(?:\.\d+)*)")

# 对象：Table / Tables / Annex / Figure / Eq / Ch
OBJECT_RE = re.compile(
    r"(Tables?\s+[\w.]+(?:N|R)?(?:\s*[、,，]\s*[\w.]+(?:N|R)?)*"
    r"|Annex\s+[A-Z]\d*"
    r"|Figure\s+[\w.]+"
    r"|Eq\([^)]+\)(?:\s*-\s*\([^)]+\))?"
    r"|Ch\s*\d+)",
    re.IGNORECASE,
)


def _normalize_doc(doc: str) -> str:
    """规范化文档名：去空格，统一大小写到 EN/DG 习惯。"""
    s = re.sub(r"\s+", "", doc).upper()
    s = s.replace("DG_EN", "DG_EN")  # already upper
    return s


def _strip_subref(s: str) -> str:
    """5.3.1(4)P -> 5.3.1，去掉 (...) 与尾部 P。"""
    s = re.sub(r"\([^)]+\)", "", s)
    if s.endswith("P"):
        s = s[:-1]
    return s.strip().rstrip(".")


def _expand_section_range(start: str, end: str) -> list[str]:
    """展开如 4.4.1.1 ~ 4.4.1.3 → [4.4.1.1, 4.4.1.2, 4.4.1.3]，或 5.4 ~ 5.8。"""
    start = _strip_subref(start)
    end = _strip_subref(end)
    sp = start.split(".")
    ep = end.split(".")
    if len(sp) != len(ep):
        # 不同层级，无法稳健展开，返回首尾两个
        return [start, end]
    try:
        s_last = int(sp[-1])
        e_last = int(ep[-1])
        if e_last < s_last:
            return [start, end]
        prefix = ".".join(sp[:-1])
        items = [str(i) for i in range(s_last, e_last + 1)]
        return [f"{prefix}.{i}" if prefix else i for i in items]
    except ValueError:
        return [start, end]


def _parse_objects_in_token(token: str) -> list[str]:
    """从 token 抽取对象，处理 Tables A、B、C 这种合并写法。"""
    out: list[str] = []
    for m in OBJECT_RE.finditer(token):
        raw = m.group(1).strip()
        # Tables A、B、C → ["Table A", "Table B", "Table C"]
        m_tables = re.match(r"Tables?\s+(.+)", raw, re.IGNORECASE)
        if m_tables and re.search(r"[、,，]", m_tables.group(1)):
            ids = re.split(r"\s*[、,，]\s*", m_tables.group(1))
            for tid in ids:
                tid = tid.strip().rstrip(".")
                if tid:
                    out.append(f"Table {tid}")
        else:
            # 标准化：Tables → Table（单复数归一化）
            norm = re.sub(r"^Tables\b", "Table", raw, flags=re.IGNORECASE)
            out.append(norm.strip())
    return out


def parse_section_field(text: str, default_doc: str = "EN1992") -> list[ExpectedDoc]:
    """主解析函数：把「推荐检索章节」字段解析成 list[ExpectedDoc]。

    格式范例：
        EN1992 §2.4.2.4/Table 2.1N；§2.4.2.2；§2.4.3；EN1990 §6.4、Annex A1
        EN1992 §4.4.1.1-§4.4.1.3；Tables 4.2、4.3N、4.4N、4.5N
        EN1992 §6.1(2)P；§3.1.7
        EN1992 §5.10.3；DG_EN1992 Ch5
    """
    if not text:
        return []
    segments = re.split(r"[;；]", text)
    docs: dict[str, ExpectedDoc] = {}
    current_doc = None

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue

        # 检测文档前缀；若有则更新当前 doc 上下文
        m = DOC_RE.search(seg)
        if m:
            current_doc = _normalize_doc(m.group(1))
            # 去掉 segment 中的文档前缀文本，避免后续误匹配
            seg = (seg[: m.start()] + seg[m.end():]).strip()
        doc_key = current_doc or default_doc
        if doc_key not in docs:
            docs[doc_key] = ExpectedDoc(doc=doc_key)

        # 抽 sections
        for sm in SECTION_RE.finditer(seg):
            start_raw = sm.group(1)
            end_raw = sm.group(2)
            if end_raw:
                for s in _expand_section_range(start_raw, end_raw):
                    if s and s not in docs[doc_key].sections:
                        docs[doc_key].sections.append(s)
            else:
                s = _strip_subref(start_raw)
                if s and s not in docs[doc_key].sections:
                    docs[doc_key].sections.append(s)

        # 抽 objects
        for obj in _parse_objects_in_token(seg):
            if obj not in docs[doc_key].objects:
                docs[doc_key].objects.append(obj)

    return list(docs.values())


# ----------------------------------------------------------------------
# 分类与桶
# ----------------------------------------------------------------------

REVIEW_BUCKETS = {"通过", "小幅修改", "中等修改", "重大修改"}


def infer_category(question: str, num_docs: int, num_sections: int) -> str:
    """基于问题文本与命中范围推导 category：
    - exact_ref: 问题里有 §x.x 或 Table x.x 这种精确引用
    - broad: 多文档或 sections 数 ≥ 4
    - parameter_lookup: 含"是多少 / 取值 / 计算公式"
    - reasoning: 含"如何 / 怎么 / 步骤 / 计算"
    - concept: 其它
    """
    if re.search(r"§\s*\d+\.\d+|\bTable\s+\d|\bAnnex\s+[A-Z]", question, re.IGNORECASE):
        return "exact_ref"
    if num_docs > 1 or num_sections >= 4:
        return "broad"
    if re.search(r"(是多少|取值|多少|限值)", question):
        return "parameter_lookup"
    if re.search(r"(如何|怎么|步骤|计算)", question):
        return "reasoning"
    return "concept"


def split_concepts(raw: str) -> list[str]:
    """按 bullet / 换行 / 顿号拆分关键概念。"""
    if not raw:
        return []
    items = []
    for chunk in re.split(r"[\n•·]+", raw):
        chunk = chunk.strip(" •·\t、，,；;")
        if chunk:
            items.append(chunk)
    return items


def derive_keywords(concepts: list[str], answer_points: list[str]) -> list[str]:
    """从概念与回答要点提取关键词（保留中英文短语，去除冗长解释）。"""
    kws: list[str] = []
    seen: set[str] = set()
    for source in (concepts, answer_points):
        for c in source:
            # 取冒号/破折号前部分作为短语
            head = re.split(r"[：:—\-]", c, maxsplit=1)[0].strip()
            if not head or len(head) > 30:
                continue
            if head not in seen:
                kws.append(head)
                seen.add(head)
    return kws[:20]


# ----------------------------------------------------------------------
# Sheet 读取
# ----------------------------------------------------------------------

def _read_review_buckets(wb) -> dict[int, str]:
    """从「逐题审查」读 id -> review_bucket。"""
    if "逐题审查" not in wb.sheetnames:
        return {}
    ws = wb["逐题审查"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        qid = row[0]
        bucket = row[2]
        if isinstance(qid, int) and isinstance(bucket, str) and bucket in REVIEW_BUCKETS:
            out[qid] = bucket
    return out


def _read_originals(wb) -> dict[int, dict]:
    """从「golden_dataset」读 id -> {question, raw_sections, concepts, answer_points, formulas}。"""
    ws = wb["golden_dataset"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        qid, question, raw_sections, concepts, answer_pts, formulas = row[:6]
        if isinstance(qid, int):
            out[qid] = {
                "question": question or "",
                "raw_sections": raw_sections or "",
                "concepts_text": concepts or "",
                "answer_points_text": answer_pts or "",
                "formulas_text": formulas or "",
            }
    return out


def _read_revised(wb) -> dict[int, dict]:
    """从「修订版基线建议」读 id -> {sections_field, answer_points, notes}。"""
    ws = wb["修订版基线建议"]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        qid, sections, answer_pts, notes = row[:4]
        if isinstance(qid, int):
            out[qid] = {
                "sections_field": sections or "",
                "revised_answer_points": answer_pts or "",
                "revision_note": notes or "",
            }
    return out


# ----------------------------------------------------------------------
# 主转换
# ----------------------------------------------------------------------

def convert(xlsx_path: Path) -> list[QuestionV2]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    originals = _read_originals(wb)
    revised = _read_revised(wb)
    buckets = _read_review_buckets(wb)

    questions: list[QuestionV2] = []
    for qid in sorted(revised.keys()):
        orig = originals.get(qid, {})
        rev = revised[qid]

        expected_docs = parse_section_field(rev["sections_field"], default_doc="EN1992")
        flat_sections = [s for d in expected_docs for s in d.sections]

        concepts = split_concepts(orig.get("concepts_text", ""))
        answer_points = split_concepts(rev.get("revised_answer_points", ""))
        formulas = split_concepts(orig.get("formulas_text", ""))
        keywords = derive_keywords(concepts, answer_points)

        category = infer_category(
            orig.get("question", ""), len(expected_docs), len(flat_sections)
        )

        q = QuestionV2(
            id=f"Q{qid:02d}",
            question=orig.get("question", ""),
            category=category,
            review_bucket=buckets.get(qid, "未审查"),
            expected_documents=expected_docs,
            expected_sections=flat_sections,
            expected_keywords=keywords,
            expected_concepts=concepts,
            expected_answer_points=answer_points,
            expected_formulas=formulas,
            must_not_include=[],
            notes={
                "raw_sections_field": rev["sections_field"],
                "raw_sections_original_unreviewed": orig.get("raw_sections", ""),
                "revision_note": rev.get("revision_note", ""),
                "original_answer_points": orig.get("answer_points_text", ""),
            },
        )
        questions.append(q)

    return questions


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert golden_dataset xlsx to v2 json.")
    parser.add_argument("--input", type=Path, default=Path("golden_dataset_reviewed.xlsx"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/retrieval_eval/dataset/test_questions_v2.json"),
    )
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Input xlsx not found: {args.input}")

    questions = convert(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_questions(questions, args.output)

    print(f"✓ Converted {len(questions)} questions → {args.output}")
    # 打印一个抽样以便人工核对
    print("\nSample (Q01):")
    q = questions[0]
    print(f"  id={q.id}  category={q.category}  review_bucket={q.review_bucket}")
    for d in q.expected_documents:
        print(f"  doc={d.doc}  sections={d.sections}  objects={d.objects}")


if __name__ == "__main__":
    main()
