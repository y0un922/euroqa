"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.api.v1.router import router as v1_router
from server.deps import get_retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    retriever = get_retriever()
    await retriever.close()


app = FastAPI(
    title="Eurocode QA API",
    description="欧洲建筑规范智能问答系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)
