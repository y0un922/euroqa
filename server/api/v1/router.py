"""v1 router aggregator."""
from fastapi import APIRouter, Depends

from server.api.v1 import auth, documents, glossary, query, settings, sources
from server.api.v1.auth import require_auth

router = APIRouter(prefix="/api/v1")
protected = [Depends(require_auth)]

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(query.router, tags=["Query"], dependencies=protected)
router.include_router(documents.router, tags=["Documents"], dependencies=protected)
router.include_router(glossary.router, tags=["Glossary"], dependencies=protected)
router.include_router(settings.router, tags=["Settings"], dependencies=protected)
router.include_router(sources.router, tags=["Sources"], dependencies=protected)
