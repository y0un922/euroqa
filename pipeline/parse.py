"""Stage 1: MinerU API client for PDF → Markdown parsing."""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import structlog

from pipeline.config import PipelineConfig

logger = structlog.get_logger()


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
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=600.0) as client:
        with open(pdf_path, "rb") as f:
            resp = await client.post(
                f"{config.mineru_api_url}/api/v1/extract",
                files={"file": (pdf_path.name, f, "application/pdf")},
                data={
                    "parse_method": config.mineru_backend,
                    "is_table_recognition": "true",
                    "is_formula_recognition": "true",
                },
            )
        resp.raise_for_status()
        task_id = resp.json().get("task_id")
        logger.info("mineru_task_submitted", pdf=pdf_path.name, task_id=task_id)

        while True:
            status_resp = await client.get(
                f"{config.mineru_api_url}/api/v1/extract/{task_id}"
            )
            status_resp.raise_for_status()
            status = status_resp.json()

            if status.get("state") == "done":
                break
            if status.get("state") == "failed":
                raise RuntimeError(f"MinerU parsing failed: {status.get('error')}")

            logger.debug("mineru_polling", state=status.get("state"))
            time.sleep(5)

        result_resp = await client.get(
            f"{config.mineru_api_url}/api/v1/extract/{task_id}/result"
        )
        result_resp.raise_for_status()
        result = result_resp.json()

        md_path = output_dir / f"{pdf_path.stem}.md"
        md_path.write_text(result.get("markdown", ""), encoding="utf-8")

        meta_path = output_dir / f"{pdf_path.stem}_meta.json"
        meta_path.write_text(
            json.dumps(result.get("metadata", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info("mineru_parse_done", pdf=pdf_path.name, output=str(md_path))
        return md_path


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
