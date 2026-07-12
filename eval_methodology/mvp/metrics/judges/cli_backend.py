"""Codex / Claude CLI structured-output backends for gold + judge."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


class CLIJudgeError(RuntimeError):
    pass


class ParseResult:
    """Structured parse outcome — regex fallback is never a silent success."""

    def __init__(
        self,
        data: dict[str, Any] | None,
        *,
        ok: bool,
        source: str,
        error: str = "",
    ) -> None:
        self.data = data
        self.ok = ok
        self.source = source  # "json" | "envelope" | "regex_fallback" | "failed"
        self.error = error


def _extract_json_object(text: str, *, allow_regex_fallback: bool = False) -> ParseResult:
    """Parse CLI stdout as structured JSON.

    By default rejects regex `{...}` salvage (audit D3). Callers that want
    salvage must set allow_regex_fallback=True and then treat source==
    'regex_fallback' as a failed/missing measurement.
    """
    text = text.strip()
    if not text:
        return ParseResult(None, ok=False, source="failed", error="empty CLI output")

    # 1) Whole-stdout JSON object
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Claude envelope: may wrap structured_output / result
            for key in ("structured_output", "result", "output"):
                val = data.get(key)
                if isinstance(val, dict):
                    return ParseResult(val, ok=True, source="envelope")
                if isinstance(val, str) and val.strip().startswith("{"):
                    try:
                        inner = json.loads(val)
                        if isinstance(inner, dict):
                            return ParseResult(inner, ok=True, source="envelope")
                    except json.JSONDecodeError:
                        pass
            # content blocks
            content = data.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        raw = block.get("text") or ""
                        try:
                            inner = json.loads(raw)
                            if isinstance(inner, dict):
                                return ParseResult(inner, ok=True, source="envelope")
                        except json.JSONDecodeError:
                            continue
            # Bare schema object (no envelope keys that look like chat)
            if any(
                k in data
                for k in (
                    "claim_verdicts",
                    "citation_verdicts",
                    "claims",
                    "reference_answer",
                    "overall_agree",
                    "per_claim",
                )
            ):
                return ParseResult(data, ok=True, source="json")
            # Generic dict success when schema-shaped keys unknown
            if "model" not in data or len(data) > 2:
                return ParseResult(data, ok=True, source="json")
    except json.JSONDecodeError:
        pass

    if allow_regex_fallback:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, dict):
                    return ParseResult(
                        data, ok=False, source="regex_fallback", error="regex salvage"
                    )
            except json.JSONDecodeError as exc:
                return ParseResult(
                    None, ok=False, source="failed", error=f"regex JSON invalid: {exc}"
                )

    return ParseResult(
        None,
        ok=False,
        source="failed",
        error=f"could not parse structured JSON: {text[:500]}",
    )


def resolve_codex_model_id(explicit: str | None = None) -> str:
    """Best-effort model id from explicit arg or env (no network probe)."""
    if explicit:
        return explicit
    for env_key in ("CODEX_MODEL", "OPENAI_MODEL", "MVP_CODEX_MODEL"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    return "codex-unresolved"


def resolve_claude_model_id(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "MVP_CLAUDE_MODEL"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    return "claude-unresolved"


def run_codex_json(
    prompt: str,
    *,
    schema_path: Path,
    workdir: Path | None = None,
    model: str | None = None,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """codex exec --ephemeral -s read-only --output-schema ...

    Raises CLIJudgeError on non-structured output. Never silently accepts
    regex-salvaged JSON as a valid measurement.
    """
    schema_path = schema_path.resolve()
    if not schema_path.is_file():
        raise FileNotFoundError(schema_path)

    resolved_model = resolve_codex_model_id(model)
    cmd = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-schema",
        str(schema_path),
    ]
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt)

    cwd = str(workdir) if workdir else None
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIJudgeError(f"codex timed out after {timeout_s}s") from exc

    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    parsed = _extract_json_object(proc.stdout or "", allow_regex_fallback=True)
    if not parsed.ok or parsed.data is None or parsed.source == "regex_fallback":
        # Also try full raw (stdout+stderr) only as proper JSON, not regex.
        parsed2 = _extract_json_object(raw, allow_regex_fallback=False)
        if parsed2.ok and parsed2.data is not None:
            parsed = parsed2
        else:
            raise CLIJudgeError(
                f"codex structured parse failed "
                f"(rc={proc.returncode}, source={parsed.source}): "
                f"{parsed.error or parsed2.error}; tail={raw[-800:]}"
            )

    data = dict(parsed.data)
    # Prefer model mentioned in stdout banners if still unresolved.
    if resolved_model in ("codex-unresolved", "codex-default") or not model:
        m = re.search(r"model[=:\s]+([A-Za-z0-9._/-]+)", raw, re.I)
        if m:
            resolved_model = m.group(1)
    data["_resolved_model"] = resolved_model
    data["_family"] = "codex"
    data["_parse_source"] = parsed.source
    return data


def run_claude_json(
    prompt: str,
    *,
    schema_path: Path,
    model: str | None = None,
    timeout_s: float = 300.0,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """claude -p --json-schema --output-format json; tools off; no session persist."""
    schema_path = schema_path.resolve()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    resolved_model = resolve_claude_model_id(model)

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        "--tools",
        "",
        "--bare",
        "--no-session-persistence",
    ]
    if model:
        cmd.extend(["--model", model])
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIJudgeError(f"claude timed out after {timeout_s}s") from exc

    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    # Prefer outer envelope model id.
    try:
        outer = json.loads(proc.stdout or "")
        if isinstance(outer, dict) and outer.get("model"):
            resolved_model = str(outer["model"])
    except json.JSONDecodeError:
        pass

    parsed = _extract_json_object(proc.stdout or "", allow_regex_fallback=True)
    if not parsed.ok or parsed.data is None or parsed.source == "regex_fallback":
        raise CLIJudgeError(
            f"claude structured parse failed "
            f"(rc={proc.returncode}, source={parsed.source}): "
            f"{parsed.error}; tail={raw[-800:]}"
        )

    data = dict(parsed.data)
    data["_resolved_model"] = resolved_model
    data["_family"] = "claude"
    data["_parse_source"] = parsed.source
    return data


def run_with_retry(
    fn,
    *,
    retries: int = 1,
) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt >= retries:
                break
    assert last is not None
    raise last
