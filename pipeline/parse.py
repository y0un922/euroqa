"""Stage 1: MinerU API client for PDF → Markdown parsing."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import io
import json
from pathlib import Path
import zipfile

import fitz
import httpx
import structlog

from pipeline.content_list import content_list_output_name
from pipeline.config import PipelineConfig

logger = structlog.get_logger()

_MINERU_OFFICIAL_MAX_PAGES = 200


@dataclass(frozen=True)
class _OfficialPdfPart:
    index: int
    name: str
    data_id: str
    content: bytes
    page_offset: int
    page_count: int

    @property
    def start_page(self) -> int:
        return self.page_offset

    @property
    def end_page(self) -> int:
        return self.page_offset + self.page_count - 1


def _write_parse_outputs(
    output_dir: Path,
    stem: str,
    markdown: str,
    metadata: dict,
    content_list: object | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{stem}.md"
    md_path.write_text(markdown, encoding="utf-8")

    if content_list is not None:
        output_name = content_list_output_name(stem)
        metadata = {
            **metadata,
            "content_list_output": output_name,
        }
        content_list_path = output_dir / output_name
        content_list_path.write_text(
            json.dumps(content_list, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    meta_path = output_dir / f"{stem}_meta.json"
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return md_path


def _get_http_client(config: PipelineConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=config.mineru_request_timeout_seconds)


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def _ensure_official_success(payload: dict, context: str) -> dict:
    if payload.get("code") != 0:
        raise RuntimeError(
            f"MinerU official {context} failed: {payload.get('msg', 'unknown error')}"
        )
    return payload.get("data", {})


def _get_official_headers(config: PipelineConfig) -> dict[str, str]:
    if not config.mineru_api_token:
        raise RuntimeError(
            "MINERU_API_TOKEN is required when MINERU_PROVIDER=official"
        )
    return {
        "Authorization": f"Bearer {config.mineru_api_token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }


async def _parse_pdf_via_local(
    pdf_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    async with _get_http_client(config) as client:
        with open(pdf_path, "rb") as f:
            resp = await client.post(
                f"{_normalize_base_url(config.mineru_api_url)}/api/v1/extract",
                files={"file": (pdf_path.name, f, "application/pdf")},
                data={
                    "parse_method": config.mineru_backend,
                    "is_table_recognition": str(config.mineru_enable_table).lower(),
                    "is_formula_recognition": str(config.mineru_enable_formula).lower(),
                },
            )
        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        logger.info("mineru_task_submitted", pdf=pdf_path.name, task_id=task_id)

        while True:
            status_resp = await client.get(
                f"{_normalize_base_url(config.mineru_api_url)}/api/v1/extract/{task_id}"
            )
            status_resp.raise_for_status()
            status = status_resp.json()
            state = status.get("state")

            if state == "done":
                break
            if state == "failed":
                raise RuntimeError(
                    f"MinerU parsing failed: {status.get('error', 'unknown error')}"
                )

            logger.debug("mineru_polling", state=state)
            await asyncio.sleep(config.mineru_poll_interval_seconds)

        result_resp = await client.get(
            f"{_normalize_base_url(config.mineru_api_url)}/api/v1/extract/{task_id}/result"
        )
        result_resp.raise_for_status()
        result = result_resp.json()
        content_list = result.get("content_list")

        md_path = _write_parse_outputs(
            output_dir,
            pdf_path.stem,
            result.get("markdown", ""),
            result.get("metadata", {}),
            content_list=content_list,
        )
        logger.info("mineru_parse_done", pdf=pdf_path.name, output=str(md_path))
        return md_path


def _find_zip_member(names: list[str], suffix: str) -> str:
    for name in names:
        if name.endswith(suffix):
            return name
    raise RuntimeError(f"MinerU result archive missing required file: {suffix}")


def _extract_markdown_from_zip(zip_bytes: bytes) -> tuple[str, dict, object | None]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        markdown_name = _find_zip_member(names, "full.md")
        markdown = archive.read(markdown_name).decode("utf-8")
        metadata: dict = {
            "archive_members": names,
            "markdown_file": markdown_name,
        }
        content_list: object | None = None
        content_list_name = next(
            (name for name in names if name.endswith("_content_list.json")),
            None,
        )
        if content_list_name:
            metadata["content_list_file"] = content_list_name
            content_list = json.loads(
                archive.read(content_list_name).decode("utf-8")
            )
        return markdown, metadata, content_list


def _get_pdf_page_count(pdf_path: Path) -> int:
    """Return the PDF page count, failing closed when it cannot be proven."""

    try:
        with fitz.open(pdf_path) as document:
            page_count = int(document.page_count)
    except Exception as exc:
        raise RuntimeError(f"Unable to read PDF page count for {pdf_path.name}") from exc
    if page_count <= 0:
        raise RuntimeError(f"PDF {pdf_path.name} has no readable pages")
    return page_count


def _split_pdf_for_official(pdf_path: Path, page_count: int) -> list[_OfficialPdfPart]:
    """Split a large PDF into in-memory parts under MinerU official's page limit."""

    parts: list[_OfficialPdfPart] = []
    with fitz.open(pdf_path) as source:
        if source.page_count != page_count:
            raise RuntimeError(f"PDF page count changed while splitting {pdf_path.name}")
        for index, start in enumerate(
            range(0, page_count, _MINERU_OFFICIAL_MAX_PAGES),
            start=1,
        ):
            end_exclusive = min(start + _MINERU_OFFICIAL_MAX_PAGES, page_count)
            with fitz.open() as part_doc:
                part_doc.insert_pdf(
                    source,
                    from_page=start,
                    to_page=end_exclusive - 1,
                )
                content = part_doc.tobytes(garbage=4, deflate=True)
            part_page_count = end_exclusive - start
            parts.append(
                _OfficialPdfPart(
                    index=index,
                    name=(
                        f"{pdf_path.stem}__part{index:03d}"
                        f"_pages{start + 1}-{end_exclusive}.pdf"
                    ),
                    data_id=f"{pdf_path.stem}__part{index:03d}",
                    content=content,
                    page_offset=start,
                    page_count=part_page_count,
                )
            )
    return parts


