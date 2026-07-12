"""Isolation verification: git dirty-set diff + .env content hash.

The working tree may already be dirty; we only assert that a run introduces
no *new* dirty paths outside the allowed eval_methodology/ footprint, and
that .env is byte-identical before/after.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from eval_methodology.mvp.paths import ENV_FILE, EVAL_ROOT, PROJECT_ROOT

# Paths allowed to become newly dirty during an MVP run.
_ALLOWED_NEW_DIRTY_PREFIXES = (
    "eval_methodology/",
)


@dataclass(frozen=True)
class IsolationSnapshot:
    """Point-in-time isolation evidence."""

    git_status_lines: tuple[str, ...]
    dirty_paths: frozenset[str]
    env_sha256: str | None
    env_exists: bool

    def to_dict(self) -> dict:
        return {
            "dirty_paths": sorted(self.dirty_paths),
            "env_exists": self.env_exists,
            "env_sha256": self.env_sha256,
            "git_status_line_count": len(self.git_status_lines),
        }


@dataclass
class IsolationReport:
    before: IsolationSnapshot
    after: IsolationSnapshot
    new_dirty_paths: frozenset[str] = field(default_factory=frozenset)
    disallowed_new_dirty: frozenset[str] = field(default_factory=frozenset)
    env_changed: bool = False
    ok: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "env_changed": self.env_changed,
            "new_dirty_paths": sorted(self.new_dirty_paths),
            "disallowed_new_dirty": sorted(self.disallowed_new_dirty),
            "reasons": list(self.reasons),
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
        }


def _run_git_status() -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines


def _paths_from_status(lines: list[str]) -> frozenset[str]:
    paths: set[str] = set()
    for line in lines:
        # porcelain: XY PATH or XY ORIG -> PATH
        body = line[3:] if len(line) > 3 else line
        if " -> " in body:
            body = body.split(" -> ", 1)[1]
        paths.add(body.strip())
    return frozenset(paths)


def _hash_env(path: Path = ENV_FILE) -> tuple[bool, str | None]:
    if not path.is_file():
        return False, None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return True, digest


def take_snapshot() -> IsolationSnapshot:
    lines = _run_git_status()
    exists, digest = _hash_env()
    return IsolationSnapshot(
        git_status_lines=tuple(lines),
        dirty_paths=_paths_from_status(lines),
        env_sha256=digest,
        env_exists=exists,
    )


def _is_allowed_new_path(path: str) -> bool:
    normalized = path.lstrip("./")
    return any(normalized.startswith(prefix) for prefix in _ALLOWED_NEW_DIRTY_PREFIXES)


def compare_snapshots(
    before: IsolationSnapshot,
    after: IsolationSnapshot,
) -> IsolationReport:
    new_dirty = after.dirty_paths - before.dirty_paths
    disallowed = frozenset(p for p in new_dirty if not _is_allowed_new_path(p))
    env_changed = before.env_sha256 != after.env_sha256
    reasons: list[str] = []
    if disallowed:
        reasons.append(
            "new dirty paths outside eval_methodology/: "
            + ", ".join(sorted(disallowed))
        )
    if env_changed:
        reasons.append(".env sha256 changed during run")
    ok = not disallowed and not env_changed
    return IsolationReport(
        before=before,
        after=after,
        new_dirty_paths=new_dirty,
        disallowed_new_dirty=disallowed,
        env_changed=env_changed,
        ok=ok,
        reasons=reasons,
    )


def assert_isolation(report: IsolationReport) -> None:
    if not report.ok:
        raise RuntimeError(
            "isolation violated: " + "; ".join(report.reasons or ["unknown"])
        )


def assert_milvus_collection_exists(
    *,
    host: str,
    port: int,
    collection: str,
) -> None:
    """Fail fast if the configured collection is missing. Never create it."""
    from pymilvus import connections, utility

    alias = "mvp_preflight"
    try:
        connections.connect(alias=alias, host=host, port=port, timeout=10)
        if not utility.has_collection(collection, using=alias):
            raise RuntimeError(
                f"Milvus collection {collection!r} does not exist on "
                f"{host}:{port}. Refusing to create indexes during evaluation. "
                "Rebuild indexes outside the MVP runner first."
            )
    finally:
        try:
            connections.disconnect(alias)
        except Exception:  # noqa: BLE001 - best-effort cleanup
            pass


# Re-export for callers that need the eval root constant.
__all__ = [
    "IsolationSnapshot",
    "IsolationReport",
    "take_snapshot",
    "compare_snapshots",
    "assert_isolation",
    "assert_milvus_collection_exists",
    "EVAL_ROOT",
]
