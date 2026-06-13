from __future__ import annotations

import argparse
import json
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx


REF_BLOCK_RE = re.compile(r"\[[^\]]*Ref-\d+[^\]]*\]")
REF_NUM_RE = re.compile(r"Ref-(\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export dataset QA answers and list every cited [Ref-N]."
    )
    parser.add_argument("--input-xlsx", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output-dir", default="outputs/dataset_answers")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser.parse_args()


def load_questions(path: Path) -> list[dict[str, Any]]:
    rows = read_xlsx_sheet(path, "questions")
    header = rows[0] if rows else {}
    column_names = {col: str(value).strip().lower() for col, value in header.items()}
    b_name = column_names.get("B", "")
    c_name = column_names.get("C", "")
    questions: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        question = row.get("A")
        if not question:
            continue
        level = row.get("B")
        category = row.get("C")
        comment = None
        if b_name == "comment" and not c_name:
            comment = row.get("B")
            level = None
            category = None
        questions.append(
            {
                "id": len(questions) + 1,
                "row_number": row_number,
                "question": str(question).strip(),
                "level": level,
                "category": category,
                "comment": comment,
            }
        )
    return questions


def read_xlsx_sheet(path: Path, sheet_name: str) -> list[dict[str, str]]:
    ns = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg_rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        shared_strings = read_shared_strings(archive, ns)
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_targets = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall("pkg_rel:Relationship", ns)
        }
        sheet_path = None
        for sheet in workbook.findall("main:sheets/main:sheet", ns):
            if sheet.attrib.get("name") == sheet_name:
                rel_id = sheet.attrib[f"{{{ns['rel']}}}id"]
                target = rel_targets[rel_id]
                sheet_path = f"xl/{target}" if not target.startswith("xl/") else target
                break
        if sheet_path is None:
            raise ValueError(f"Sheet not found: {sheet_name}")

        worksheet = ET.fromstring(archive.read(sheet_path))
        rows: list[dict[str, str]] = []
        for row in worksheet.findall("main:sheetData/main:row", ns):
            values: dict[str, str] = {}
            for cell in row.findall("main:c", ns):
                ref = cell.attrib.get("r", "")
                column = "".join(ch for ch in ref if ch.isalpha())
                value = read_cell_value(cell, shared_strings, ns)
                if value is not None:
                    values[column] = value
            rows.append(values)
        return rows


def read_shared_strings(archive: zipfile.ZipFile, ns: dict[str, str]) -> list[str]:
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root.findall("main:si", ns):
        parts = [node.text or "" for node in item.findall(".//main:t", ns)]
        values.append("".join(parts))
    return values


def read_cell_value(
    cell: ET.Element,
    shared_strings: list[str],
    ns: dict[str, str],
) -> str | None:
    value_node = cell.find("main:v", ns)
    inline_node = cell.find("main:is/main:t", ns)
    if inline_node is not None:
        return inline_node.text or ""
    if value_node is None:
        return None
    raw = value_node.text or ""
    if cell.attrib.get("t") == "s":
        return shared_strings[int(raw)]
    return raw


def decode_sse_payload(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def query_answer(
    client: httpx.Client,
    *,
    base_url: str,
    question: str,
    thinking: bool,
) -> dict[str, Any]:
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    progress_events: list[Any] = []
    done_payload: dict[str, Any] = {}
    error_payload: Any = None
    url = f"{base_url.rstrip('/')}/api/v1/query/stream"

    started = time.perf_counter()
    request_payload = {
        "question": question,
        "stream": True,
        "llm": {"enable_thinking": thinking},
    }
    with client.stream("POST", url, json=request_payload) as response:
        response.raise_for_status()
        event: str | None = None
        data_lines: list[str] = []
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
                data_lines = []
                continue
            if line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
                continue
            if line != "":
                continue

            raw_data = "\n".join(data_lines)
            payload = decode_sse_payload(raw_data)
            if event == "reasoning":
                if isinstance(payload, dict):
                    reasoning_parts.append(str(payload.get("text") or ""))
                elif payload is not None:
                    reasoning_parts.append(str(payload))
            elif event == "chunk":
                if isinstance(payload, dict):
                    answer_parts.append(str(payload.get("text") or ""))
                elif payload is not None:
                    answer_parts.append(str(payload))
            elif event == "progress":
                progress_events.append(payload)
            elif event == "error":
                error_payload = payload
            elif event == "done":
                done_payload = payload if isinstance(payload, dict) else {"raw": payload}
                break

    elapsed = round(time.perf_counter() - started, 3)
    if error_payload is not None and not done_payload:
        raise RuntimeError(f"stream error: {error_payload!r}")
    return {
        "answer": "".join(answer_parts).strip(),
        "reasoning": "".join(reasoning_parts).strip(),
        "elapsed_seconds": elapsed,
        "metadata": done_payload,
        "progress_events": progress_events,
    }


def simplify_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": source.get("file"),
        "display_title": source.get("display_title"),
        "document_id": source.get("document_id"),
        "section": source.get("section"),
        "page": source.get("page"),
        "clause": source.get("clause"),
        "title": source.get("title"),
        "locator_text": source.get("locator_text"),
        "highlight_text": source.get("highlight_text"),
        "original_text": source.get("original_text"),
    }


