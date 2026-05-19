"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.api.debug_pipeline import router as debug_router
from server.api.v1.auth import require_auth
from server.api.v1.router import router as v1_router
from server.deps import get_retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    from server.services.task_manager import get_task_manager
    task_manager = get_task_manager()
    await task_manager.start()
    yield
    await task_manager.stop()
    retriever = get_retriever()
    await retriever.close()


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

app.include_router(v1_router)
app.include_router(debug_router, dependencies=[Depends(require_auth)])
