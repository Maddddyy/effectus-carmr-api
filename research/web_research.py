"""
Adversarial web research module.
Three surgical use points in the pipeline:
  1. Post-commitment: validate strategic context, find counter-evidence
  2. Post-assumptions: test each parent assumption against current market data
  3. Post-meaning: find how contested terms are actually defined in industry/regulation
"""
import httpx
import os
import asyncio
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

EXA_API_KEY = os.getenv("EXA_API_KEY", "")


async def search_exa(query: str, num_results: int = 3) -> List[dict]:
    """Neural search via Exa AI."""
    if not EXA_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": num_results,
                    "type": "neural",
                    "contents": {"text": {"maxCharacters": 1000}},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for r in data.get("results", []):
                snippet = r.get("text", "")
                if not snippet and r.get("highlights"):
                    snippet = " ".join(r["highlights"])
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": snippet[:900],
                })
            return results
    except Exception as e:
        logger.warning(f"Exa search failed for '{query}': {e}")
        return []


def _format_results(results: List[dict], query: str) -> str:
    if not results:
        return f"[No research results for: {query}]"
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r['title']}")
        if r.get("url"):
            parts.append(f"    {r['url']}")
        if r.get("snippet"):
            parts.append(f"    {r['snippet'][:600]}")
    return "\n".join(parts)


# ── Point 1: Commitment validation ────────────────────────────────────────────

async def research_commitment(title: str, sector: str, commitment_what: str) -> str:
    """
    After commitment extraction: find COUNTER-EVIDENCE and CONTEXT.
    Two searches: (a) market/sector context (b) evidence against the strategic thesis.
    """
    queries = [
        f"{title} {sector} market size competitive landscape 2024 2025",
        f"{commitment_what[:100]} failure risks challenges evidence against",
    ]
    results_parts = []
    for q in queries:
        results = await search_exa(q, num_results=3)
        if results:
            results_parts.append(f"Query: {q}\n{_format_results(results, q)}")
    return "\n\n".join(results_parts) if results_parts else "[No research results]"


# ── Point 2: Assumption validation (adversarial) ──────────────────────────────

async def research_assumption(
    statement: str,
    falsification: str,
    commitment_title: str,
) -> str:
    """
    For each PARENT assumption: adversarially test it.
    Search for: (a) current data on the metric in the falsification condition
                (b) evidence the assumption is already at risk
    """
    # Extract the core claim from the falsification condition for targeted search
    metric_hint = falsification[:120] if falsification else statement[:120]

    queries = [
        f"{statement[:100]} current data evidence 2024 2025",
        f"{metric_hint} market research forecast latest",
    ]

    results_parts = []
    for q in queries:
        results = await search_exa(q, num_results=2)
        if results:
            results_parts.append(f"Query: {q}\n{_format_results(results, q)}")

    return "\n\n".join(results_parts) if results_parts else "[No research results]"


# ── Point 3: Meaning term validation ─────────────────────────────────────────

async def research_term_definition(term: str, industry: str) -> str:
    """
    How is this term actually defined in regulatory/governance/industry contexts?
    Find evidence of contested or inconsistent usage.
    """
    queries = [
        f'"{term}" definition {industry} regulatory governance official',
        f'"{term}" different meanings ambiguity {industry} risk',
    ]
    results_parts = []
    for q in queries:
        results = await search_exa(q, num_results=2)
        if results:
            results_parts.append(f"Query: {q}\n{_format_results(results, q)}")
    return "\n\n".join(results_parts) if results_parts else "[No research results]"
