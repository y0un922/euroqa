from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from server.config import ServerConfig
from server.core.conversation import ConversationState
from server.agents.tool_progress import ToolProgressCallback

if TYPE_CHECKING:
    from server.agents.evidence import EvidenceBundle
    from server.core.retrieval import HybridRetriever


@dataclass
class QADeps:
    """Agent runtime dependencies passed to tools through RunContextWrapper."""

    config: ServerConfig
    retriever: HybridRetriever
    glossary: dict[str, str]
    bundle: EvidenceBundle
    conversation_state: ConversationState | None = None
    domain_filter: str | None = None
    sources_filter: list[str] | None = None
    tool_progress: ToolProgressCallback | None = None
