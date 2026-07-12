"""Reproduce assessment empty-content with DIVERSE evidence (simulates real 23-chunk run)."""
from __future__ import annotations

import asyncio
import json
import time

from openai import AsyncOpenAI

from server.agents.decompose import _ASSESSMENT_PROMPT
from server.config import ServerConfig

DIVERSE_CHUNKS = [
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "6.4.3.2 稳定及静平衡验算 (1) 在考虑静平衡验算时，应考虑不利作用的不利方向偏差。对于刚性结构，作用偏差可通过增大作用的标准值来考虑。"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "(2) 对应 EQU 静平衡验算，γG=1.10（不利），γQ=1.50（不利）"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "6.4.3.2 STR/GEO 持久/瞬态 EQU 的最小值组合公式 6.10 / 6.10a / 6.10b"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "3.1.6 混凝土设计强度 fcd = αcc fck / γc，αcc 为系数，γc 为混凝土分项系数"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "(2) γc = 1.5（持久/瞬态），γc = 1.2（偶然）"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "3.1.6 (3) fctd = αct fctk / γc，αct 取 1.0"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "2.4.2.4 钢筋 fyd = fyk / γs，γs = 1.15（持久/瞬态）"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "(2) 偶然组合 γs = 1.0"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "表 A1.2(B) STR/GEO 持久/瞬态：γG=1.35 不利，γQ=1.50 不利"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "表 A1.2(C) STR 静平衡：γG=1.0 不利/0.95 有利"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "弹性模量 Ecm 由表 3.1 给出，与 fcm 相关"),
    ("EN 1992-1-1 | 3.1.7 | p.40", "3.1.7 截面设计应力-应变关系：λ=0.8 η=1.0（≤C50/60）"),
    ("EN 1992-1-1 | 3.1.7 | p.40", "矩形应力块 λ=fck 减小系数，η=1 - (fck-50)/400（>C50）"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "6.4.3.2(4) 作用组合 6.10a: γG·Gk + ψ0·γQ·Qk；6.10b: 0.85γG·Gk + 1.5γQ·Qk"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "2.4.2.4(1) 混凝土和钢筋分项系数适用于极限状态 STR/GEO"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "fck 为特征圆柱体抗压强度，C30/37 即 fck=30MPa"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "EQU 验算结构整体稳定，γG=1.10 不利方向"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "表 2.1N 混凝土 γc：持久/瞬态 1.5，偶然 1.2"),
    ("EN 1992-1-1 | 2.4.2.4 | p.29", "表 2.1N 钢筋 γs：持久/瞬态 1.15，偶然 1.0"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "A1.2.1 适用性 SLS 组合系数 ψ1 ψ2 ψ3"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "αcc 推荐 1.0，国家附录可改（UK 取 0.85）"),
    ("EN 1990:2002 | 6.4.3.2(2) | p.48", "γF·Fk = γG·Gk + γQ·Qk，γF 为作用分项系数"),
    ("EN 1992-1-1 | 3.1.6 | p.39", "fcd 用于截面承载力计算，γc 体现材料强度不确定性"),
]


async def _call(client, model, system, user, max_tokens, timeout):
    t0 = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.0, max_tokens=max_tokens,
            ), timeout=timeout)
    except Exception as exc:
        print(f"  FAILED {time.perf_counter()-t0:.1f}s: {type(exc).__name__}: {exc}")
        return
    dt = time.perf_counter()-t0
    c = resp.choices[0]
    content = c.message.content or ""
    rc = getattr(c.message, "reasoning_content", None) or ""
    print(f"  max_tokens={max_tokens} elapsed={dt:.1f}s finish_reason={c.finish_reason}")
    print(f"  content_len={len(content)} reasoning_len={len(rc)} reasoning_tokens={getattr(resp.usage.completion_tokens_details,'reasoning_tokens',None)} completion_tokens={resp.usage.completion_tokens if resp.usage else None}")
    print(f"  content[:200]={content[:200]!r}")


async def main():
    cfg = ServerConfig()
    client = AsyncOpenAI(api_key=cfg.resolved_decompose_llm_api_key, base_url=cfg.resolved_decompose_llm_base_url)
    evidence = "\n".join(f"[Ref-{i+1}] {src}\n{txt}" for i,(src,txt) in enumerate(DIVERSE_CHUNKS))
    print(f"evidence_len={len(evidence)} chunks={len(DIVERSE_CHUNKS)}")
    payload = {"question": "请给出混凝土结构设计中相关作用荷载和材料的分项系数。", "rewritten_question": "partial factors for actions and materials in concrete structure design", "implicit_context": "", "previous_queries": ["EN 1990 partial factors actions","EN 1992-1-1 partial factors materials"], "evidence": evidence[:12000]}
    user = json.dumps(payload, ensure_ascii=False)
    for mt in (600, 1500, 3000):
        print(f"\n--- ASSESSMENT diverse evidence, max_tokens={mt} ---")
        await _call(client, cfg.resolved_decompose_llm_model, _ASSESSMENT_PROMPT, user, mt, timeout=40)

if __name__ == "__main__":
    asyncio.run(main())