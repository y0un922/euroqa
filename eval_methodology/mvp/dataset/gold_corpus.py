"""Deterministic corpus manifest and gold evidence validation."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Any

MIN_QUOTE_CHARS = 20


def normalize_text(value: str) -> str:
    """Normalize Unicode and whitespace for deterministic quote containment."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def corpus_manifest(corpus_dir: Path) -> dict[str, Any]:
    """Return a stable manifest of readable Markdown corpus files.

    Raises:
        RuntimeError: If the corpus is empty or a Markdown symlink escapes it.
    """
    root = corpus_dir.resolve()
    files: list[Path] = []
    if root.is_dir():
        for path in sorted(root.rglob("*.md")):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"corpus symlink escapes root: {path}") from exc
            files.append(path)
    if not files:
        raise RuntimeError(f"no Markdown corpus files under {root}")
    digest = hashlib.sha256()
    rows = []
    for path in files:
        raw = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(raw).digest())
        rows.append({"path": relative, "size": len(raw)})
    return {"root": str(root), "files": rows, "sha256": digest.hexdigest()}


def _quote_in_section(document: str, section: str, normalized_quote: str) -> bool:
    """Return whether a quote occurs under the declared Markdown heading."""
    section_key = normalize_text(section).casefold()
    lines = document.splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if match:
            headings.append((index, normalize_text(match.group(1)).casefold()))
    for heading_index, (line_index, title) in enumerate(headings):
        if section_key != title:
            continue
        end = (
            headings[heading_index + 1][0]
            if heading_index + 1 < len(headings)
            else len(lines)
        )
        if normalized_quote in normalize_text("\n".join(lines[line_index:end])):
            return True
    return False


def validate_gold(gold: dict[str, Any], corpus_dir: Path) -> list[str]:
    """Validate exact corpus locators and claim/evidence invariants."""
    errors: list[str] = []
    root = corpus_dir.resolve()
    evidence = gold.get("evidence") or []
    claims = gold.get("claims") or []
    evidence_ids: set[str] = set()
    claim_ids: set[str] = set()

    for index, item in enumerate(evidence):
        eid = str(item.get("evidence_id") or "").strip()
        rel = str(item.get("document_path") or "").strip()
        section = str(item.get("section") or "").strip()
        quote = str(item.get("quote") or "")
        prefix = f"evidence[{index}]"
        if not eid or eid in evidence_ids:
            errors.append(f"{prefix}: missing or duplicate evidence_id={eid!r}")
        evidence_ids.add(eid)
        if not section:
            errors.append(f"{prefix}: section is required")
        normalized_quote = normalize_text(quote)
        if len(normalized_quote) < MIN_QUOTE_CHARS:
            errors.append(f"{prefix}: quote shorter than {MIN_QUOTE_CHARS} characters")
        relative_path = Path(rel)
        if relative_path.is_absolute() or ".." in relative_path.parts or "\\" in rel:
            errors.append(
                f"{prefix}: document_path must be a canonical relative path: {rel!r}"
            )
            continue
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{prefix}: document_path escapes corpus: {rel!r}")
            continue
        if candidate.suffix.lower() != ".md" or not candidate.is_file():
            errors.append(f"{prefix}: Markdown document not found: {rel!r}")
            continue
        raw_document = candidate.read_text(encoding="utf-8")
        document = normalize_text(raw_document)
        if normalized_quote and normalized_quote not in document:
            errors.append(f"{prefix}: quote not found verbatim in {rel!r}")
        elif normalized_quote and not _quote_in_section(
            raw_document, section, normalized_quote
        ):
            errors.append(
                f"{prefix}: section heading not found or quote is outside section: {section!r}"
            )

    used_evidence: set[str] = set()
    for index, claim in enumerate(claims):
        cid = str(claim.get("claim_id") or "").strip()
        status = claim.get("status")
        refs = [str(ref) for ref in claim.get("evidence_ids") or []]
        prefix = f"claim[{index}]"
        if not cid or cid in claim_ids:
            errors.append(f"{prefix}: missing or duplicate claim_id={cid!r}")
        claim_ids.add(cid)
        unknown = sorted(set(refs) - evidence_ids)
        if unknown:
            errors.append(f"{prefix}: unknown evidence_ids={unknown}")
        if status == "supported" and not refs:
            errors.append(f"{prefix}: supported claim has no evidence")
        if status == "corpus_gap" and refs:
            errors.append(f"{prefix}: corpus_gap claim references evidence")
        used_evidence.update(refs)
    unused = sorted(evidence_ids - used_evidence)
    if unused:
        errors.append(f"unreferenced evidence_ids={unused}")
    if not str(gold.get("reference_answer") or "").strip():
        errors.append("reference_answer is empty")
    if not claims:
        errors.append("claims is empty")
    return errors
