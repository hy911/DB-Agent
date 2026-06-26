"""The Model Recommender orchestration (plan-execute).

extract criteria (LLM) → resolve genes (deterministic) → fetch candidate sets per
criterion concurrently → score & rank (pure) → fetch efficacy evidence for the
top-N → write a persuasive NL summary (LLM). Reuses the shared tool layer via Deps
(replica, resolve_gene, llm); DB stays sync via asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import dataclasses

from db_agent.db import recommend_queries as q
from db_agent.graph.state import Deps
from db_agent.llm import extract_criteria, recommend_summary
from db_agent.mas.recommender.model import Criteria, RankedModel, Recommendation
from db_agent.mas.recommender.scoring import Signal, rank_models


def _is_zh(text: str) -> bool:
    return any("一" <= c <= "鿿" for c in text)


def _no_criteria_note(question: str) -> str:
    return (
        "未能从您的描述中识别出明确的筛选条件，请提供靶点基因、突变、表达高低或适应症/模型类型等信息。"
        if _is_zh(question)
        else "No selection criteria could be extracted; please specify a target gene, "
        "mutation, expression level, indication or model type."
    )


def _no_match_note(question: str) -> str:
    return (
        "未找到符合所给条件的模型，建议放宽其中一项条件后重试。"
        if _is_zh(question)
        else "No models matched the given criteria; consider relaxing one of them."
    )


async def _resolve_symbol(deps: Deps, name: str) -> str | None:
    res = await asyncio.to_thread(deps.resolve_gene, deps.replica, name)
    return res.symbol if res.status == "resolved" else None


def _table_preview(models: list[RankedModel]) -> str:
    lines = []
    for i, m in enumerate(models, 1):
        label = m.model_id or m.model_name or m.model_uuid
        attrs = ", ".join(x for x in (m.model_type, m.cancer_type) if x)
        ev = (
            "; ".join(f"{r.get('drug_name')} TGI={r.get('tgi_tv')}" for r in m.evidence[:5])
            if m.evidence
            else "无"
        )
        lines.append(
            f"{i}. {label} ({attrs}) — 匹配度 {m.score}，命中: {('; '.join(m.matched)) or '无'} "
            f"— 药效证据({len(m.evidence)}条): {ev}"
        )
    return "\n".join(lines)


async def run_recommendation(question: str, *, deps: Deps, top_n: int = 3) -> Recommendation:
    md = deps.layer.get_table("model_desc_info")
    cancer_types = list(md.columns["cancer_type"].values) if md else []
    model_types = list(md.columns["model_type"].values) if md else []

    raw = await extract_criteria(deps.llm, deps.settings, question, cancer_types, model_types)
    criteria = Criteria.from_json(raw)
    if criteria.is_empty():
        return Recommendation(
            question, criteria, (), summary=_no_criteria_note(question), notes=("no_criteria",)
        )

    notes: list[str] = []
    resolved_mut: list[tuple[str, str]] = []
    for g in criteria.mutated_genes:
        sym = await _resolve_symbol(deps, g)
        (resolved_mut.append((g, sym)) if sym else notes.append(f"未能解析基因 {g}"))
    resolved_expr: list[tuple[str, str, str]] = []  # (raw_gene, direction, symbol)
    for ec in criteria.expression:
        sym = await _resolve_symbol(deps, ec.gene)
        (
            resolved_expr.append((ec.gene, ec.direction, sym))
            if sym
            else notes.append(f"未能解析基因 {ec.gene}")
        )

    # candidate sets per criterion, concurrently (sync fetch off the event loop)
    mut_rows = await asyncio.gather(
        *(asyncio.to_thread(q.models_with_mutation, deps.replica, sym) for _, sym in resolved_mut)
    )
    expr_rows = await asyncio.gather(
        *(
            asyncio.to_thread(q.models_with_expression, deps.replica, sym, direction)
            for _, direction, sym in resolved_expr
        )
    )

    signals: list[Signal] = []
    tiebreak: dict[str, float] = {}
    for (raw_g, _sym), uuids in zip(resolved_mut, mut_rows, strict=True):
        signals.append((f"{raw_g} 突变", frozenset(uuids)))
    for (raw_g, direction, _sym), pairs in zip(resolved_expr, expr_rows, strict=True):
        word = "高" if direction == "high" else "低"
        signals.append((f"{raw_g} {word}表达", frozenset(u for u, _ in pairs)))
        n = len(pairs) or 1
        for idx, (u, _val) in enumerate(pairs):
            tiebreak[u] = tiebreak.get(u, 0.0) + (n - idx) / n  # strongest expresser ≈ 1.0

    pool: set[str] = set()
    for _, uuids in signals:
        pool |= uuids
    if criteria.cancer_type or criteria.model_type:
        seed = await asyncio.to_thread(
            q.models_with_attributes, deps.replica, criteria.cancer_type, criteria.model_type
        )
        pool |= set(seed)

    if not pool:
        return Recommendation(
            question, criteria, (), summary=_no_match_note(question), notes=tuple(notes)
        )

    details = await asyncio.to_thread(q.model_details, deps.replica, list(pool))
    if criteria.cancer_type:
        ct = criteria.cancer_type
        signals.append(
            (
                f"瘤种 {ct}",
                frozenset(u for u, d in details.items() if str(d.get("cancer_type")) == ct),
            )
        )
    if criteria.model_type:
        mt = criteria.model_type
        signals.append(
            (
                f"模型类型 {mt}",
                frozenset(u for u, d in details.items() if str(d.get("model_type")) == mt),
            )
        )

    ranked = rank_models(signals, details, tiebreak=tiebreak, top_n=top_n)
    enriched = [
        dataclasses.replace(
            m,
            evidence=tuple(
                await asyncio.to_thread(q.efficacy_evidence, deps.replica, m.model_uuid)
            ),
        )
        for m in ranked
    ]

    summary = await recommend_summary(deps.llm, deps.settings, question, _table_preview(enriched))
    return Recommendation(question, criteria, tuple(enriched), summary=summary, notes=tuple(notes))
