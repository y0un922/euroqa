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


# Process + disk pin so cache keys use the real model after first resolution
# (audit D4: avoid lookup under codex-unresolved while store under real id).
_PINNED_MODELS: dict[str, str] = {}


def _pins_path() -> Path:
    from eval_methodology.mvp.paths import CACHE_DIR

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "resolved_models.json"


def _load_disk_pins() -> dict[str, str]:
    path = _pins_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items() if v}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def pin_resolved_model(family: str, model_id: str) -> None:
    """Remember the actual model id for a judge family (process + disk)."""
    if not model_id or "unresolved" in model_id or model_id.endswith("-failed"):
        return
    _PINNED_MODELS[family] = model_id
    pins = _load_disk_pins()
    if pins.get(family) == model_id:
        return
    pins[family] = model_id
    try:
        _pins_path().write_text(
            json.dumps(pins, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def resolve_codex_model_id(explicit: str | None = None) -> str:
    """Model id: explicit → env → pinned (disk/process) → unresolved placeholder."""
    if explicit:
        return explicit
    for env_key in ("CODEX_MODEL", "OPENAI_MODEL", "MVP_CODEX_MODEL"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    if "codex" in _PINNED_MODELS:
        return _PINNED_MODELS["codex"]
    disk = _load_disk_pins()
    if disk.get("codex"):
        _PINNED_MODELS["codex"] = disk["codex"]
        return disk["codex"]
    return "codex-unresolved"


def resolve_claude_model_id(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for env_key in ("ANTHROPIC_MODEL", "CLAUDE_MODEL", "MVP_CLAUDE_MODEL"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return val
    if "claude" in _PINNED_MODELS:
        return _PINNED_MODELS["claude"]
    disk = _load_disk_pins()
    if disk.get("claude"):
        _PINNED_MODELS["claude"] = disk["claude"]
        return disk["claude"]
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
    pin_resolved_model("codex", resolved_model)
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
    # Prefer outer envelope model id (field varies by CLI version).
    try:
        outer = json.loads(proc.stdout or "")
        if isinstance(outer, dict):
            if outer.get("model"):
                resolved_model = str(outer["model"])
            else:
                usage = outer.get("modelUsage") or outer.get("model_usage")
                if isinstance(usage, dict) and usage:
                    # e.g. {"glm-5.2:cloud[1m]": {...}}
                    resolved_model = str(next(iter(usage.keys())))
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
    pin_resolved_model("claude", resolved_model)
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
