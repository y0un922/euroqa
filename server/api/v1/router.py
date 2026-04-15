"""v1 router aggregator."""
from fastapi import APIRouter

from server.api.v1 import documents, glossary, query, settings, sources

router = APIRouter(prefix="/api/v1")
router.include_router(query.router, tags=["Query"])
router.include_router(documents.router, tags=["Documents"])
router.include_router(glossary.router, tags=["Glossary"])
router.include_router(settings.router, tags=["Settings"])
router.include_router(sources.router, tags=["Sources"])
