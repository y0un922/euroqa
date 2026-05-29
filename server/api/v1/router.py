"""v1 router aggregator."""
from fastapi import APIRouter, Depends
from fastapi.routing import APIRoute

from server.api.v1 import auth, documents, glossary, query, settings, sources
from server.api.v1.auth import require_auth

router = APIRouter(prefix="/api/v1")
protected = [Depends(require_auth)]


def _include_public_contract_routes(
    source_router: APIRouter,
    *,
    public_routes: set[tuple[str, str]],
    tags: list[str],
) -> None:
    """Include selected external contract routes without auth and protect the rest."""
    public_router = APIRouter()
    protected_router = APIRouter()

    for route in source_router.routes:
        if isinstance(route, APIRoute):
            is_public = any(
                method in route.methods and path == route.path
                for method, path in public_routes
            )
        else:
            is_public = False
        (public_router if is_public else protected_router).routes.append(route)

    router.include_router(public_router, tags=tags)
    router.include_router(protected_router, tags=tags, dependencies=protected)


router.include_router(auth.router, prefix="/auth", tags=["Auth"])
_include_public_contract_routes(
    query.router,
    public_routes={("POST", "/query/stream")},
    tags=["Query"],
)
_include_public_contract_routes(
    documents.router,
    public_routes={
        ("POST", "/documents/parse"),
        ("POST", "/documents/status"),
        ("POST", "/documents/delete"),
    },
    tags=["Documents"],
)
router.include_router(glossary.router, tags=["Glossary"], dependencies=protected)
router.include_router(settings.router, tags=["Settings"], dependencies=protected)
_include_public_contract_routes(
    sources.router,
    public_routes={("POST", "/translate")},
    tags=["Sources"],
)
