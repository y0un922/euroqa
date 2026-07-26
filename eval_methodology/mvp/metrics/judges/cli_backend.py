"""Codex / Claude CLI structured-output backends for gold + judge."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any


class CLIJudgeError(RuntimeError):
    pass


_PROCESS_GROUP_GRACE_S = 5.0


def _terminate_process_group(
    process: subprocess.Popen[str], *, grace_s: float = _PROCESS_GROUP_GRACE_S
) -> tuple[str, str]:
    """Terminate a CLI process group and drain pipes held by descendants."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return process.communicate()
    try:
        return process.communicate(timeout=grace_s)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return process.communicate()


def _run_cli_process(
    cmd: list[str], *, cwd: str | None, timeout_s: float
) -> subprocess.CompletedProcess[str]:
    """Run a CLI in its own process group and clean up descendants on timeout."""
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = _terminate_process_group(process)
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout_s,
            output=stdout or exc.output,
            stderr=stderr or exc.stderr,
        ) from exc
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


class ParseResult:
    """Structured parse outcome."""

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
        self.source = source  # "json" | "envelope" | "failed"
        self.error = error


def _extract_json_object(text: str) -> ParseResult:
    """Parse CLI stdout as structured JSON.

    Only valid whole-output JSON and supported CLI envelopes are accepted.
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
    ignore_rules: bool = False,
    add_dirs: tuple[Path, ...] = (),
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """codex exec --ephemeral -s read-only --output-schema ...

    Raises CLIJudgeError on non-structured output.
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
    if workdir:
        cmd.extend(["-C", str(workdir.resolve())])
    for directory in add_dirs:
        cmd.extend(["--add-dir", str(directory.resolve())])
    if ignore_rules:
        cmd.append("--ignore-rules")
    if reasoning_effort:
        cmd.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    if model:
        cmd.extend(["-m", model])
    cmd.append(prompt)

    cwd = str(workdir) if workdir else None
    try:
        proc = _run_cli_process(cmd, cwd=cwd, timeout_s=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise CLIJudgeError(f"codex timed out after {timeout_s}s") from exc

    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        raise CLIJudgeError(
            f"codex failed with rc={proc.returncode}; tail={raw[-800:]}"
        )
    parsed = _extract_json_object(proc.stdout or "")
    if not parsed.ok or parsed.data is None:
        parsed2 = _extract_json_object(raw)
        if parsed2.ok and parsed2.data is not None:
            parsed = parsed2
        else:
            raise CLIJudgeError(
                f"codex structured parse failed "
                f"(rc={proc.returncode}, source={parsed.source}): "
                f"{parsed.error or parsed2.error}; tail={raw[-800:]}"
            )

    data = dict(parsed.data)
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
    workdir: Path | None = None,
    tools: tuple[str, ...] = (),
    add_dirs: tuple[Path, ...] = (),
    permission_mode: str | None = None,
) -> dict[str, Any]:
    """Run Claude with native structured output and explicit filesystem access.

    Judge calls keep the default empty tool set. Gold review calls opt in to the
    read-only ``Read``, ``Grep``, and ``Glob`` tools for the parsed corpus.
    """
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
        ",".join(tools),
        "--no-session-persistence",
    ]
    if model:
        cmd.extend(["--model", model])
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    for directory in add_dirs:
        cmd.extend(["--add-dir", str(directory.resolve())])
    if permission_mode:
        cmd.extend(["--permission-mode", permission_mode])

    try:
        proc = _run_cli_process(
            cmd,
            cwd=str(workdir) if workdir else None,
            timeout_s=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIJudgeError(f"claude timed out after {timeout_s}s") from exc

    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        raise CLIJudgeError(
            f"claude failed with rc={proc.returncode}; tail={raw[-800:]}"
        )
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

    parsed = _extract_json_object(proc.stdout or "")
    if not parsed.ok or parsed.data is None:
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
