"""Persistent pipeline debug run snapshots and history."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    """Serialize dataclasses and enums into JSON-friendly objects."""
    if is_dataclass(value):
        return asdict(value)
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return enum_value
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


class PipelineDebugStore:
    """Read persisted pipeline debug runs and artifacts."""

    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir)

    def list_runs(self) -> list[dict[str, Any]]:
        """Return all runs sorted by newest first."""
        if not self.root_dir.exists():
            return []
        runs: list[dict[str, Any]] = []
        for manifest_path in self.root_dir.glob("*/manifest.json"):
            try:
                runs.append(json.loads(manifest_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        runs.sort(key=lambda run: run.get("started_at", ""), reverse=True)
        return runs

    def get_run(self, run_id: str) -> dict[str, Any]:
        """Load a single run manifest."""
        manifest_path = self.root_dir / run_id / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(run_id)
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def read_text_artifact(self, run_id: str, relative_path: str) -> str:
        """Read a text artifact from a run directory."""
        path = self.root_dir / run_id / relative_path
        if not path.exists():
            raise FileNotFoundError(relative_path)
        return path.read_text(encoding="utf-8")

    def read_json_artifact(self, run_id: str, relative_path: str) -> Any:
        """Read a JSON artifact from a run directory."""
        return json.loads(self.read_text_artifact(run_id, relative_path))


class PipelineDebugRecorder:
    """Persist pipeline stage state, artifacts, and events for debug UI."""

    def __init__(self, root_dir: Path, run_id: str):
        self.root_dir = root_dir
        self.run_id = run_id
        self.run_dir = self.root_dir / self.run_id
        self.artifacts_dir = self.run_dir / "artifacts"
        self.manifest_path = self.run_dir / "manifest.json"
        self.events_path = self.run_dir / "events.jsonl"
        self.manifest: dict[str, Any] = {
            "run_id": self.run_id,
            "status": "running",
            "started_at": _utc_now(),
            "updated_at": _utc_now(),
            "current_stage": None,
            "current_document_id": None,
            "stages": {},
            "documents": {},
            "global_artifacts": [],
            "summary": {},
        }

    @classmethod
    def create(cls, root_dir: Path | str) -> "PipelineDebugRecorder":
        """Create a new recorder instance and initialize on-disk state."""
        root = Path(root_dir)
        run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
        recorder = cls(root, run_id)
        recorder.run_dir.mkdir(parents=True, exist_ok=True)
        recorder.artifacts_dir.mkdir(parents=True, exist_ok=True)
        recorder._save_manifest()
        recorder._append_event("run_created", {"run_id": run_id})
        return recorder

    @staticmethod
    def serialize_tree(node: Any) -> dict[str, Any]:
        """Serialize a DocumentNode tree recursively."""
        return {
            "title": node.title,
            "content": node.content,
            "element_type": getattr(node.element_type, "value", str(node.element_type)),
            "level": node.level,
            "page_numbers": list(node.page_numbers),
            "page_file_index": list(getattr(node, "page_file_index", [])),
            "clause_ids": list(node.clause_ids),
            "cross_refs": list(node.cross_refs),
            "source": node.source,
            "children": [PipelineDebugRecorder.serialize_tree(child) for child in node.children],
        }

    @staticmethod
    def serialize_chunks(chunks: list[Any]) -> dict[str, Any]:
        """Serialize chunk list and summary counts."""
        counts: dict[str, int] = {}
        serialized_chunks = []
        for chunk in chunks:
            payload = chunk.model_dump()
            element_type = payload["metadata"]["element_type"]
            counts[element_type] = counts.get(element_type, 0) + 1
            serialized_chunks.append(payload)
        return {
            "total": len(serialized_chunks),
            "counts": counts,
            "chunks": serialized_chunks,
        }

    def start_stage(
        self,
        stage: str,
        *,
        document_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Mark a stage as running."""
        target = self._get_stage_container(stage, document_id)
        target["status"] = "running"
        target["started_at"] = target.get("started_at", _utc_now())
        if summary is not None:
            target["summary"] = summary
        self.manifest["current_stage"] = stage
        self.manifest["current_document_id"] = document_id
        self._touch_manifest()
        self._append_event("stage_started", {"stage": stage, "document_id": document_id, "summary": summary or {}})

    def update_stage(
        self,
        stage: str,
        *,
        document_id: str | None = None,
        summary: dict[str, Any] | None = None,
        event_type: str = "stage_progress",
    ) -> None:
        """Update stage summary while it is running."""
        target = self._get_stage_container(stage, document_id)
        target["status"] = target.get("status", "running")
        if summary is not None:
            target["summary"] = summary
        self.manifest["current_stage"] = stage
        self.manifest["current_document_id"] = document_id
        self._touch_manifest()
        self._append_event(event_type, {"stage": stage, "document_id": document_id, "summary": summary or {}})

    def complete_stage(
        self,
        stage: str,
        *,
        document_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Mark a stage as completed."""
        target = self._get_stage_container(stage, document_id)
        target["status"] = "completed"
        target["completed_at"] = _utc_now()
        if summary is not None:
            target["summary"] = summary
        self.manifest["current_stage"] = stage
        self.manifest["current_document_id"] = document_id
        self._touch_manifest()
        self._append_event("stage_completed", {"stage": stage, "document_id": document_id, "summary": summary or {}})

    def fail_stage(
        self,
        stage: str,
        *,
        document_id: str | None = None,
        error: str,
    ) -> None:
        """Mark a stage as failed."""
        target = self._get_stage_container(stage, document_id)
        target["status"] = "failed"
        target["completed_at"] = _utc_now()
        target["error"] = error
        self.manifest["status"] = "failed"
        self.manifest["current_stage"] = stage
        self.manifest["current_document_id"] = document_id
        self._touch_manifest()
        self._append_event("stage_failed", {"stage": stage, "document_id": document_id, "error": error})

    def record_text_artifact(
        self,
        *,
        document_id: str | None,
        stage: str,
        filename: str,
        label: str,
        content: str,
        content_type: str,
    ) -> str:
        """Persist a text artifact and register it in the manifest."""
        relative_path = self._artifact_relative_path(document_id, filename)
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._register_artifact(stage, document_id, label, relative_path, content_type)
        return relative_path

    def record_json_artifact(
        self,
        *,
        document_id: str | None,
        stage: str,
        filename: str,
        label: str,
        payload: Any,
    ) -> str:
        """Persist a JSON artifact and register it in the manifest."""
        relative_path = self._artifact_relative_path(document_id, filename)
        path = self.run_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        self._register_artifact(stage, document_id, label, relative_path, "application/json")
        return relative_path

    def complete_run(self, *, summary: dict[str, Any] | None = None) -> None:
        """Finalize the run as completed."""
        self.manifest["status"] = "completed"
        self.manifest["completed_at"] = _utc_now()
        self.manifest["current_stage"] = None
        self.manifest["current_document_id"] = None
        if summary is not None:
            self.manifest["summary"] = summary
        self._touch_manifest()
        self._append_event("run_completed", {"summary": summary or {}})

    def fail_run(self, *, error: str) -> None:
        """Finalize the run as failed."""
        self.manifest["status"] = "failed"
        self.manifest["completed_at"] = _utc_now()
        self.manifest["error"] = error
        self._touch_manifest()
        self._append_event("run_failed", {"error": error})

    def _artifact_relative_path(self, document_id: str | None, filename: str) -> str:
        if document_id:
            return f"artifacts/{document_id}/{filename}"
        return f"artifacts/_global/{filename}"

    def _register_artifact(
        self,
        stage: str,
        document_id: str | None,
        label: str,
        relative_path: str,
        content_type: str,
    ) -> None:
        artifact = {
            "label": label,
            "path": relative_path,
            "content_type": content_type,
        }
        target = self._get_stage_container(stage, document_id)
        target.setdefault("artifacts", []).append(artifact)
        self._touch_manifest()
        self._append_event("artifact_recorded", {"stage": stage, "document_id": document_id, "artifact": artifact})

    def _get_stage_container(self, stage: str, document_id: str | None) -> dict[str, Any]:
        if document_id:
            document = self.manifest["documents"].setdefault(
                document_id,
                {"title": document_id, "stages": {}},
            )
            return document["stages"].setdefault(stage, {})
        return self.manifest["stages"].setdefault(stage, {})

    def _touch_manifest(self) -> None:
        self.manifest["updated_at"] = _utc_now()
        self._save_manifest()

    def _save_manifest(self) -> None:
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "timestamp": _utc_now(),
            "event": event_type,
            **payload,
        }
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, default=_json_default) + "\n")
