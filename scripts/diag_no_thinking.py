"""Test whether extra_body enable_thinking=False disables reasoning and speeds up."""
from __future__ import annotations

import asyncio, json, time
from openai import AsyncOpenAI
from server.agents.decompose import _ASSESSMENT_PROMPT, _OUTLINE_PROMPT
from server.config import ServerConfig

DIVERSE = [
    ("EN 1990 | 6.4.3.2 | p.48", "EQU γG=1.10 不利; STR/GEO γG=1.35 γQ=1.50"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "γc=1.5 持久/瞬态, γc=1.2 偶然; γs=1.15 持久, 1.0 偶然"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "fcd = αcc fck / γc; αcc 推荐 1.0 (UK 0.85)"),
    ("EN 1990 | A1.2 | p.55", "表 A1.2(B) STR/GEO; 6.10a/6.10b 组合"),
] * 6  # ~24 chunks

async def _call(client, model, system, user, max_tokens, extra):
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model, messages=[{"role":"system","content":system},{"role":"user","content":user}],
        temperature=0.0, max_tokens=max_tokens, extra_body=extra,
    )
    dt = time.perf_counter()-t0
    c = resp.choices[0]
    content = c.message.content or ""
    rc = getattr(c.message, "reasoning_content", None) or ""
    rt = getattr(resp.usage.completion_tokens_details, "reasoning_tokens", None) if resp.usage else None
    print(f"  extra={extra} elapsed={dt:.1f}s finish={c.finish_reason} content_len={len(content)} reasoning_len={len(rc)} reasoning_tokens={rt}")
    print(f"  content[:140]={content[:140]!r}")

async def main():
    cfg = ServerConfig()
    dec = AsyncOpenAI(api_key=cfg.resolved_decompose_llm_api_key, base_url=cfg.resolved_decompose_llm_base_url)
    agt = AsyncOpenAI(api_key=cfg.resolved_agent_llm_api_key, base_url=cfg.resolved_agent_llm_base_url)
    ev = "\n".join(f"[Ref-{i+1}] {s}\n{t}" for i,(s,t) in enumerate(DIVERSE))[:12000]
    assess_user = json.dumps({"question":"混凝土分项系数","rewritten_question":"concrete partial factors","implicit_context":"","previous_queries":[],"evidence":ev}, ensure_ascii=False)
    outline_user = json.dumps({"question":"混凝土分项系数","rewritten_question":"concrete partial factors","implicit_context":"","history":[],"evidence":ev}, ensure_ascii=False)

    print("\n[ASSESS deepseek-v4-flash] thinking ON (default)")
    await _call(dec, cfg.resolved_decompose_llm_model, _ASSESSMENT_PROMPT, assess_user, 600, None)
    print("\n[ASSESS deepseek-v4-flash] extra_body enable_thinking=False")
    await _call(dec, cfg.resolved_decompose_llm_model, _ASSESSMENT_PROMPT, assess_user, 600, {"enable_thinking": False})

    print("\n[OUTLINE qwen3.6-flash] thinking ON (default)")
    await _call(agt, cfg.resolved_agent_llm_model, _OUTLINE_PROMPT, outline_user, 900, None)
    print("\n[OUTLINE qwen3.6-flash] extra_body enable_thinking=False")
    await _call(agt, cfg.resolved_agent_llm_model, _OUTLINE_PROMPT, outline_user, 900, {"enable_thinking": False})

if __name__ == "__main__":
    asyncio.run(main())