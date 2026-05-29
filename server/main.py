"""FastAPI application entry point."""
from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.api.debug_pipeline import router as debug_router
from server.api.v1.auth import require_auth
from server.api.v1.router import router as v1_router
from server.config import ServerConfig
from server.deps import get_config, get_retriever
from server.logging_config import configure_logging
from server.middleware.request_context import RequestContextMiddleware
from shared.llm_clients import close_async_openai_clients

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.services.task_manager import get_task_manager

    config: ServerConfig = get_config()
    configure_logging(json_mode=config.log_json)

    retriever = get_retriever()
    try:
        await retriever.initialize()
    except Exception:
        logger.error("retriever_initialize_failed", exc_info=True)
        raise

    task_manager = get_task_manager()
    await task_manager.start()
    yield
    await task_manager.stop()
    await retriever.close()
    await close_async_openai_clients()


app = FastAPI(
    title="Eurocode QA API",
    description="欧洲建筑规范智能问答系统",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request, exc: HTTPException):
    """Return the documented API error envelope for explicit business errors."""
    detail = exc.detail
    message = detail if isinstance(detail, str) else "请求处理失败"
    response_detail = None if isinstance(detail, str) else str(detail)
    return JSONResponse(
        status_code=200,
        content={
            "code": exc.status_code,
            "message": message,
            "detail": response_detail,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request, exc: RequestValidationError):
    """Map request validation failures to the external error envelope."""
    return JSONResponse(
        status_code=200,
        content={
            "code": 400,
            "message": "参数错误",
            "detail": str(exc.errors()),
        },
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(v1_router)
app.include_router(debug_router, dependencies=[Depends(require_auth)])


@app.get("/health")
async def health():
    """Liveness probe -- always returns 200 when the process is up."""
    return {"status": "ok"}


@app.get("/healthz")
async def healthz(config: ServerConfig = Depends(get_config)):
    """Readiness probe -- checks Milvus and Elasticsearch connectivity."""
    checks: dict[str, str] = {}

    # Milvus
    try:
        from pymilvus import connections as milvus_connections

        alias = "__healthz__"
        milvus_connections.connect(
            alias=alias,
            host=config.milvus_host,
            port=str(config.milvus_port),
            timeout=3,
        )
        milvus_connections.disconnect(alias)
        checks["milvus"] = "ok"
    except Exception:
        checks["milvus"] = "unavailable"

    # Elasticsearch
    try:
        from elasticsearch import Elasticsearch

        es = Elasticsearch(config.es_url, request_timeout=3)
        es.ping()
        es.close()
        checks["elasticsearch"] = "ok"
    except Exception:
        checks["elasticsearch"] = "unavailable"

    all_ok = all(v == "ok" for v in checks.values())
    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
    )
