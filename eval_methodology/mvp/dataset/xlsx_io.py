"""Read the client Excel question sheet without modifying the skill file.

Logic mirrored from `.claude/skills/euro-qa-run-eval/scripts/run_eval_dataset.py`
(load_questions / xlsx helpers) so we do not edit that skill.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass(frozen=True)
class ExcelQuestionRow:
    id: str
    question: str
    existing_correctness: str | None
    existing_completeness: str | None
    existing_hallucination: str | None
    existing_verdict: str | None
    question_type: str | None


def _cell_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _xlsx_col_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return max(index - 1, 0)


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    values: list[str] = []
    for item in root.findall("main:si", XML_NS):
        texts = [node.text or "" for node in item.findall(".//main:t", XML_NS)]
        values.append("".join(texts))
    return values


def _sheet_path_for_name(zf: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pkgrel:Relationship", XML_NS)
    }
    for sheet in workbook.findall("main:sheets/main:sheet", XML_NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib.get(f"{{{XML_NS['rel']}}}id")
        if rel_id is None or rel_id not in rel_targets:
            raise ValueError(f"Sheet relationship not found for {sheet_name!r}")
        target = rel_targets[rel_id]
        if target.startswith("/"):
            return target.lstrip("/")
        return "xl/" + target.lstrip("/")
    available = [
        sheet.attrib.get("name", "")
        for sheet in workbook.findall("main:sheets/main:sheet", XML_NS)
    ]
    raise ValueError(
        f"Sheet {sheet_name!r} not found. Available sheets: {', '.join(available)}"
    )


def _read_xlsx_rows(excel_path: Path, sheet_name: str) -> list[list[str | None]]:
    with zipfile.ZipFile(excel_path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_path = _sheet_path_for_name(zf, sheet_name)
        root = ET.fromstring(zf.read(sheet_path))

    rows: list[list[str | None]] = []
    for row in root.findall(".//main:sheetData/main:row", XML_NS):
        values: list[str | None] = []
        for cell in row.findall("main:c", XML_NS):
            cell_ref = cell.attrib.get("r", "")
            col_index = _xlsx_col_to_index(cell_ref)
            while len(values) <= col_index:
                values.append(None)

            cell_type = cell.attrib.get("t")
            text: str | None = None
            if cell_type == "inlineStr":
                texts = [node.text or "" for node in cell.findall(".//main:t", XML_NS)]
                text = "".join(texts)
            else:
                value_node = cell.find("main:v", XML_NS)
                if value_node is not None and value_node.text is not None:
                    if cell_type == "s":
                        text = shared_strings[int(value_node.text)]
                    else:
                        text = value_node.text
            values[col_index] = text
        rows.append(values)
    return rows


def load_excel_questions(
    excel_path: Path,
    sheet_name: str = "questions",
) -> list[ExcelQuestionRow]:
    """Load non-empty questions and free-text review columns from the workbook."""
    # Try common sheet names used in client workbooks.
    last_err: Exception | None = None
    for name in (sheet_name, "questions", "问题集", "Sheet1", "问题", "评估"):
        try:
            raw_rows = _read_xlsx_rows(excel_path, name)
            break
        except ValueError as exc:
            last_err = exc
            raw_rows = []
    else:
        raise ValueError(str(last_err) if last_err else "no sheet found")

    questions: list[ExcelQuestionRow] = []
    for row in raw_rows[1:]:
        question = _cell_text(row[0] if len(row) > 0 else None)
        if question is None:
            continue
        qid = f"Q{len(questions) + 1:02d}"
        questions.append(
            ExcelQuestionRow(
                id=qid,
                question=question,
                existing_correctness=_cell_text(row[1] if len(row) > 1 else None),
                existing_completeness=_cell_text(row[2] if len(row) > 2 else None),
                existing_hallucination=_cell_text(row[3] if len(row) > 3 else None),
                existing_verdict=_cell_text(row[4] if len(row) > 4 else None),
                question_type=_cell_text(row[5] if len(row) > 5 else None),
            )
        )
    return questions
