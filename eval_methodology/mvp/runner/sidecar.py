"""Bypass backend: spawn uvicorn with env overrides on an alt port.

Isolation:
  - state dirs redirected to a temp directory
  - never writes project .env
  - process group + finally kill
  - milvus collection must already exist (no create)
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

# Ensure project root is importable when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.candidate import (  # noqa: E402
    CandidateConfig,
    baseline_candidate,
    candidate_to_env,
    validate_against_server_config,
)
from eval_methodology.mvp.isolation import (  # noqa: E402
    assert_isolation,
    assert_milvus_collection_exists,
    compare_snapshots,
    take_snapshot,
)
from eval_methodology.mvp.paths import (  # noqa: E402
    ARTIFACTS_DIR,
    BASELINE_PORT,
    PROJECT_ROOT,
)
from eval_methodology.mvp.runner.client import query_stream  # noqa: E402


@dataclass
class SidecarHandle:
    """Live sidecar process + temp state."""

    port: int
    process: subprocess.Popen[str]
    temp_dir: Path
    env_overrides: dict[str, str]
    candidate: CandidateConfig
    log_path: Path
    _owned_temp: bool = True
    _stopped: bool = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def stream_url(self) -> str:
        return f"{self.base_url}/api/v1/query/stream"

    def wait_ready(self, timeout_s: float = 120.0) -> None:
        deadline = time.monotonic() + timeout_s
        last_err: Exception | None = None
        health_urls = [
            f"{self.base_url}/docs",
            f"{self.base_url}/openapi.json",
            f"{self.base_url}/api/v1/health",
        ]
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                tail = _tail_log(self.log_path, n=40)
                raise RuntimeError(
                    f"sidecar exited early with code {self.process.returncode}. "
                    f"log tail:\n{tail}"
                )
            for url in health_urls:
                try:
                    resp = httpx.get(url, timeout=2.0)
                    if resp.status_code < 500:
                        return
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
            time.sleep(0.5)
        tail = _tail_log(self.log_path, n=40)
        raise TimeoutError(
            f"sidecar on port {self.port} not ready within {timeout_s}s "
            f"(last_err={last_err}). log tail:\n{tail}"
        )

    def stop(self, grace_s: float = 8.0) -> None:
        if self._stopped:
            return
        self._stopped = True
        proc = self.process
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            deadline = time.monotonic() + grace_s
            while time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.1)
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                proc.wait(timeout=5)
        if self._owned_temp:
            # Keep temp dir for debugging; caller may delete.
            pass


@dataclass
class SidecarSession:
    """Context manager wrapping start/stop + isolation snapshots."""

    candidate: CandidateConfig
    port: int = BASELINE_PORT
    ready_timeout_s: float = 120.0
    handle: SidecarHandle | None = None
    before: Any = None
    after: Any = None
    isolation_report: Any = None
    _extra_env: dict[str, str] = field(default_factory=dict)

    def __enter__(self) -> SidecarHandle:
        self.before = take_snapshot()
        self.handle = start_sidecar(
            self.candidate,
            port=self.port,
            extra_env=self._extra_env,
        )
        self.handle.wait_ready(timeout_s=self.ready_timeout_s)
        return self.handle

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            self.handle.stop()
        self.after = take_snapshot()
        self.isolation_report = compare_snapshots(self.before, self.after)
        # Always surface isolation failure even if the body raised.
        try:
            assert_isolation(self.isolation_report)
        except RuntimeError:
            if exc_type is None:
                raise
            # Prefer original exception; isolation failure is attached via note.
            if hasattr(exc, "add_note"):
                exc.add_note(
                    "isolation also failed: "
                    + "; ".join(self.isolation_report.reasons)
                )


def build_sidecar_env(
    candidate: CandidateConfig,
    temp_dir: Path,
    *,
    extra_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build subprocess env: ambient + isolation redirects + candidate overrides."""
    # Validate candidate against full ServerConfig before launch.
    validated = validate_against_server_config(candidate)
    assert_milvus_collection_exists(
        host=validated.milvus_host,
        port=validated.milvus_port,
        collection=validated.milvus_collection,
    )

    temp_dir.mkdir(parents=True, exist_ok=True)
    kb_path = temp_dir / "knowledge_bases.db"
    parsed_dir = temp_dir / "parsed"
    debug_dir = temp_dir / "debug_runs"
    spot_dir = temp_dir / "spot_check"
    log_dir = temp_dir / "logs"
    for path in (parsed_dir, debug_dir, spot_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # Isolation redirects (state must not touch project trees).
    env["KNOWLEDGE_BASE_DB_PATH"] = str(kb_path)
    env["PARSED_DIR"] = str(parsed_dir)
    env["DEBUG_PIPELINE_DIR"] = str(debug_dir)
    env["SPOT_CHECK_ENABLED"] = "0"
    env["SPOT_CHECK_DIR"] = str(spot_dir)
    env["REDIS_URL"] = ""
    # Keep embedding/rerank/LLM from ambient .env via ServerConfig load in child.
    env.update(candidate_to_env(candidate))
    if extra_env:
        env.update({k: str(v) for k, v in extra_env.items()})
    return env


def start_sidecar(
    candidate: CandidateConfig,
    *,
    port: int = BASELINE_PORT,
    temp_dir: Path | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> SidecarHandle:
    """Spawn uvicorn in a new process group on the given port."""
    owned = temp_dir is None
    if temp_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"euroqa_mvp_sidecar_{port}_"))
    env = build_sidecar_env(candidate, temp_dir, extra_env=extra_env)
    log_path = temp_dir / "uvicorn.log"
    cmd = [
        "uv",
        "run",
        "uvicorn",
        "server.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "info",
    ]
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,  # process group for killpg
        )
    except Exception:
        log_file.close()
        raise

    return SidecarHandle(
        port=port,
        process=process,
        temp_dir=temp_dir,
        env_overrides={
            k: env[k]
            for k in (
                "KNOWLEDGE_BASE_DB_PATH",
                "PARSED_DIR",
                "DEBUG_PIPELINE_DIR",
                "SPOT_CHECK_ENABLED",
                "REDIS_URL",
                "RETRIEVAL_AUTO_CROSS_REF_CLOSURE",
            )
            if k in env
        },
        candidate=candidate,
        log_path=log_path,
        _owned_temp=owned,
    )