def _make_official_request_body(
    config: PipelineConfig,
    parts: list[_OfficialPdfPart],
) -> dict:
    return {
        "enable_formula": config.mineru_enable_formula,
        "enable_table": config.mineru_enable_table,
        "language": config.mineru_language,
        "model_version": config.mineru_official_model_version,
        "files": [
            {
                "name": part.name,
                "data_id": part.data_id,
                "is_ocr": config.mineru_is_ocr,
            }
            for part in parts
        ],
    }


def _items_from_content_list(content_list: object, *, part_name: str) -> list[dict]:
    if isinstance(content_list, dict):
        items = content_list.get("items")
    else:
        items = content_list
    if not isinstance(items, list):
        raise RuntimeError(f"MinerU split result for {part_name} has invalid content_list")
    if not items:
        raise RuntimeError(f"MinerU split result for {part_name} has empty content_list")
    if not all(isinstance(item, dict) for item in items):
        raise RuntimeError(f"MinerU split result for {part_name} has non-object items")
    return items


def _offset_content_list_items(
    content_list: object,
    part: _OfficialPdfPart,
) -> tuple[list[dict], dict]:
    """Validate and offset all page_idx values from part-local to original pages."""

    items = _items_from_content_list(content_list, part_name=part.name)
    adjusted_items: list[dict] = []
    local_pages: list[int] = []
    for item in items:
        page_idx = item.get("page_idx")
        if not isinstance(page_idx, int):
            raise RuntimeError(
                f"MinerU split result for {part.name} has item without integer page_idx"
            )
        if page_idx < 0 or page_idx >= part.page_count:
            raise RuntimeError(
                f"MinerU split result for {part.name} has out-of-range page_idx "
                f"{page_idx}; expected 0..{part.page_count - 1}"
            )
        adjusted = dict(item)
        adjusted["page_idx"] = page_idx + part.page_offset
        adjusted_items.append(adjusted)
        local_pages.append(page_idx)

    original_pages = [page + part.page_offset for page in local_pages]
    return adjusted_items, {
        "item_count": len(adjusted_items),
        "min_local_page_idx": min(local_pages),
        "max_local_page_idx": max(local_pages),
        "min_original_page_idx": min(original_pages),
        "max_original_page_idx": max(original_pages),
    }


