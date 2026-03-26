"""POST /api/v1/query — main Q&A endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from server.deps import get_config, get_conversation_manager, get_glossary, get_retriever
from server.core.query_understanding import analyze_query
from server.core.generation import generate_answer
from server.models.schemas import QueryRequest, QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query(
    req: QueryRequest,
    config=Depends(get_config),
    retriever=Depends(get_retriever),
    glossary=Depends(get_glossary),
    conv_mgr=Depends(get_conversation_manager),
) -> QueryResponse:
    analysis = await analyze_query(req.question, glossary, config)

    filters = analysis.filters
    if req.domain:
        filters["source"] = req.domain

    result = await retriever.retrieve(
        query=analysis.rewritten_query,
        intent=analysis.intent,
        filters=filters,
    )

    conv = conv_mgr.get_or_create(req.conversation_id)

    response = await generate_answer(
        question=req.question,
        chunks=result.chunks,
        parent_chunks=result.parent_chunks,
        glossary_terms=analysis.matched_terms,
        conversation_history=conv.history,
        config=config,
    )
    response.conversation_id = conv.conversation_id

    conv_mgr.add_turn(conv.conversation_id, req.question, response.answer)

    return response
