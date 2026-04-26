"""
Pipeline Orchestrator - 8-stage argumentation analysis pipeline.
All analysis is performed by Effectus Research.
Research is used SURGICALLY at 3 points only.
Each stage: extract, adversarial QC, (targeted research), revise, validate.
"""
import asyncio
import json
import time
import logging
from typing import AsyncGenerator, List, Tuple

from .ingest import parse_document, truncate_for_context, combine_documents
from .stages import (
    run_preanalysis,
    run_commitment,
    run_assumptions,
    run_reasoning,
    run_meaning,
    run_review,
    run_cross_validation,
)
from .llm_client import research_and_revise
from models.carmr_schema import CARMRRecord, ExtractionResult, RecordData, Assumption, ReasoningBlock, MeaningTerm, ReviewTrigger
from research.web_research import research_commitment, research_assumption, research_term_definition
from prompts.carmr_framework import get_stage_system_prompt

logger = logging.getLogger(__name__)

QUALITY_THRESHOLD = 0.70
MAX_RETRIES = 2


def sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def run_pipeline(
    job_id: str,
    files: List[Tuple[str, bytes]],
) -> AsyncGenerator[str, None]:

    start_time = time.time()
    stage_reports = []
    research_citations = []

    # -- STAGE 0: Ingest ----------------------------------------------------------
    yield sse("stage_start", {"stage": "ingest", "stage_num": 0, "total_stages": 8,
                              "message": f"Effectus Research: reading {len(files)} document(s)..."})

    parsed_docs = []
    for filename, content in files:
        yield sse("thinking", {"stage": "ingest", "message": f"Parsing {filename}..."})
        text, doc_type = await parse_document(filename, content)
        if text:
            parsed_docs.append((filename, text, doc_type))
            yield sse("thinking", {"stage": "ingest",
                                   "message": f"{filename}: {len(text):,} chars ({doc_type})"})

    if not parsed_docs:
        yield sse("error", {"message": "No documents could be parsed.", "stage": "ingest"})
        return

    combined_text = combine_documents(parsed_docs)
    doc_context = truncate_for_context(combined_text, max_chars=80000)
    filenames = [f for f, _, _ in parsed_docs]

    yield sse("stage_complete", {"stage": "ingest",
                                  "message": f"Parsed {len(parsed_docs)} document(s), {len(doc_context):,} characters"})

    # -- STAGE 1: Pre-Analysis ----------------------------------------------------
    yield sse("stage_start", {"stage": "preanalysis", "stage_num": 1, "total_stages": 8,
                              "message": "Effectus Research: mapping strategic argument structure - claims, grounds, implicit premises..."})

    preanalysis = await run_preanalysis(doc_context, None)

    yield sse("thinking", {"stage": "preanalysis",
                           "message": f"Strategic claim: {preanalysis.get('strategic_claim', '')[:120]}"})
    yield sse("thinking", {"stage": "preanalysis",
                           "message": f"Implicit grounds identified: {len(preanalysis.get('implicit_grounds', []))}"})
    yield sse("thinking", {"stage": "preanalysis",
                           "message": f"Contested terms flagged: {preanalysis.get('contested_terms', [])}"})

    yield sse("stage_complete", {"stage": "preanalysis",
                                  "message": "Structural map complete",
                                  "partial_result": {
                                      "context_summary": preanalysis.get("context_summary", ""),
                                      "key_entities": preanalysis.get("commitment_signals", [])[:3],
                                  }})

    running_context = {
        "doc_context": doc_context,
        **preanalysis,
    }

    carmr = CARMRRecord(scrId=f"SCR-{job_id[:8].upper()}")

    # -- STAGE 2: Commitment ------------------------------------------------------
    yield sse("stage_start", {"stage": "commitment", "stage_num": 2, "total_stages": 8,
                              "message": "Effectus Research: extracting commitment - four-part statement, ownership, reversibility..."})

    yield sse("thinking", {"stage": "commitment",
                           "message": "Effectus Research: analysing commitment structure with extended reasoning..."})
    c_result, c_score, c_issues = await run_commitment(running_context)
    yield sse("quality_check", {"stage": "commitment", "quality_score": c_score,
                                 "issues": c_issues, "passed": c_score >= QUALITY_THRESHOLD})

    # Research Point 1: validate commitment context + find counter-evidence
    sector = c_result.get("portfolio", "") or preanalysis.get("context_summary", "")[:60]
    yield sse("research", {"stage": "commitment",
                           "query": "Validating strategic context and gathering adversarial evidence",
                           "status": "searching..."})
    try:
        research_text, research_urls = await research_commitment(
            title=c_result.get("title", ""),
            sector=sector,
            commitment_what=c_result.get("statementWhat", ""),
        )
        if research_text and "[No research" not in research_text:
            # Store verified citations with URLs
            for url in research_urls:
                research_citations.append(url)
            yield sse("research", {"stage": "commitment",
                                   "query": "Strategic context and counter-evidence",
                                   "finding": research_text[:500],
                                   "sources": research_urls[:3],
                                   "status": "complete"})
            # Revise commitment with research
            system = get_stage_system_prompt("commitment", "Revise commitment with research context")
            c_result, c_score, c_issues = await research_and_revise(
                system_prompt=system,
                original_extraction=c_result,
                research_findings=research_text,
                stage_name="commitment",
            )
            yield sse("thinking", {"stage": "commitment",
                                   "message": f"Effectus Research: revised with external validation. Quality: {c_score:.2f}"})
    except Exception as e:
        logger.warning(f"Commitment research failed: {e}")
        yield sse("thinking", {"stage": "commitment",
                               "message": "External research unavailable - proceeding on document evidence only"})

    if c_result:
        carmr.recordData = RecordData(**{k: v for k, v in c_result.items() if k in RecordData.model_fields})
        running_context["commitment"] = c_result

    stage_reports.append({"stage": "commitment", "quality_score": c_score, "issues": c_issues})
    yield sse("stage_complete", {"stage": "commitment", "quality_score": c_score,
                                  "partial_result": {"title": carmr.recordData.title},
                                  "warnings": c_issues if c_score < QUALITY_THRESHOLD else []})

    # -- STAGE 3: Assumptions -----------------------------------------------------
    yield sse("stage_start", {"stage": "assumptions", "stage_num": 3, "total_stages": 8,
                              "message": "Effectus Research: argumentation analysis - extracting defeasible premises (max 5, parent-child hierarchy)..."})

    yield sse("thinking", {"stage": "assumptions",
                           "message": "Effectus Research: applying four argumentation tests to draft premises..."})
    a_result, a_score, a_issues = await run_assumptions(running_context)
    assumptions_list = a_result.get("assumptions", [])

    yield sse("thinking", {"stage": "assumptions",
                           "message": f"Adversarial QC complete: {len(assumptions_list)} assumptions, quality score {a_score:.2f}"})
    yield sse("quality_check", {"stage": "assumptions", "quality_score": a_score,
                                 "issues": a_issues, "passed": a_score >= QUALITY_THRESHOLD})

    # Research Point 2: adversarially test each PARENT assumption
    parent_assumptions = [a for a in assumptions_list if not a.get("parentId")]
    for a in parent_assumptions[:2]:  # Max 2 research calls
        query = f"{a.get('statement', '')[:80]}..."
        yield sse("research", {"stage": "assumptions", "query": query, "status": "searching..."})
        try:
            finding, finding_urls = await research_assumption(
                statement=a.get("statement", ""),
                falsification=a.get("falsification", ""),
                commitment_title=carmr.recordData.title,
            )
            if finding and "[No research" not in finding:
                for url in finding_urls:
                    research_citations.append(url)
                yield sse("research", {"stage": "assumptions", "query": query,
                                       "finding": finding[:500],
                                       "sources": finding_urls[:3],
                                       "status": "complete"})
                # If research suggests assumption is already at risk, flag it
                at_risk_signals = ["failed", "at risk", "below target", "missed", "reversed", "rollback"]
                if any(s in finding.lower() for s in at_risk_signals):
                    a["status"] = "at-risk"
                    yield sse("thinking", {"stage": "assumptions",
                                           "message": f"Effectus Research: external data signals {a.get('id')} may already be at-risk"})
        except Exception as e:
            logger.warning(f"Assumption research failed: {e}")

    if a_result:
        carmr.assumptions = [
            Assumption(**{k: v for k, v in a.items() if k in Assumption.model_fields})
            for a in assumptions_list
        ]
        running_context["assumptions"] = a_result

    stage_reports.append({"stage": "assumptions", "quality_score": a_score, "issues": a_issues})
    yield sse("stage_complete", {"stage": "assumptions", "quality_score": a_score,
                                  "partial_result": {
                                      "count": len(carmr.assumptions),
                                      "parents": [a.id for a in carmr.assumptions if not a.parentId],
                                      "children": [a.id for a in carmr.assumptions if a.parentId],
                                  },
                                  "warnings": a_issues if a_score < QUALITY_THRESHOLD else []})

    # -- STAGE 4: Reasoning -------------------------------------------------------
    yield sse("stage_start", {"stage": "reasoning", "stage_num": 4, "total_stages": 8,
                              "message": "Effectus Research: applying Walton's Practical Reasoning - extracting causal strands with defeat analysis (max 3)..."})

    yield sse("thinking", {"stage": "reasoning",
                           "message": "Effectus Research: mapping argument warrants, grounds, and single points of failure..."})
    r_result, r_score, r_issues = await run_reasoning(running_context)
    yield sse("quality_check", {"stage": "reasoning", "quality_score": r_score,
                                 "issues": r_issues, "passed": r_score >= QUALITY_THRESHOLD})

    if r_result:
        carmr.reasoningBlocks = [
            ReasoningBlock(**{k: v for k, v in rb.items() if k in ReasoningBlock.model_fields})
            for rb in r_result.get("reasoningBlocks", [])
        ][:3]  # enforce max 3
        running_context["reasoning"] = r_result

    stage_reports.append({"stage": "reasoning", "quality_score": r_score, "issues": r_issues})
    yield sse("stage_complete", {"stage": "reasoning", "quality_score": r_score,
                                  "partial_result": {"blocks": len(carmr.reasoningBlocks)},
                                  "warnings": r_issues if r_score < QUALITY_THRESHOLD else []})

    # -- STAGE 5: Meaning ---------------------------------------------------------
    yield sse("stage_start", {"stage": "meaning", "stage_num": 5, "total_stages": 8,
                              "message": "Effectus Research: equivocation prevention - identifying contested terms in governance-critical clauses..."})

    yield sse("thinking", {"stage": "meaning",
                           "message": "Effectus Research: identifying terms whose drift would break falsification conditions..."})
    m_result, m_score, m_issues = await run_meaning(running_context)
    meaning_terms = m_result.get("meaningTerms", [])[:5]  # enforce max 5

    # Research Point 3: validate contested definitions
    for mt in meaning_terms[:2]:  # Max 2 research calls
        term = mt.get("term", "")
        yield sse("research", {"stage": "meaning",
                               "query": f"'{term}' industry and regulatory definition",
                               "status": "searching..."})
        try:
            sector = carmr.recordData.portfolio or carmr.recordData.title[:40]
            finding, finding_urls = await research_term_definition(term, sector)
            if finding and "[No research" not in finding:
                for url in finding_urls:
                    research_citations.append(url)
                yield sse("research", {"stage": "meaning",
                                       "query": f"'{term}' definition",
                                       "finding": finding[:400],
                                       "sources": finding_urls[:3],
                                       "status": "complete"})
        except Exception as e:
            logger.warning(f"Term research failed: {e}")

    if m_result:
        carmr.meaningTerms = [
            MeaningTerm(**{k: v for k, v in mt.items() if k in MeaningTerm.model_fields})
            for mt in meaning_terms
        ]
        running_context["meaning"] = m_result

    stage_reports.append({"stage": "meaning", "quality_score": m_score, "issues": m_issues})
    yield sse("stage_complete", {"stage": "meaning", "quality_score": m_score,
                                  "partial_result": {"terms": [t.term for t in carmr.meaningTerms]},
                                  "warnings": m_issues if m_score < QUALITY_THRESHOLD else []})

    # -- STAGE 6: Review Triggers -------------------------------------------------
    yield sse("stage_start", {"stage": "review", "stage_num": 6, "total_stages": 8,
                              "message": "Effectus Research: generating falsification-style review triggers..."})

    rev_result, rev_score, rev_issues = await run_review(running_context)
    yield sse("quality_check", {"stage": "review", "quality_score": rev_score,
                                 "issues": rev_issues, "passed": rev_score >= QUALITY_THRESHOLD})

    if rev_result:
        all_triggers = rev_result.get("reviewTriggers", [])
        # Enforce: max 2 time + max 2 event
        time_triggers = [t for t in all_triggers if t.get("type") == "time"][:2]
        event_triggers = [t for t in all_triggers if t.get("type") == "event"][:2]
        carmr.reviewTriggers = [
            ReviewTrigger(**{k: v for k, v in rt.items() if k in ReviewTrigger.model_fields})
            for rt in (time_triggers + event_triggers)
        ]
        running_context["review"] = rev_result

    stage_reports.append({"stage": "review", "quality_score": rev_score, "issues": rev_issues})
    yield sse("stage_complete", {"stage": "review", "quality_score": rev_score,
                                  "partial_result": {"triggers": len(carmr.reviewTriggers)}})

    # -- STAGE 7: Cross-Validation ------------------------------------------------
    yield sse("stage_start", {"stage": "cross_validation", "stage_num": 7, "total_stages": 8,
                              "message": "Effectus Research: structural integrity check - assumption coverage, falsification completeness..."})

    validation = await run_cross_validation(running_context, carmr)
    cis = validation.get("cis", 0.0)
    cis_breakdown = validation.get("cis_breakdown", {})
    cross_warnings = validation.get("warnings", [])

    yield sse("stage_complete", {"stage": "cross_validation", "cis": cis,
                                  "cis_breakdown": cis_breakdown, "warnings": cross_warnings})

    # -- STAGE 8: Synthesis -------------------------------------------------------
    yield sse("stage_start", {"stage": "synthesis", "stage_num": 8, "total_stages": 8,
                              "message": "Effectus Research: assembling final CARMR record..."})

    all_warnings = []
    for r in stage_reports:
        if r.get("quality_score", 1.0) < QUALITY_THRESHOLD:
            all_warnings.extend(r.get("issues", []))
    all_warnings.extend(cross_warnings)

    overall_confidence = sum(r.get("quality_score", 0.5) for r in stage_reports) / max(len(stage_reports), 1)

    # Deduplicate research citations while preserving order
    seen_citations = set()
    deduped_citations = []
    for c in research_citations:
        if c not in seen_citations:
            seen_citations.add(c)
            deduped_citations.append(c)

    result = ExtractionResult(
        job_id=job_id,
        carmr=carmr,
        cis=cis,
        cis_breakdown=cis_breakdown,
        overall_confidence=round(overall_confidence, 2),
        warnings=list(dict.fromkeys(all_warnings)),  # deduplicate preserving order
        research_citations=deduped_citations,
        extracted_from=filenames,
        processing_time_seconds=round(time.time() - start_time, 1),
    )

    yield sse("complete", {
        "job_id": job_id,
        "carmr": result.carmr.model_dump(),
        "cis": result.cis,
        "cis_breakdown": result.cis_breakdown,
        "overall_confidence": result.overall_confidence,
        "warnings": result.warnings,
        "research_citations": result.research_citations,
        "extracted_from": result.extracted_from,
        "processing_time_seconds": result.processing_time_seconds,
    })