def _tail_log(path: Path, n: int = 40) -> str:
    if not path.is_file():
        return "(no log)"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-n:])


def run_smoke(
    *,
    port: int = BASELINE_PORT,
    question: str | None = None,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """Start sidecar, hit /query/stream once, stop, assert isolation."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    before = take_snapshot()
    candidate = baseline_candidate()
    handle: SidecarHandle | None = None
    record: dict[str, Any] = {
        "ok": False,
        "port": port,
        "candidate": candidate.model_dump(),
    }
    try:
        handle = start_sidecar(candidate, port=port)
        record["temp_dir"] = str(handle.temp_dir)
        record["env_overrides"] = handle.env_overrides
        handle.wait_ready(timeout_s=120.0)
        q = question or "C30/37混凝土的抗压强度设计值是多少？"
        result = query_stream(
            handle.stream_url,
            q,
            timeout_s=timeout_s,
        )
        record["query"] = {
            "question": q,
            "status": result.get("status"),
            "answer_preview": (result.get("answer") or "")[:200],
            "chunk_ids": result.get("context_chunk_ids", [])[:20],
            "unresolved_refs": result.get("unresolved_refs", []),
            "elapsed_ms": result.get("elapsed_ms"),
        }
        record["ok"] = result.get("status") == "ok"
    finally:
        if handle is not None:
            handle.stop()
        after = take_snapshot()
        report = compare_snapshots(before, after)
        record["isolation"] = report.to_dict()
        out = ARTIFACTS_DIR / "smoke_isolation.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        assert_isolation(report)
    if not record["ok"]:
        raise RuntimeError(f"smoke query failed: {record.get('query')}")
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MVP sidecar runner")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="start baseline sidecar, query 1 question, stop, assert isolation",
    )
    parser.add_argument("--port", type=int, default=BASELINE_PORT)
    parser.add_argument("--question", type=str, default=None)
    parser.add_argument(
        "--isolation-only",
        action="store_true",
        help="only snapshot git/.env before and after a no-op (no backend)",
    )
    args = parser.parse_args(argv)

    if args.isolation_only:
        before = take_snapshot()
        after = take_snapshot()
        report = compare_snapshots(before, after)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        assert_isolation(report)
        print("isolation-only OK")
        return 0

    if args.smoke:
        record = run_smoke(port=args.port, question=args.question)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        print("smoke OK")
        return 0

    parser.error("specify --smoke or --isolation-only")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