def _merged_official_split_outputs(
    parts: list[_OfficialPdfPart],
    part_results: list[tuple[dict, str, dict, object | None]],
    *,
    original_page_count: int,
) -> tuple[str, dict, dict]:
    """Merge split MinerU outputs after strict page-metadata validation."""

    markdown_parts: list[str] = []
    merged_items: list[dict] = []
    part_metadata: list[dict] = []

    for part, (result, markdown, zip_metadata, content_list) in zip(
        parts,
        part_results,
        strict=True,
    ):
        if content_list is None:
            raise RuntimeError(
                f"MinerU split result for {part.name} missing content_list"
            )
        adjusted_items, validation = _offset_content_list_items(content_list, part)
        markdown_parts.append(markdown.strip())
        merged_items.extend(adjusted_items)
        part_metadata.append(
            {
                "index": part.index,
                "file_name": part.name,
                "data_id": part.data_id,
                "page_offset": part.page_offset,
                "page_start": part.start_page,
                "page_end": part.end_page,
                "page_count": part.page_count,
                "batch_id": result.get("batch_id"),
                "result": result,
                "zip": zip_metadata,
                "validation": validation,
            }
        )

    if not merged_items:
        raise RuntimeError("MinerU split merge produced no content_list items")

    max_page_idx = max(item["page_idx"] for item in merged_items)
    if max_page_idx >= original_page_count:
        raise RuntimeError(
            "MinerU split merge produced page_idx outside original PDF page count"
        )

    return (
        "\n\n".join(part for part in markdown_parts if part),
        {"items": merged_items},
        {
            "split_pdf": True,
            "original_page_count": original_page_count,
            "page_limit": _MINERU_OFFICIAL_MAX_PAGES,
            "part_count": len(parts),
            "parts": part_metadata,
            "validation": {
                "status": "passed",
                "max_original_page_idx": max_page_idx,
            },
        },
    )


async def _submit_official_parts(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    config: PipelineConfig,
    parts: list[_OfficialPdfPart],
) -> tuple[str, list[str]]:
    create_resp = await client.post(
        f"{base_url}/api/v4/file-urls/batch",
        headers=headers,
        json=_make_official_request_body(config, parts),
    )
    create_resp.raise_for_status()
    create_data = _ensure_official_success(
        create_resp.json(),
        "upload url request",
    )
    batch_id = create_data.get("batch_id")
    upload_urls = create_data.get("file_urls", [])
    if not batch_id or not isinstance(upload_urls, list):
        raise RuntimeError("MinerU official upload request returned no batch_id or file_urls")
    if len(upload_urls) != len(parts):
        raise RuntimeError(
            "MinerU official upload request returned unexpected file_urls count"
        )

    for part, upload_url in zip(parts, upload_urls, strict=True):
        upload_resp = await client.put(upload_url, content=part.content)
        upload_resp.raise_for_status()
        logger.info(
            "mineru_official_upload_done",
            pdf=part.name,
            batch_id=batch_id,
            page_offset=part.page_offset,
            page_count=part.page_count,
        )
    return batch_id, upload_urls


async def _wait_official_parts_done(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    headers: dict[str, str],
    config: PipelineConfig,
    batch_id: str,
    parts: list[_OfficialPdfPart],
) -> dict[str, dict]:
    expected_names = {part.name for part in parts}

    while True:
        result_resp = await client.get(
            f"{base_url}/api/v4/extract-results/batch/{batch_id}",
            headers=headers,
        )
        result_resp.raise_for_status()
        result_data = _ensure_official_success(
            result_resp.json(),
            "batch result query",
        )
        extract_results = result_data.get("extract_result", [])
        if not isinstance(extract_results, list):
            raise RuntimeError("MinerU official batch result has invalid extract_result")
        matched = {
            item.get("file_name"): {**item, "batch_id": batch_id}
            for item in extract_results
            if isinstance(item, dict) and item.get("file_name") in expected_names
        }
        if set(matched) != expected_names:
            raise RuntimeError("MinerU official batch result missing split part entries")

        failed = [
            item
            for item in matched.values()
            if item.get("state") == "failed"
        ]
        if failed:
            raise RuntimeError(
                "MinerU official parsing failed: "
                + "; ".join(
                    str(item.get("err_msg", "unknown error")) for item in failed
                )
            )
        if all(item.get("state") == "done" for item in matched.values()):
            return matched

        logger.debug(
            "mineru_official_polling",
            batch_id=batch_id,
            states={name: item.get("state") for name, item in matched.items()},
        )
        await asyncio.sleep(config.mineru_poll_interval_seconds)