def cited_ref_numbers(answer: str) -> list[int]:
    seen: set[int] = set()
    refs: list[int] = []
    for block in REF_BLOCK_RE.finditer(answer or ""):
        for match in REF_NUM_RE.finditer(block.group(0)):
            ref_num = int(match.group(1))
            if ref_num not in seen:
                seen.add(ref_num)
                refs.append(ref_num)
    return refs


def write_json(path: Path, results: dict[str, Any]) -> None:
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, results: dict[str, Any]) -> None:
    lines: list[str] = [
        "# 层级分类问题集答案",
        "",
        f"- 生成时间: {results['generated_at']}",
        f"- 问题集: `{results['input_file']}`",
        f"- 系统接口: `{results['base_url']}/api/v1/query/stream`",
        f"- thinking: `{results['enable_thinking']}`",
        f"- 有效问题数: {len(results['items'])}",
        f"- 来源导出策略: `正文实际引用的全部 [Ref-N]，保留原编号`",
        "",
    ]
    for item in results["items"]:
        metadata = item.get("metadata") or {}
        sources = metadata.get("sources") or []
        answer = item.get("answer") or "（未生成答案正文）"
        refs = cited_ref_numbers(answer)
        missing_refs = [ref for ref in refs if ref < 1 or ref > len(sources)]
        unused_count = max(0, len(sources) - len(refs))

        lines.extend(
            [
                f"## {item['id']}. {item['question']}",
                "",
                f"- Excel 行号: {item['row_number']}",
                *(
                    [f"- 旧版导出 Excel 行号: {item.get('legacy_row_number')}"]
                    if item.get("legacy_row_number")
                    else []
                ),
                f"- 层级: {item.get('level') or ''} / {item.get('category') or ''}",
                f"- 甲方 comment: {item.get('comment') or ''}",
                f"- 置信度: {metadata.get('confidence') or ''}",
                f"- groundedness: {metadata.get('groundedness') or ''}",
                f"- 耗时: {item.get('elapsed_seconds')} 秒",
                f"- 来源总数: {len(sources)}",
                f"- 正文引用来源数: {len(refs)}",
                f"- 未在正文引用来源数: {unused_count}",
                "",
                "### 答案",
                "",
                answer,
                "",
                "### Thinking",
                "",
                item.get("reasoning")
                or (
                    metadata.get("thinking")
                    if isinstance(metadata.get("thinking"), str)
                    else ""
                )
                or "（未返回 thinking 内容）",
                "",
                "### 来源（正文实际引用）",
                "",
            ]
        )
        if not sources:
            lines.append("无")
        else:
            for ref_num in refs:
                if ref_num < 1 or ref_num > len(sources):
                    lines.append(f"- [Ref-{ref_num}] 缺失：metadata.sources 中不存在该编号")
                    continue
                source = sources[ref_num - 1]
                display = (
                    source.get("display_title")
                    or source.get("file")
                    or source.get("document_id")
                    or "未知文档"
                )
                page = source.get("page") or ""
                clause = source.get("clause") or ""
                locator = (
                    source.get("highlight_text")
                    or source.get("original_text")
                    or source.get("locator_text")
                    or ""
                )
                lines.append(
                    f"- [Ref-{ref_num}] {display}，页 {page}，条款 {clause}: {locator}"
                )
        if missing_refs:
            lines.extend(
                [
                    "",
                    "### 引用一致性警告",
                    "",
                    "- 正文存在 metadata.sources 中无法映射的引用: "
                    + ", ".join(f"[Ref-{ref}]" for ref in missing_refs),
                ]
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_xlsx = Path(args.input_xlsx)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"answers_{args.run_id}.json"
    md_path = output_dir / f"answers_{args.run_id}.md"

    questions = load_questions(input_xlsx)
    results: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(input_xlsx),
        "base_url": args.base_url.rstrip("/"),
        "enable_thinking": args.thinking,
        "source_export_policy": "cited_refs_only_keep_original_numbers",
        "items": [],
    }

    with httpx.Client(timeout=args.timeout) as client:
        for question in questions:
            print(
                f"[{question['id']}/{len(questions)}] {question['question']}",
                flush=True,
            )
            try:
                response = query_answer(
                    client,
                    base_url=args.base_url,
                    question=question["question"],
                    thinking=args.thinking,
                )
                metadata = response["metadata"]
                item = {
                    **question,
                    "answer": response["answer"],
                    "reasoning": response["reasoning"],
                    "elapsed_seconds": response["elapsed_seconds"],
                    "metadata": metadata,
                    "sources_summary": [
                        simplify_source(source)
                        for source in (metadata.get("sources") or [])
                        if isinstance(source, dict)
                    ],
                    "progress_events": response["progress_events"],
                    "error": None,
                }
            except Exception as exc:
                item = {
                    **question,
                    "answer": "",
                    "reasoning": "",
                    "elapsed_seconds": None,
                    "metadata": {},
                    "sources_summary": [],
                    "progress_events": [],
                    "error": repr(exc),
                }
            results["items"].append(item)
            write_json(json_path, results)
            write_markdown(md_path, results)

    print(f"JSON: {json_path}")
    print(f"MD: {md_path}")


if __name__ == "__main__":
    main()
