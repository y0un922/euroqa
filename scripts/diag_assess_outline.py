"""Diagnose why assessment returns empty and outline times out.

Reproduces the exact decompose/assessment/outline LLM calls against the
configured DashScope models and prints finish_reason + content + reasoning_content
so we can see whether reasoning tokens are eating the output budget.
"""
from __future__ import annotations

import asyncio
import json
import time

from openai import AsyncOpenAI

from server.agents.decompose import _ASSESSMENT_PROMPT, _OUTLINE_PROMPT, _SYSTEM_PROMPT
from server.config import ServerConfig


async def _call(client, model, system, user, max_tokens, timeout):
    t0 = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.0,
                max_tokens=max_tokens,
            ),
            timeout=timeout,
        )
    except Exception as exc:
        print(f"  CALL FAILED in {time.perf_counter()-t0:.1f}s: {type(exc).__name__}: {exc}")
        return
    dt = time.perf_counter() - t0
    choice = resp.choices[0]
    content = choice.message.content or ""
    rc = getattr(choice.message, "reasoning_content", None) or ""
    print(f"  elapsed={dt:.1f}s finish_reason={choice.finish_reason}")
    print(f"  content len={len(content)}  reasoning_content len={len(rc)}")
    print(f"  content[:120]={content[:120]!r}")
    print(f"  reasoning[:160]={rc[:160]!r}")
    if resp.usage:
        print(f"  usage={resp.usage}")
    # provider-specific raw dump
    try:
        print(f"  raw_message_keys={list(choice.message.model_dump().keys())}")
    except Exception:
        pass


async def main():
    cfg = ServerConfig()
    print(f"decompose model = {cfg.resolved_decompose_llm_model}  base={cfg.resolved_decompose_llm_base_url}")
    print(f"agent model      = {cfg.resolved_agent_llm_model}  base={cfg.resolved_agent_llm_base_url}")

    dec_client = AsyncOpenAI(
        api_key=cfg.resolved_decompose_llm_api_key,
        base_url=cfg.resolved_decompose_llm_base_url,
    )
    agent_client = AsyncOpenAI(
        api_key=cfg.resolved_agent_llm_api_key,
        base_url=cfg.resolved_agent_llm_base_url,
    )

    evidence = ("[Ref-1] EN 1992-1-1 | 3.1 Concrete | p.42 | " + ("concrete strength fck fcm fctm modulus " * 40) + "\n") * 60
    evidence = evidence[:12000]
    print(f"\nevidence len = {len(evidence)}")

    # 1. decompose (small input) - baseline, should succeed
    print("\n[1] DECOMPOSE (deepseek-v4-flash, max_tokens=500, small input)")
    await _call(
        dec_client, cfg.resolved_decompose_llm_model, _SYSTEM_PROMPT,
        json.dumps({"question": "混凝土结构设计作用荷载和材料分项系数", "history": [], "glossary_terms": {}}, ensure_ascii=False),
        max_tokens=500, timeout=30,
    )

    # 2. assessment (12k evidence input, max_tokens=600) - the failing one
    print("\n[2] ASSESSMENT (deepseek-v4-flash, max_tokens=600, 12k evidence)")
    await _call(
        dec_client, cfg.resolved_decompose_llm_model, _ASSESSMENT_PROMPT,
        json.dumps({"question": "混凝土分项系数", "rewritten_question": "concrete partial factors", "implicit_context": "", "previous_queries": [], "evidence": evidence}, ensure_ascii=False),
        max_tokens=600, timeout=30,
    )

    # 3. assessment with larger max_tokens (test the budget hypothesis)
    print("\n[3] ASSESSMENT (deepseek-v4-flash, max_tokens=3000, 12k evidence)")
    await _call(
        dec_client, cfg.resolved_decompose_llm_model, _ASSESSMENT_PROMPT,
        json.dumps({"question": "混凝土分项系数", "rewritten_question": "concrete partial factors", "implicit_context": "", "previous_queries": [], "evidence": evidence}, ensure_ascii=False),
        max_tokens=3000, timeout=60,
    )

    # 4. outline (qwen3.6-flash, 12k evidence, max_tokens=900)
    print("\n[4] OUTLINE (qwen3.6-flash, max_tokens=900, 12k evidence)")
    await _call(
        agent_client, cfg.resolved_agent_llm_model, _OUTLINE_PROMPT,
        json.dumps({"question": "混凝土分项系数", "rewritten_question": "concrete partial factors", "implicit_context": "", "history": [], "evidence": evidence}, ensure_ascii=False),
        max_tokens=900, timeout=40,
    )


if __name__ == "__main__":
    asyncio.run(main())