async def _parse_pdf_via_official(
    pdf_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    base_url = _normalize_base_url(config.mineru_official_base_url)
    headers = _get_official_headers(config)
    page_count = _get_pdf_page_count(pdf_path)
    if page_count > _MINERU_OFFICIAL_MAX_PAGES:
        parts = _split_pdf_for_official(pdf_path, page_count)
    else:
        parts = [
            _OfficialPdfPart(
                index=1,
                name=pdf_path.name,
                data_id=pdf_path.stem,
                content=pdf_path.read_bytes(),
                page_offset=0,
                page_count=page_count,
            )
        ]

    async with _get_http_client(config) as client:
        batch_id, _ = await _submit_official_parts(
            client,
            base_url=base_url,
            headers=headers,
            config=config,
            parts=parts,
        )
        matched_by_name = await _wait_official_parts_done(
            client,
            base_url=base_url,
            headers=headers,
            config=config,
            batch_id=batch_id,
            parts=parts,
        )

        part_results: list[tuple[dict, str, dict, object | None]] = []
        for part in parts:
            matched = matched_by_name[part.name]
            full_zip_url = matched.get("full_zip_url")
            if not full_zip_url:
                raise RuntimeError(
                    f"MinerU official result for {part.name} missing full_zip_url"
                )

            zip_resp = await client.get(full_zip_url)
            zip_resp.raise_for_status()
            markdown, zip_metadata, content_list = _extract_markdown_from_zip(
                zip_resp.content
            )
            part_results.append((matched, markdown, zip_metadata, content_list))

        if len(parts) == 1:
            matched, markdown, zip_metadata, content_list = part_results[0]
            metadata = {
                "provider": "official",
                "batch_id": batch_id,
                "result": matched,
                "original_page_count": page_count,
                **zip_metadata,
            }
        else:
            markdown, content_list, split_metadata = _merged_official_split_outputs(
                parts,
                part_results,
                original_page_count=page_count,
            )
            metadata = {
                "provider": "official",
                "batch_id": batch_id,
                **split_metadata,
            }

        md_path = _write_parse_outputs(
            output_dir,
            pdf_path.stem,
            markdown,
            metadata,
            content_list=content_list,
        )
        logger.info("mineru_parse_done", pdf=pdf_path.name, output=str(md_path))
        return md_path


async def parse_pdf(
    pdf_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    """Call MinerU API to parse a single PDF into Markdown.

    Args:
        pdf_path: path to PDF file
        output_dir: output directory for Markdown + images
        config: pipeline configuration

    Returns:
        Path to output Markdown file
    """
    provider = config.mineru_provider.lower()
    if provider == "local":
        return await _parse_pdf_via_local(pdf_path, output_dir, config)
    if provider == "official":
        return await _parse_pdf_via_official(pdf_path, output_dir, config)
    raise RuntimeError(f"Unsupported MINERU_PROVIDER: {config.mineru_provider}")


async def parse_all_pdfs(config: PipelineConfig) -> list[Path]:
    """Parse all PDFs in the configured directory."""
    pdf_dir = Path(config.pdf_dir)
    parsed_dir = Path(config.parsed_dir)
    results: list[Path] = []

    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        output_dir = parsed_dir / pdf_path.stem
        try:
            md_path = await parse_pdf(pdf_path, output_dir, config)
            results.append(md_path)
        except Exception:
            logger.exception("parse_failed", pdf=pdf_path.name)

    return results
