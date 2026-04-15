"""Stage 1: MinerU API client for PDF → Markdown parsing."""
from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
import zipfile

import httpx
import structlog

from pipeline.content_list import content_list_output_name
from pipeline.config import PipelineConfig

logger = structlog.get_logger()


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


async def _parse_pdf_via_official(
    pdf_path: Path,
    output_dir: Path,
    config: PipelineConfig,
) -> Path:
    base_url = _normalize_base_url(config.mineru_official_base_url)
    headers = _get_official_headers(config)
    request_body = {
        "enable_formula": config.mineru_enable_formula,
        "enable_table": config.mineru_enable_table,
        "language": config.mineru_language,
        "model_version": config.mineru_official_model_version,
        "files": [
            {
                "name": pdf_path.name,
                "data_id": pdf_path.stem,
                "is_ocr": config.mineru_is_ocr,
            }
        ],
    }

    async with _get_http_client(config) as client:
        create_resp = await client.post(
            f"{base_url}/api/v4/file-urls/batch",
            headers=headers,
            json=request_body,
        )
        create_resp.raise_for_status()
        create_data = _ensure_official_success(
            create_resp.json(),
            "upload url request",
        )
        batch_id = create_data.get("batch_id")
        upload_urls = create_data.get("file_urls", [])
        if not batch_id or not upload_urls:
            raise RuntimeError("MinerU official upload request returned no batch_id or file_urls")

        upload_resp = await client.put(
            upload_urls[0],
            content=pdf_path.read_bytes(),
        )
        upload_resp.raise_for_status()
        logger.info(
            "mineru_official_upload_done",
            pdf=pdf_path.name,
            batch_id=batch_id,
        )

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
            matched = next(
                (item for item in extract_results if item.get("file_name") == pdf_path.name),
                extract_results[0] if len(extract_results) == 1 else None,
            )
            if matched is None:
                raise RuntimeError(
                    f"MinerU official batch result missing entry for {pdf_path.name}"
                )

            state = matched.get("state")
            if state == "done":
                break
            if state == "failed":
                raise RuntimeError(
                    f"MinerU official parsing failed: {matched.get('err_msg', 'unknown error')}"
                )

            logger.debug(
                "mineru_official_polling",
                pdf=pdf_path.name,
                batch_id=batch_id,
                state=state,
            )
            await asyncio.sleep(config.mineru_poll_interval_seconds)

        full_zip_url = matched.get("full_zip_url")
        if not full_zip_url:
            raise RuntimeError(
                f"MinerU official result for {pdf_path.name} missing full_zip_url"
            )

        zip_resp = await client.get(full_zip_url)
        zip_resp.raise_for_status()
        markdown, zip_metadata, content_list = _extract_markdown_from_zip(
            zip_resp.content
        )

        md_path = _write_parse_outputs(
            output_dir,
            pdf_path.stem,
            markdown,
            {
                "provider": "official",
                "batch_id": batch_id,
                "result": matched,
                **zip_metadata,
            },
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
