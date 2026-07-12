"""Codex / Claude CLI structured-output backends for gold + judge."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class CLIJudgeError(RuntimeError):
    pass


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise CLIJudgeError("empty CLI output")
    # Direct JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # Claude --output-format json often wraps content.
    try:
        outer = json.loads(text)
        if isinstance(outer, dict):
            for key in ("structured_output", "result", "content", "output"):
                val = outer.get(key)
                if isinstance(val, dict):
                    return val
                if isinstance(val, str):
                    try:
                        inner = json.loads(val)
                        if isinstance(inner, dict):
                            return inner
                    except json.JSONDecodeError:
                        pass
            # message content blocks
            content = outer.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        try:
                            inner = json.loads(block.get("text") or "")
                            if isinstance(inner, dict):
                                return inner
                        except json.JSONDecodeError:
                            continue
    except json.JSONDecodeError:
        pass
    # Fallback: first {...} blob
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise CLIJudgeError(f"could not parse JSON from CLI output: {text[:500]}")


def run_codex_json(
    prompt: str,
    *,
    schema_path: Path,
    workdir: Path | None = None,
    model: str | None = None,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """codex exec --ephemeral -s read-only --output-schema ..."""
    schema_path = schema_path.resolve()
    if not schema_path.is_file():
        raise FileNotFoundError(schema_path)

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
    if proc.returncode != 0:
        # Still try to parse stdout; some versions write JSON then exit non-zero.
        try:
            data = _extract_json_object(proc.stdout or "")
            data["_resolved_model"] = model or "codex-default"
            data["_family"] = "codex"
            return data
        except CLIJudgeError:
            raise CLIJudgeError(
                f"codex exit {proc.returncode}: {raw[-1500:]}"
            ) from None

    data = _extract_json_object(proc.stdout or raw)
    data["_resolved_model"] = model or "codex-default"
    data["_family"] = "codex"
    return data


def run_claude_json(
    prompt: str,
    *,
    schema_path: Path,
    model: str | None = None,
    timeout_s: float = 300.0,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """claude -p --json-schema --output-format json with tools disabled."""
    schema_path = schema_path.resolve()
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema, ensure_ascii=False),
        # Disable tools: empty tools list when supported.
        "--tools",
        "",
        "--bare",
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
    if proc.returncode != 0:
        try:
            data = _extract_json_object(proc.stdout or "")
            data["_resolved_model"] = model or "claude-default"
            data["_family"] = "claude"
            return data
        except CLIJudgeError:
            raise CLIJudgeError(
                f"claude exit {proc.returncode}: {raw[-1500:]}"
            ) from None

    data = _extract_json_object(proc.stdout or raw)
    data["_resolved_model"] = model or "claude-default"
    data["_family"] = "claude"
    # Try to pull model from outer envelope if present.
    try:
        outer = json.loads(proc.stdout or "")
        if isinstance(outer, dict) and outer.get("model"):
            data["_resolved_model"] = outer["model"]
    except json.JSONDecodeError:
        pass
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
