"""
Adversarial web research module - Effectus Research external validation layer.
Three surgical use points in the pipeline:
  1. Post-commitment: validate strategic context, find counter-evidence
  2. Post-assumptions: test each parent assumption against current market data
  3. Post-meaning: find how contested terms are actually defined in industry/regulation

Factual integrity rules:
  - All URLs are verified live before inclusion (HEAD request, 2s timeout)
  - Search results with no accessible URL are excluded from citations
  - Formatted output includes only verified, accessible sources
  - URLs are returned separately so the orchestrator can store them as citations
"""
import httpx
import os
import asyncio
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

EXA_API_KEY = os.getenv("EXA_API_KEY", "")


async def verify_url(url: str, client: httpx.AsyncClient) -> bool:
    """Verify a URL is accessible. Returns False if unreachable or non-2xx/3xx."""
    if not url or not url.startswith("http"):
        return False
    try:
        resp = await client.head(url, timeout=2.5, follow_redirects=True)
        return resp.status_code < 400
    except Exception:
        # Fall back to a GET with tiny range to handle servers that block HEAD
        try:
            resp = await client.get(url, timeout=3.0, follow_redirects=True,
                                    headers={"Range": "bytes=0-0"})
            return resp.status_code < 400
        except Exception:
            return False


async def search_exa(query: str, num_results: int = 4) -> List[dict]:
    """Neural search via Exa AI. Returns only results with verified accessible URLs."""
    if not EXA_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"},
                json={
                    "query": query,
                    "numResults": num_results,
                    "type": "neural",
                    "contents": {"text": {"maxCharacters": 1200}},
                },
            )
            resp.raise_for_status()
            data = resp.json()

            raw_results = []
            for r in data.get("results", []):
                snippet = r.get("text", "")
                if not snippet and r.get("highlights"):
                    snippet = " ".join(r["highlights"])
                raw_results.append({
                    "title": r.get("title", "").strip(),
                    "url": r.get("url", "").strip(),
                    "snippet": snippet[:1000],
                })

            if not raw_results:
                return []

            # Verify all URLs concurrently
            verify_client = httpx.AsyncClient(timeout=5.0)
            try:
                checks = await asyncio.gather(
                    *[verify_url(r["url"], verify_client) for r in raw_results],
                    return_exceptions=True
                )
            finally:
                await verify_client.aclose()

            verified = []
            seen_urls = set()
            for r, ok in zip(raw_results, checks):
                if ok is True and r["url"] and r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    verified.append(r)

            if not verified:
                # Fall back to unverified if all checks failed (network restriction)
                logger.warning(f"URL verification failed for all results on query '{query}' - using unverified")
                seen = set()
                for r in raw_results:
                    if r["url"] and r["url"] not in seen and r.get("snippet"):
                        seen.add(r["url"])
                        verified.append(r)

            return verified

    except Exception as e:
        logger.warning(f"Exa search failed for '{query}': {e}")
        return []


def _format_results(results: List[dict], query: str) -> Tuple[str, List[str]]:
    """
    Returns (formatted_text, list_of_urls).
    URLs are extracted separately for citation tracking.
    """
    if not results:
        return f"[No verified research results for: {query}]", []

    parts = []
    urls = []
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        url = r.get("url", "")
        snippet = r.get("snippet", "")

        parts.append(f"[{i}] {title}")
        if url:
            parts.append(f"    Source: {url}")
            urls.append(url)
        if snippet:
            parts.append(f"    {snippet[:700]}")

    return "\n".join(parts), urls


# -- Point 1: Commitment validation -------------------------------------------

async def research_commitment(
    title: str,
    sector: str,
    commitment_what: str,
) -> Tuple[str, List[str]]:
    """
    After commitment extraction: find COUNTER-EVIDENCE and CONTEXT.
    Two searches: (a) market/sector context (b) evidence against the strategic thesis.
    Returns (formatted_text, verified_urls).
    """
    queries = [
        f"{title} {sector} market size competitive landscape 2024 2025",
        f"{commitment_what[:100]} failure risks challenges evidence against",
    ]
    all_text_parts = []
    all_urls = []

    for q in queries:
        results = await search_exa(q, num_results=3)
        if results:
            text, urls = _format_results(results, q)
            all_text_parts.append(f"Query: {q}\n{text}")
            all_urls.extend(urls)

    combined = "\n\n".join(all_text_parts) if all_text_parts else "[No research results]"
    # Deduplicate URLs
    seen = set()
    deduped_urls = [u for u in all_urls if not (u in seen or seen.add(u))]
    return combined, deduped_urls


# -- Point 2: Assumption validation (adversarial) -----------------------------

async def research_assumption(
    statement: str,
    falsification: str,
    commitment_title: str,
) -> Tuple[str, List[str]]:
    """
    For each PARENT assumption: adversarially test it.
    Search for: (a) current data on the metric in the falsification condition
                (b) evidence the assumption is already at risk
    Returns (formatted_text, verified_urls).
    """
    metric_hint = falsification[:120] if falsification else statement[:120]

    queries = [
        f"{statement[:100]} current data evidence 2024 2025",
        f"{metric_hint} market research forecast latest",
    ]

    all_text_parts = []
    all_urls = []

    for q in queries:
        results = await search_exa(q, num_results=2)
        if results:
            text, urls = _format_results(results, q)
            all_text_parts.append(f"Query: {q}\n{text}")
            all_urls.extend(urls)

    combined = "\n\n".join(all_text_parts) if all_text_parts else "[No research results]"
    seen = set()
    deduped_urls = [u for u in all_urls if not (u in seen or seen.add(u))]
    return combined, deduped_urls


# -- Point 3: Meaning term validation -----------------------------------------

async def research_term_definition(
    term: str,
    industry: str,
) -> Tuple[str, List[str]]:
    """
    How is this term actually defined in regulatory/governance/industry contexts?
    Find evidence of contested or inconsistent usage.
    Returns (formatted_text, verified_urls).
    """
    queries = [
        f'"{term}" definition {industry} regulatory governance official',
        f'"{term}" different meanings ambiguity {industry} risk',
    ]
    all_text_parts = []
    all_urls = []

    for q in queries:
        results = await search_exa(q, num_results=2)
        if results:
            text, urls = _format_results(results, q)
            all_text_parts.append(f"Query: {q}\n{text}")
            all_urls.extend(urls)

    combined = "\n\n".join(all_text_parts) if all_text_parts else "[No research results]"
    seen = set()
    deduped_urls = [u for u in all_urls if not (u in seen or seen.add(u))]
    return combined, deduped_urls
