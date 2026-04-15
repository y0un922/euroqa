"""检索召回评测脚本。

用法:
    uv run python tests/eval/eval_retrieval.py [--top-k 8] [--config-override KEY=VALUE ...]

需要 Milvus 和 Elasticsearch 正常运行。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import structlog

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.config import ServerConfig
from server.core.query_understanding import analyze_query
from server.core.retrieval import HybridRetriever

logger = structlog.get_logger()

EVAL_DIR = Path(__file__).parent
QUESTIONS_PATH = EVAL_DIR / "test_questions.json"


def _section_matches(chunk_section_path: list[str], clause_ids: list[str], expected: str) -> bool:
    """判断 chunk 的 section_path 或 clause_ids 是否匹配期望的 section 编号。"""
    # clause_ids 精确匹配
    for cid in clause_ids:
        if expected in cid or cid.startswith(expected):
            return True

    # section_path 模糊匹配（section_path 可能包含 "6.2 Shear" 这类格式）
    for segment in chunk_section_path:
        if expected in segment:
            return True

    return False


def _keyword_matches(content: str, embedding_text: str, keywords: list[str]) -> list[str]:
    """返回在 chunk content 或 embedding_text 中命中的关键词列表。"""
    combined = (content + " " + embedding_text).lower()
    return [kw for kw in keywords if kw.lower() in combined]


def _document_matches(source: str, expected_document: str | None) -> bool:
    """判断文档名是否与期望文档宽松匹配。"""
    if not expected_document:
        return True
    normalized_source = source.lower().replace(" ", "")
    normalized_expected = expected_document.lower().replace(" ", "")
    return normalized_expected in normalized_source or normalized_source in normalized_expected


def _anchor_phrase_matches(content: str, anchor_phrases: list[str]) -> list[str]:
    """返回在 chunk content 中命中的 anchor phrase。"""
    content_lower = content.lower()
    return [phrase for phrase in anchor_phrases if phrase.lower() in content_lower]


def _must_not_include_hits(chunks: list[Any], forbidden: list[str]) -> list[str]:
    """检查 top-k 结果中出现的禁止项。"""
    if not forbidden:
        return []
    combined = " ".join(
        " ".join(
            [
                chunk.content,
                chunk.embedding_text,
                chunk.metadata.source,
                chunk.metadata.source_title,
                " ".join(chunk.metadata.section_path),
                " ".join(chunk.metadata.clause_ids),
            ]
        ).lower()
        for chunk in chunks
    )
    return [term for term in forbidden if term.lower() in combined]


def _predicted_mode(analysis: Any, result: Any) -> str:
    """根据 query understanding + retrieval groundedness 推导最终模式。"""
    answer_mode = getattr(analysis, "answer_mode", None)
    answer_mode_value = getattr(answer_mode, "value", answer_mode)
    groundedness = getattr(result, "groundedness", None)

    if answer_mode_value == "exact" and groundedness == "grounded":
        return "exact"
    if answer_mode_value == "exact" and groundedness == "exact_not_grounded":
        return "exact_not_grounded"
    return "open"


def _normalize_ref_label(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _resolved_ref_labels(result: Any) -> set[str]:
    labels: set[str] = set()
    for label in getattr(result, "resolved_refs", []) or []:
        if isinstance(label, str) and label.strip():
            labels.add(_normalize_ref_label(label))

    for chunk in getattr(result, "ref_chunks", []) or []:
        object_label = getattr(chunk.metadata, "object_label", "")
        if object_label:
            labels.add(_normalize_ref_label(object_label))
        for clause_id in chunk.metadata.clause_ids:
            if clause_id:
                labels.add(_normalize_ref_label(clause_id))
    return labels


def _direct_ref_hits(result: Any, expected_direct_refs: list[str]) -> list[str]:
    """返回成功解析的直接引用对象标签。"""
    resolved = _resolved_ref_labels(result)
    hits: list[str] = []
    for ref in expected_direct_refs:
        if _normalize_ref_label(ref) in resolved:
            hits.append(ref)
    return hits


def _reference_closure_satisfied(result: Any, expected_direct_refs: list[str]) -> bool:
    """判断 exact cross-ref 题是否真正形成证据闭环。"""
    if getattr(result, "groundedness", None) != "grounded":
        return False

    unresolved = {
        _normalize_ref_label(label)
        for label in getattr(result, "unresolved_refs", []) or []
        if isinstance(label, str) and label.strip()
    }
    expected = {_normalize_ref_label(label) for label in expected_direct_refs}
    if expected & unresolved:
        return False
    return expected.issubset(_resolved_ref_labels(result))


def _noise_intrusion_rate(forbidden_hits: list[str], forbidden: list[str]) -> float | None:
    """返回 forbidden terms 在 top-k 中的侵入比例。"""
    if not forbidden:
        return None
    return len(forbidden_hits) / len(forbidden)


async def evaluate(
    top_k: int = 8,
    config_overrides: dict[str, str] | None = None,
) -> dict:
    """执行完整评测，返回结果摘要。"""
    # 加载配置
    config = ServerConfig()
    if config_overrides:
        data = config.model_dump()
        for key, value in config_overrides.items():
            if key in data:
                # 尝试类型转换
                original_type = type(data[key])
                if original_type == int:
                    data[key] = int(value)
                elif original_type == float:
                    data[key] = float(value)
                elif original_type == bool:
                    data[key] = value.lower() in ("true", "1", "yes")
                else:
                    data[key] = value
        config = ServerConfig(**data)

    # 加载词汇表
    glossary_path = Path(config.glossary_path)
    if glossary_path.exists():
        raw = json.loads(glossary_path.read_text(encoding="utf-8"))
        glossary: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, str):
                glossary[key] = value
            elif isinstance(value, dict) and "en" in value:
                glossary[key] = value["en"]
    else:
        glossary = {}

    # 加载测试问题
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    # 初始化检索器
    retriever = HybridRetriever(config)

    results = []
    total_section_recall = 0.0
    total_keyword_recall = 0.0
    total_anchor_hit_rate = 0.0
    anchor_hit_rate_measured_questions = 0
    grounded_mode_hits = 0
    grounded_mode_accuracy_measured_questions = 0
    total_direct_ref_resolution_rate = 0.0
    direct_ref_resolution_measured_questions = 0
    reference_closure_hits = 0
    reference_closure_measured_questions = 0
    total_noise_intrusion_rate = 0.0
    noise_intrusion_measured_questions = 0
    successful_questions = 0

    print(f"\n{'='*70}")
    print(f"检索召回评测 | top_k={top_k} | vector_top_k={config.vector_top_k} "
          f"| bm25_top_k={config.bm25_top_k} | rerank_top_n={config.rerank_top_n}")
    print(f"{'='*70}\n")

    try:
        for q in questions:
            qid = q["id"]
            question = q["question"]
            expected_sections = q.get("expected_sections", [])
            expected_keywords = q.get("expected_keywords", [])
            expected_mode = q.get("expected_mode")
            expected_document = q.get("expected_document")
            expected_anchor_phrases = q.get("expected_anchor_phrases", [])
            expected_direct_refs = q.get("expected_direct_refs", [])
            expected_reference_closure = q.get("expected_reference_closure")
            must_not_include = q.get("must_not_include", [])

            try:
                analysis = await analyze_query(question, glossary, config)
                filters = analysis.filters

                result = await retriever.retrieve(
                    queries=analysis.expanded_queries,
                    original_query=analysis.original_question,
                    filters=filters,
                    answer_mode=analysis.answer_mode.value if analysis.answer_mode else None,
                    intent_label=analysis.intent_label,
                    target_hint=analysis.target_hint,
                    requested_objects=getattr(analysis, "requested_objects", []),
                )
            except Exception as exc:
                logger.warning("eval_question_failed", question_id=qid, exc_info=True)
                print(f"[ERROR] {qid}: {question}")
                print(f"  原因: {type(exc).__name__}: {exc}")
                print("  说明: 服务不可用或评测依赖未就绪，本题跳过。\n")
                results.append({
                    "id": qid,
                    "question": question,
                    "category": q["category"],
                    "error": f"{type(exc).__name__}: {exc}",
                })
                continue

            successful_questions += 1
            chunks = result.chunks[:top_k]
            scores = result.scores[:top_k]

            hit_sections: set[str] = set()
            for chunk in chunks:
                for exp_sec in expected_sections:
                    if _section_matches(
                        chunk.metadata.section_path,
                        chunk.metadata.clause_ids,
                        exp_sec,
                    ):
                        hit_sections.add(exp_sec)

            section_recall = len(hit_sections) / len(expected_sections) if expected_sections else 1.0

            all_hit_keywords: set[str] = set()
            for chunk in chunks:
                hits = _keyword_matches(chunk.content, chunk.embedding_text, expected_keywords)
                all_hit_keywords.update(hits)

            keyword_recall = len(all_hit_keywords) / len(expected_keywords) if expected_keywords else 1.0

            all_hit_anchor_phrases: set[str] = set()
            for chunk in chunks:
                all_hit_anchor_phrases.update(_anchor_phrase_matches(chunk.content, expected_anchor_phrases))
            anchor_hit_rate = None
            if expected_anchor_phrases:
                anchor_hit_rate = len(all_hit_anchor_phrases) / len(expected_anchor_phrases)
                total_anchor_hit_rate += anchor_hit_rate
                anchor_hit_rate_measured_questions += 1

            document_hit = any(
                _document_matches(chunk.metadata.source, expected_document)
                for chunk in chunks
            ) if expected_document else True
            predicted_mode = _predicted_mode(analysis, result)
            grounded_mode_match = None
            if expected_mode is not None:
                grounded_mode_match = predicted_mode == expected_mode
                grounded_mode_hits += 1 if grounded_mode_match else 0
                grounded_mode_accuracy_measured_questions += 1

            forbidden_hits = _must_not_include_hits(chunks, must_not_include)
            direct_ref_hits = _direct_ref_hits(result, expected_direct_refs)
            direct_ref_resolution_rate = None
            if expected_direct_refs:
                direct_ref_resolution_rate = len(direct_ref_hits) / len(expected_direct_refs)
                total_direct_ref_resolution_rate += direct_ref_resolution_rate
                direct_ref_resolution_measured_questions += 1

            reference_closure_ok = None
            if expected_reference_closure is not None:
                reference_closure_ok = _reference_closure_satisfied(
                    result,
                    expected_direct_refs,
                )
                reference_closure_hits += 1 if reference_closure_ok == expected_reference_closure else 0
                reference_closure_measured_questions += 1

            noise_intrusion_rate = _noise_intrusion_rate(forbidden_hits, must_not_include)
            if noise_intrusion_rate is not None:
                total_noise_intrusion_rate += noise_intrusion_rate
                noise_intrusion_measured_questions += 1

            total_section_recall += section_recall
            total_keyword_recall += keyword_recall

            status = "PASS" if section_recall >= 0.5 else "FAIL"
            print(f"[{status}] {qid}: {question}")
            print(f"  改写: {analysis.rewritten_query}")
            print(f"  routing: answer_mode={getattr(getattr(analysis, 'answer_mode', None), 'value', None)} | "
                  f"intent_label={getattr(analysis, 'intent_label', None)} | "
                  f"predicted_mode={predicted_mode} | groundedness={getattr(result, 'groundedness', None)}")
            print(f"  过滤: {filters}")
            print(f"  section_recall: {section_recall:.2f} ({len(hit_sections)}/{len(expected_sections)})")
            print(f"    命中: {sorted(hit_sections)}")
            print(f"    未中: {sorted(set(expected_sections) - hit_sections)}")
            print(f"  keyword_recall: {keyword_recall:.2f} ({len(all_hit_keywords)}/{len(expected_keywords)})")
            if anchor_hit_rate is None:
                print("  anchor_hit_rate: not_applicable（样例未声明 expected_anchor_phrases）")
            else:
                print(f"  anchor_hit_rate: {anchor_hit_rate:.2f} ({len(all_hit_anchor_phrases)}/{len(expected_anchor_phrases)})")
            print(f"  document_hit: {document_hit}")
            if grounded_mode_match is None:
                print("  grounded_mode_match: not_applicable（样例未声明 expected_mode）")
            else:
                print(f"  grounded_mode_match: {grounded_mode_match}")
            if direct_ref_resolution_rate is None:
                print("  direct_ref_resolution_rate: not_applicable（样例未声明 expected_direct_refs）")
            else:
                print(
                    f"  direct_ref_resolution_rate: {direct_ref_resolution_rate:.2f} "
                    f"({len(direct_ref_hits)}/{len(expected_direct_refs)})"
                )
            if reference_closure_ok is None:
                print("  reference_closure: not_applicable（样例未声明 expected_reference_closure）")
            else:
                print(f"  reference_closure: {reference_closure_ok}")
            if forbidden_hits:
                print(f"  must_not_include 命中: {forbidden_hits}")
            if noise_intrusion_rate is not None:
                print(f"  noise_intrusion_rate: {noise_intrusion_rate:.2f}")
            if scores:
                print(f"  rerank_scores: [{', '.join(f'{s:.3f}' for s in scores[:5])}{'...' if len(scores) > 5 else ''}]")
            print(f"  检索到的 sections:")
            for i, chunk in enumerate(chunks):
                sec = " > ".join(chunk.metadata.section_path)
                clauses = ", ".join(chunk.metadata.clause_ids[:3])
                score = scores[i] if i < len(scores) else 0.0
                print(f"    [{i+1}] score={score:.3f} | {sec} | clause={clauses} | type={chunk.metadata.element_type.value}")
            print()

            results.append({
                "id": qid,
                "question": question,
                "category": q["category"],
                "rewritten_query": analysis.rewritten_query,
                "filters": filters,
                "expected_mode": expected_mode,
                "predicted_mode": predicted_mode,
                "groundedness": getattr(result, "groundedness", None),
                "document_hit": document_hit,
                "section_recall": section_recall,
                "keyword_recall": keyword_recall,
                "anchor_hit_rate": anchor_hit_rate,
                "grounded_mode_match": grounded_mode_match,
                "direct_ref_hits": direct_ref_hits,
                "direct_ref_resolution_rate": direct_ref_resolution_rate,
                "reference_closure": reference_closure_ok,
                "resolved_refs": getattr(result, "resolved_refs", None),
                "unresolved_refs": getattr(result, "unresolved_refs", None),
                "noise_intrusion_rate": noise_intrusion_rate,
                "hit_sections": sorted(hit_sections),
                "missed_sections": sorted(set(expected_sections) - hit_sections),
                "hit_keywords": sorted(all_hit_keywords),
                "hit_anchor_phrases": sorted(all_hit_anchor_phrases),
                "must_not_include_hits": forbidden_hits,
                "top_scores": scores[:5],
                "chunk_count": len(chunks),
                "notes": q.get("notes"),
            })
    finally:
        try:
            await retriever.close()
        except Exception:
            logger.warning("eval_retriever_close_failed", exc_info=True)

    # 汇总
    n = len(questions)
    measured_n = successful_questions
    avg_section_recall = total_section_recall / measured_n if measured_n else 0
    avg_keyword_recall = total_keyword_recall / measured_n if measured_n else 0
    avg_anchor_hit_rate = (
        total_anchor_hit_rate / anchor_hit_rate_measured_questions
        if anchor_hit_rate_measured_questions else None
    )
    pass_count = sum(1 for r in results if r.get("section_recall", 0.0) >= 0.5)
    grounded_mode_accuracy = (
        grounded_mode_hits / grounded_mode_accuracy_measured_questions
        if grounded_mode_accuracy_measured_questions else None
    )
    direct_ref_resolution_rate = (
        total_direct_ref_resolution_rate / direct_ref_resolution_measured_questions
        if direct_ref_resolution_measured_questions else None
    )
    reference_closure_rate = (
        reference_closure_hits / reference_closure_measured_questions
        if reference_closure_measured_questions else None
    )
    avg_noise_intrusion_rate = (
        total_noise_intrusion_rate / noise_intrusion_measured_questions
        if noise_intrusion_measured_questions else None
    )

    summary = {
        "config": {
            "vector_top_k": config.vector_top_k,
            "bm25_top_k": config.bm25_top_k,
            "rerank_top_n": config.rerank_top_n,
            "eval_top_k": top_k,
        },
        "metrics": {
            "avg_section_recall": round(avg_section_recall, 4),
            "avg_keyword_recall": round(avg_keyword_recall, 4),
            "anchor_hit_rate": round(avg_anchor_hit_rate, 4) if avg_anchor_hit_rate is not None else None,
            "anchor_hit_rate_measured_questions": anchor_hit_rate_measured_questions,
            "grounded_mode_accuracy": round(grounded_mode_accuracy, 4) if grounded_mode_accuracy is not None else None,
            "grounded_mode_accuracy_measured_questions": grounded_mode_accuracy_measured_questions,
            "direct_ref_resolution_rate": (
                round(direct_ref_resolution_rate, 4)
                if direct_ref_resolution_rate is not None else None
            ),
            "direct_ref_resolution_measured_questions": direct_ref_resolution_measured_questions,
            "reference_closure_rate": (
                round(reference_closure_rate, 4)
                if reference_closure_rate is not None else None
            ),
            "reference_closure_measured_questions": reference_closure_measured_questions,
            "noise_intrusion_rate": (
                round(avg_noise_intrusion_rate, 4)
                if avg_noise_intrusion_rate is not None else None
            ),
            "noise_intrusion_measured_questions": noise_intrusion_measured_questions,
            "over_answer_rate": None,
            "over_answer_rate_note": "placeholder: 当前脚本仅评估 retrieval/routing，不调用 generation，无法真实计算 over-answer_rate。",
            "pass_rate": round(pass_count / n, 4) if n else 0,
            "pass_count": pass_count,
            "total": n,
            "measured_questions": measured_n,
        },
        "per_question": results,
    }

    print(f"{'='*70}")
    print(f"汇总:")
    print(f"  平均 section_recall@{top_k}: {avg_section_recall:.4f}")
    print(f"  平均 keyword_recall@{top_k}: {avg_keyword_recall:.4f}")
    if avg_anchor_hit_rate is None:
        print(f"  平均 anchor_hit_rate@{top_k}: not_applicable（无样例声明 expected_anchor_phrases）")
    else:
        print(f"  平均 anchor_hit_rate@{top_k}: {avg_anchor_hit_rate:.4f} "
              f"(measured={anchor_hit_rate_measured_questions})")
    if grounded_mode_accuracy is None:
        print("  grounded_mode_accuracy: not_applicable（无样例声明 expected_mode）")
    else:
        print(f"  grounded_mode_accuracy: {grounded_mode_accuracy:.4f} "
              f"(measured={grounded_mode_accuracy_measured_questions})")
    if direct_ref_resolution_rate is None:
        print("  direct_ref_resolution_rate: not_applicable（无样例声明 expected_direct_refs）")
    else:
        print(
            f"  direct_ref_resolution_rate: {direct_ref_resolution_rate:.4f} "
            f"(measured={direct_ref_resolution_measured_questions})"
        )
    if reference_closure_rate is None:
        print("  reference_closure_rate: not_applicable（无样例声明 expected_reference_closure）")
    else:
        print(
            f"  reference_closure_rate: {reference_closure_rate:.4f} "
            f"(measured={reference_closure_measured_questions})"
        )
    if avg_noise_intrusion_rate is None:
        print("  noise_intrusion_rate: not_applicable（无样例声明 must_not_include）")
    else:
        print(
            f"  noise_intrusion_rate: {avg_noise_intrusion_rate:.4f} "
            f"(measured={noise_intrusion_measured_questions})"
        )
    print("  over_answer_rate: placeholder（当前脚本未实现 generation 级评测）")
    print(f"  通过率 (section_recall >= 0.5): {pass_count}/{n} ({pass_count/n*100:.1f}%)")
    print(f"{'='*70}\n")

    # 保存结果
    output_path = EVAL_DIR / "eval_results.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"详细结果已保存到: {output_path}")

    return summary


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="检索召回评测")
    parser.add_argument("--top-k", type=int, default=8, help="评测时取 top-k 个 chunk")
    parser.add_argument("--config-override", nargs="*", default=[], help="配置覆盖 KEY=VALUE")
    args = parser.parse_args()

    overrides = {}
    for item in args.config_override:
        if "=" in item:
            key, value = item.split("=", 1)
            overrides[key] = value

    asyncio.run(evaluate(top_k=args.top_k, config_overrides=overrides or None))


if __name__ == "__main__":
    main()
