from __future__ import annotations

import json
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import httpx


INPUT_XLSX = Path("/Users/youngz/Downloads/(层级分类)问题集_20260518.xlsx")
BASE_URL = "http://127.0.0.1:18080"
OUTPUT_DIR = Path("outputs/dataset_answers")
RUN_ID = "20260527_215008_thinking"
JSON_PATH = OUTPUT_DIR / f"answers_{RUN_ID}.json"
MD_PATH = OUTPUT_DIR / f"answers_{RUN_ID}.md"
ENABLE_THINKING = True


def load_questions(path: Path) -> list[dict[str, Any]]:
    rows = read_xlsx_sheet(path, "questions")
    questions: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        question = row.get("A")
        if not question:
            continue
        questions.append(
            {
                "id": len(questions) + 1,
                "row_number": row_number,
                "question": str(question).strip(),
                "level": row.get("B"),
                "category": row.get("C"),
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


def query_answer(client: httpx.Client, question: str) -> dict[str, Any]:
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    progress_events: list[Any] = []
    done_payload: dict[str, Any] = {}
    url = f"{BASE_URL}/api/v1/query/stream"

    started = time.perf_counter()
    request_payload = {
        "question": question,
        "stream": True,
        "llm": {"enable_thinking": ENABLE_THINKING},
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
            elif event == "done":
                done_payload = payload if isinstance(payload, dict) else {"raw": payload}
                break

    elapsed = round(time.perf_counter() - started, 3)
    reasoning = "".join(reasoning_parts).strip()
    return {
        "answer": "".join(answer_parts).strip(),
        "reasoning": reasoning,
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


def write_json(results: dict[str, Any]) -> None:
    JSON_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(results: dict[str, Any]) -> None:
    lines: list[str] = [
        "# 层级分类问题集答案",
        "",
        f"- 生成时间: {results['generated_at']}",
        f"- 问题集: `{results['input_file']}`",
        f"- 系统接口: `{results['base_url']}/api/v1/query/stream`",
        f"- thinking: `{results['enable_thinking']}`",
        f"- 有效问题数: {len(results['items'])}",
        "",
    ]
    for item in results["items"]:
        metadata = item.get("metadata") or {}
        sources = metadata.get("sources") or []
        lines.extend(
            [
                f"## {item['id']}. {item['question']}",
                "",
                f"- Excel 行号: {item['row_number']}",
                f"- 层级: {item.get('level') or ''} / {item.get('category') or ''}",
                f"- 置信度: {metadata.get('confidence') or ''}",
                f"- groundedness: {metadata.get('groundedness') or ''}",
                f"- 耗时: {item.get('elapsed_seconds')} 秒",
                "",
                "### 答案",
                "",
                item.get("answer") or "（未生成答案正文）",
                "",
                "### Thinking",
                "",
                item.get("reasoning") or (metadata.get("thinking") if isinstance(metadata.get("thinking"), str) else "")
                or "（未返回 thinking 内容）",
                "",
                "### 来源",
                "",
            ]
        )
        if not sources:
            lines.append("无")
        else:
            for index, source in enumerate(sources[:8], start=1):
                display = source.get("display_title") or source.get("file") or source.get("document_id") or "未知文档"
                page = source.get("page") or ""
                clause = source.get("clause") or ""
                locator = source.get("locator_text") or source.get("highlight_text") or ""
                lines.append(f"- [{index}] {display}，页 {page}，条款 {clause}: {locator}")
        lines.append("")
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    questions = load_questions(INPUT_XLSX)
    results: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input_file": str(INPUT_XLSX),
        "base_url": BASE_URL,
        "enable_thinking": ENABLE_THINKING,
        "items": [],
    }

    with httpx.Client(timeout=600.0) as client:
        for question in questions:
            print(f"[{question['id']}/{len(questions)}] {question['question']}", flush=True)
            try:
                response = query_answer(client, question["question"])
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
            write_json(results)
            write_markdown(results)

    print(f"JSON: {JSON_PATH}")
    print(f"MD: {MD_PATH}")


if __name__ == "__main__":
    main()
