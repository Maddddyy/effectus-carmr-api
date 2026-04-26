"""
Pipeline stages - rebuilt on argumentation science foundations.
Each stage: precise extraction → adversarial QC → targeted research → revision.
Limits enforced: max 5 assumptions (parent-child), max 3 reasoning blocks, max 5 meaning terms.
"""
import json
import logging
from typing import Tuple, List

from .llm_client import extract_structured
from prompts.carmr_framework import get_stage_system_prompt, CARMR_FRAMEWORK, ARGUMENTATION_THEORY

logger = logging.getLogger(__name__)


# ── Stage 1: Pre-Analysis ──────────────────────────────────────────────────────

async def run_preanalysis(doc_context: str, emit) -> dict:
    system = get_stage_system_prompt(
        "Pre-Analysis",
        "Map the strategic argument before extraction. Identify the core commitment claim, "
        "what grounds (circumstances) are stated, and which terms carry the most governance risk."
    )

    prompt = f"""Analyse these documents to prepare for CARMR argumentation extraction.

DOCUMENTS:
{doc_context[:40000]}

Extract a STRUCTURAL MAP - not a summary. Identify:

1. context_summary: One precise sentence - what strategic commitment is being made and by whom.
2. document_type: What kind of documents (board minutes / strategy paper / transcript / mixed)
3. commitment_signals: Direct quotes or close paraphrases of the actual commitment decision
4. strategic_claim: The single central claim - what outcome does this commitment assert will follow?
5. stated_grounds: Explicit circumstances or facts cited to justify the commitment
6. implicit_grounds: Things taken for granted that appear nowhere as explicit statements
   (look for what is NOT questioned - these are often the most dangerous assumptions)
7. contested_terms: Terms used with strategic weight whose meaning is unclear or potentially drifting
8. counter_signals: Any stated risks, dissents, or qualifications found in the documents
"""

    result, _, _ = await extract_structured(
        system_prompt=system,
        user_prompt=prompt,
        output_schema_description="""
"context_summary": "string",
"document_type": "string",
"commitment_signals": ["string"],
"strategic_claim": "string",
"stated_grounds": ["string"],
"implicit_grounds": ["string"],
"contested_terms": ["string"],
"counter_signals": ["string"]
""",
        thinking=True,
    )
    return result


# ── Stage 2: Commitment (C) ───────────────────────────────────────────────────

async def run_commitment(running_context: dict) -> Tuple[dict, float, List[str]]:
    system = get_stage_system_prompt(
        "Commitment Extraction (C)",
        "Extract the governed commitment. Every field must be governance-grade: "
        "specific enough for a board member to reconstruct the decision in 2 years."
    )

    doc = running_context.get("doc_context", "")[:50000]
    preanalysis = {
        "context_summary": running_context.get("context_summary", ""),
        "commitment_signals": running_context.get("commitment_signals", []),
        "strategic_claim": running_context.get("strategic_claim", ""),
        "stated_grounds": running_context.get("stated_grounds", []),
    }

    prompt = f"""Pre-analysis structural map:
{json.dumps(preanalysis, indent=2)}

Documents:
{doc}

Extract the COMMITMENT (C). Precision rules:

statementWhat: The EXACT commitment - capital amount, resource, direction. No vagueness.
  BAD: "Invest in digital infrastructure"
  GOOD: "Commit €250M to establish 8 sovereign edge data-centre sites across Germany"

statementWhyNow: The STRUCTURAL WINDOW - what specific market/regulatory/competitive moment
  makes NOW the necessary timing. Not "market is growing" but "which specific window closes if
  we don't act now, and what evidence shows it's open now."

statementScope: Explicitly state what IS and IS NOT included. The exclusions are as important
  as the inclusions. If something is not explicitly excluded, it will be assumed to be in scope.

statementOutcomes: Specific measurable results. Name metrics, targets, timeframes.
  NOT "establish market leadership" - "achieve €45M ARR by Year 5, top-3 market position in
  North American EV by 2030."

reversibility: "full" | "partial" | "irreversible"
  For partial: exitCostMin and exitCostMax are REQUIRED (in millions, currency clear).
  For irreversible: explicitly acknowledge this is a one-way door.

sponsor: The board or C-suite principal who OWN this commitment (name + role if available).
owner: The executive ACCOUNTABLE for execution (role minimum).
"""

    return await extract_structured(
        system_prompt=system,
        user_prompt=prompt,
        output_schema_description="""
"title": "string - specific title, not generic",
"date": "string - YYYY-MM-DD or best estimate with note",
"sponsor": "string - name + role if available, role minimum",
"owner": "string - role minimum",
"statementWhat": "string - 1-2 precise sentences",
"statementWhyNow": "string - the structural window, specific",
"statementScope": "string - what is in AND what is explicitly out",
"statementOutcomes": "string - specific metrics and timeframes",
"reversibility": "full|partial|irreversible",
"exitCostMin": "string - number in millions if partial, else empty",
"exitCostMax": "string - number in millions if partial, else empty",
"portfolio": "string - programme or portfolio name",
"status": "draft"
""",
        thinking=True,
    )


# -- Stage 3: Assumptions (A) -- the most critical stage ---------------------

async def run_assumptions(running_context: dict) -> Tuple[dict, float, List[str]]:
    """
    Two-pass extraction:
    Pass 1: Draft up to 5 flat assumptions ranked by governance relevance
    Pass 2: Adversarial QC using the 4 argumentation tests - revise or replace failures
    """
    system = get_stage_system_prompt(
        "Assumptions Extraction (A) - Argumentation Analysis",
        "Extract the highest-relevance defeasible premises using formal argumentation criteria. "
        "Max 5 flat assumptions. Ranked by governance consequence. Ultra-precise falsification conditions."
    )

    doc = running_context.get("doc_context", "")[:40000]
    commitment = json.dumps(running_context.get("commitment", {}), indent=2)
    implicit_grounds = json.dumps(running_context.get("implicit_grounds", []))
    stated_grounds = json.dumps(running_context.get("stated_grounds", []))
    contested_terms = json.dumps(running_context.get("contested_terms", []))

    # -- Pass 1: Draft extraction ----------------------------------------------
    draft_prompt = f"""Commitment extracted:
{commitment}

Pre-analysis found these grounds and signals:
- Stated grounds: {stated_grounds}
- Implicit grounds (taken for granted, never questioned): {implicit_grounds}
- Contested terms (may need Meaning entries): {contested_terms}

Documents:
{doc}

Extract the ASSUMPTIONS using ARGUMENTATION ANALYSIS.

SELECTION CRITERION - governance relevance rank:
Include only assumptions where falsification would force fundamental revision of the commitment.
Rank them: A1 = single most consequential if false. A5 = fifth most consequential.
If fewer than 5 pass the Defeater Test, include fewer. Precision over volume.

CONTENT RULES for each assumption:
- statement: 1-2 sentences max. One claim. If it contains "and", split or prune.
- owner: The role or person who can OBSERVE and MONITOR this assumption (not just the one who made it).
- falsification: 2-3 sentences MAXIMUM. Must name:
  (a) a specific metric or observable event
  (b) a specific threshold or condition
  (c) a timeframe
  (d) a data source or observable mechanism
  If you cannot write this in 2-3 sentences, the assumption is not yet well-formed - sharpen it.
- confidence: your assessment of how well-evidenced this assumption was AT TIME OF COMMITMENT
- isImplicit: true if the document never states this assumption explicitly

INCLUDE implicit assumptions - they are often the most dangerous.
The implicit grounds list above is your starting point for finding them.
"""

    draft_result, _, _ = await extract_structured(
        system_prompt=system,
        user_prompt=draft_prompt,
        output_schema_description="""
"assumptions": [
  {
    "id": "A1",
    "parentId": null,
    "statement": "string - 1-2 sentences, single claim",
    "owner": "string - role or name+role",
    "status": "active",
    "confidence": "high|medium|low|unknown",
    "falsification": "string - 2-3 sentences, specific metric/threshold/timeframe/source",
    "dissentingView": "string or empty",
    "isImplicit": false
  }
]
""",
        thinking=True,
    )

    assumptions_draft = draft_result.get("assumptions", [])

    if not assumptions_draft:
        return {"assumptions": []}, 0.3, ["No assumptions extracted in draft pass"]

    # -- Pass 2: Adversarial QC -----------------------------------------------
    qc_result, qc_score, qc_issues = await _qc_assumptions(
        assumptions_draft, commitment, system
    )

    final_assumptions = qc_result.get("assumptions", assumptions_draft)

    # Enforce hard max 5, flat list only
    if len(final_assumptions) > 5:
        final_assumptions = final_assumptions[:5]
        qc_issues.append(f"Trimmed to 5 assumptions (governance relevance rank order preserved)")

    # Ensure all parentId fields are null (flat structure)
    for a in final_assumptions:
        a["parentId"] = None

    return {"assumptions": final_assumptions}, qc_score, qc_issues


async def _qc_assumptions(
    assumptions: list, commitment: str, system: str
) -> Tuple[dict, float, List[str]]:
    """
    Adversarial QC pass: apply 4 argumentation tests to each assumption.
    Revise or replace any that fail.
    """
    qc_prompt = f"""You are performing ADVERSARIAL ARGUMENTATION CRITIQUE on a draft set of assumptions.

Commitment context:
{commitment}

DRAFT ASSUMPTIONS (ranked A1 = highest governance consequence):
{json.dumps(assumptions, indent=2)}

Apply the FOUR ARGUMENTATION TESTS to each assumption:

TEST 1 - DEFEATER TEST:
"If this assumption were false, does the commitment ACTUALLY require fundamental revision?"
Fail: The commitment could continue unchanged even if this assumption is false.
Action: Remove it. It is not a genuine defeater.

TEST 2 - INDEPENDENCE TEST:
"Is this assumption logically distinct from every other assumption?"
Fail: This assumption is derivable from or a restatement of another.
Action: Merge the weaker one into the stronger one.

TEST 3 - TESTABILITY TEST:
"Does the falsification condition name a SPECIFIC metric, threshold, timeframe, AND data source?"
Fail: The falsification condition contains vague language ("if market changes", "if demand falls").
Action: Rewrite the falsification condition to meet the precision standard.

TEST 4 - ATOMICITY TEST:
"Does this assumption test EXACTLY ONE CLAIM?"
Fail: The statement contains "and" connecting two distinct claims.
Action: Prune to the single most consequential claim.

ADDITIONAL CHECKS:
- Are the most DANGEROUS assumptions included? (check implicit grounds - often more consequential)
- Re-rank by governance consequence after QC. A1 should be the one whose falsification would
  cause the most severe commitment revision.
- Falsification conditions: are any too long (>3 sentences)? Trim them.
- Does any falsification condition use a term that may need a Meaning entry? Flag it.

Output the REVISED assumption set. For each change, explain why.
Keep total at MAX 5. Flat list only - no parent/child hierarchy.
"""

    result, score, issues = await extract_structured(
        system_prompt=system,
        user_prompt=qc_prompt,
        output_schema_description="""
"assumptions": [
  {
    "id": "string (A1..A5, flat list)",
    "parentId": null,
    "statement": "string",
    "owner": "string",
    "status": "active",
    "confidence": "high|medium|low|unknown",
    "falsification": "string",
    "dissentingView": "string",
    "isImplicit": false
  }
],
"qc_changes": ["string - description of each change made and why"],
"qc_score": 0.0
""",
        thinking=True,
    )

    # Use the qc_score from the model's own assessment
    model_qc_score = result.get("qc_score", score)
    return result, float(model_qc_score), issues


# ── Stage 4: Reasoning (R) ────────────────────────────────────────────────────

async def run_reasoning(running_context: dict) -> Tuple[dict, float, List[str]]:
    system = get_stage_system_prompt(
        "Reasoning Extraction (R) - Walton's Practical Reasoning",
        "Extract the argument structure using Walton's Practical Reasoning scheme. "
        "Max 3 blocks. Each block is a DISTINCT logical strand, not a narrative paragraph."
    )

    commitment = json.dumps(running_context.get("commitment", {}), indent=2)
    assumptions_raw = running_context.get("assumptions", {})
    assumptions = assumptions_raw.get("assumptions", []) if isinstance(assumptions_raw, dict) else []
    doc = running_context.get("doc_context", "")[:30000]

    prompt = f"""Commitment:
{commitment}

Assumptions (defeasible premises):
{json.dumps(assumptions, indent=2)}

Documents:
{doc}

Extract the REASONING using Walton's Practical Reasoning scheme.

STRUCTURE - each block captures a DISTINCT logical strand:
  THEN (claim): The specific outcome asserted IF the linked assumptions hold.
    - Not a restatement of the commitment outcomes. The LOGICAL CONSEQUENCE of the specific
    assumptions linked to this block.
  BECAUSE (grounds + warrant): Two things joined:
    (a) the GROUNDS: what data or evidence supports this claim?
    (b) the WARRANT: the GENERAL PRINCIPLE that connects the grounds to the claim.
    Format: "[Evidence/data] operates through [mechanism] to produce [claim]"
    - NOT "because the market is growing" - "because [specific evidence] + [specific mechanism]"
  ELABORATION (defeat analysis): Which specific assumptions, if falsified, would UNDERCUT
    this argument strand? Name the SINGLE POINT OF FAILURE - the one assumption whose failure
    would collapse this entire strand of reasoning.

RULES:
- Max 3 blocks. If the same logical move is made twice, MERGE into one block.
- Every assumption should be linked to at least one block.
- The THEN must be distinct across blocks (different outcomes, not the same outcome restated).
- ELABORATION must name specific assumption ids, not just describe risk generically.
- Blocks should collectively cover: operational logic (can we execute?),
  commercial logic (will the market respond?), and strategic logic (will this produce durable advantage?).
  Use fewer if fewer distinct strands exist in this commitment.
"""

    return await extract_structured(
        system_prompt=system,
        user_prompt=prompt,
        output_schema_description="""
"reasoningBlocks": [
  {
    "id": "RB1",
    "linkedAssumptions": ["A1", "A1-a"],
    "then": "string - the specific outcome asserted (1-2 sentences)",
    "because": "string - [evidence] operates through [mechanism] to produce [claim]",
    "elaboration": "string - single point of failure analysis, names specific assumption ids"
  }
]
""",
        thinking=True,
    )


# ── Stage 5: Meaning (M) ──────────────────────────────────────────────────────

async def run_meaning(running_context: dict) -> Tuple[dict, float, List[str]]:
    system = get_stage_system_prompt(
        "Meaning Extraction (M) - Equivocation Prevention",
        "Identify only terms where semantic drift would create an equivocation fallacy. "
        "If the term's definition is clear and uncontested in context, do not include it. "
        "Target 3-5 terms. Cover all falsification-critical terms but stop at 5."
    )

    commitment = json.dumps(running_context.get("commitment", {}), indent=2)
    assumptions_raw = running_context.get("assumptions", {})
    assumptions = assumptions_raw.get("assumptions", []) if isinstance(assumptions_raw, dict) else []
    reasoning_raw = running_context.get("reasoning", {})
    reasoning = reasoning_raw.get("reasoningBlocks", []) if isinstance(reasoning_raw, dict) else []
    contested_terms = running_context.get("contested_terms", [])

    # Compile all text that uses potentially contested terms
    all_falsification = " ".join(a.get("falsification", "") for a in assumptions)
    all_reasoning = " ".join(rb.get("because", "") + " " + rb.get("then", "") for rb in reasoning)

    prompt = f"""Commitment:
{commitment}

Assumptions (pay attention to falsification conditions - terms used there are highest priority):
{json.dumps(assumptions, indent=2)}

Reasoning blocks:
{json.dumps(reasoning, indent=2)}

Pre-analysis flagged these contested terms: {json.dumps(contested_terms)}

Identify MEANING TERMS - but only where EQUIVOCATION is a genuine governance risk.

INCLUSION CRITERIA (must meet at least one):
1. The term appears in a FALSIFICATION CONDITION - if its meaning drifts, the condition
   becomes unmeasurable and governance breaks down.
2. The term is used in the WARRANT of a reasoning block - if it shifts meaning, the
   causal mechanism no longer holds.
3. The term has documented CONTESTED USAGE in the relevant industry or regulatory context.

EXCLUSION CRITERIA (do not include if):
- The term's meaning is clear and uncontested in this specific context
- The term appears only in narrative sections, not in governance-critical clauses
- Including it would be comprehensive but not consequential

For each included term:
- term: MUST be a word or phrase that appears VERBATIM (or near-verbatim) in the source
  documents. Do NOT invent labels or use terms from internet research. If the document uses
  "anchor client", use "anchor client" - not "major customer" or "enterprise buyer".
- contextQuote: The EXACT phrase from the documents where this term appears in a
  governance-critical role (falsification condition or reasoning warrant).
- definition: OPERATIONAL definition - specific enough to CHECK. Not a dictionary definition.
  "A single enterprise customer committing to ≥€5M ARR minimum 3-year contract" not
  "a major customer."
- driftRisk: Name the SPECIFIC GOVERNANCE FAILURE. Which falsification condition becomes
  unmeasurable? Which argument in the reasoning collapses?

Target 3-5 terms. Include all terms where semantic drift would break a falsification condition
or undercut a reasoning warrant. If only 2-3 terms genuinely qualify, use 2-3.
Do not pad to reach 5 - but aim for at least 3 to ensure the critical terms are covered.
"""

    return await extract_structured(
        system_prompt=system,
        user_prompt=prompt,
        output_schema_description="""
"meaningTerms": [
  {
    "id": "M1",
    "term": "string - exact term",
    "autoDetected": true,
    "contextQuote": "string - exact quote where this term has governance weight",
    "definition": "string - operational, specific, checkable",
    "driftRisk": "string - names the specific condition/argument that breaks if this term drifts"
  }
]
""",
        thinking=True,
    )


# ── Stage 6: Review Triggers (R) ──────────────────────────────────────────────

async def run_review(running_context: dict) -> Tuple[dict, float, List[str]]:
    system = get_stage_system_prompt(
        "Review Triggers (R) - Falsification-Style Governance",
        "Generate review triggers that are as precise as falsification conditions. "
        "Not scheduled check-ins - structured defeat conditions that fire mandatory re-examination."
    )

    commitment = json.dumps(running_context.get("commitment", {}), indent=2)
    assumptions_raw = running_context.get("assumptions", {})
    assumptions = assumptions_raw.get("assumptions", []) if isinstance(assumptions_raw, dict) else []

    # Find highest-risk assumptions (failed confidence or at-risk signals)
    high_risk = [a for a in assumptions if a.get("confidence") in ("low", "medium") or a.get("isImplicit")]
    if not high_risk:
        high_risk = assumptions[:2]

    prompt = f"""Commitment:
{commitment}

Assumptions with highest governance risk (link event triggers to these):
{json.dumps(high_risk, indent=2)}

All assumptions:
{json.dumps(assumptions, indent=2)}

Generate REVIEW TRIGGERS as FALSIFICATION-STYLE GOVERNANCE INSTRUMENTS.

Time trigger (1-2 maximum):
- A scheduled re-examination at a specific date
- Date: calculate from the commitment date - typically 12-18 months out
- Description: What SPECIFICALLY should be re-examined at this date?
  Not "review all assumptions" but "assess whether [specific metric X] has reached
  [threshold Y] consistent with the commercial timeline in A2"
- If the commitment date is unknown, use a relative description: "12 months post first-site go-live"

Event trigger (1-2 maximum - do not proliferate):
- Fired by a SPECIFIC observable event, not a general market trend
- Derive from the falsification condition of the SINGLE HIGHEST-RISK assumption only
- One event trigger is sufficient if it covers the highest-risk assumption
- Two event triggers only if there are two genuinely distinct, high-consequence risk events
- Format: "If [specific metric] crosses [specific threshold] for [specific duration],
  trigger mandatory review of [specific assumption ids] within [timeframe]"
- Do NOT create an event trigger for every assumption - that defeats the purpose of prioritisation

Total triggers: maximum 4 (up to 2 time + up to 2 event). Fewer is better if they cover the highest risks.

QUALITY TEST: Could a board secretary determine UNAMBIGUOUSLY whether this trigger has fired?
If not, the trigger is too vague.
"""

    return await extract_structured(
        system_prompt=system,
        user_prompt=prompt,
        output_schema_description="""
"reviewTriggers": [
  {
    "id": "RT1",
    "type": "time|event",
    "description": "string - specific, binary-testable trigger condition",
    "nextReviewDue": "YYYY-MM-DD for time triggers, empty for event triggers",
    "overdue": false
  }
]
""",
        thinking=True,
    )


# ── Stage 7: Cross-Validation ─────────────────────────────────────────────────

async def run_cross_validation(running_context: dict, carmr) -> dict:
    warnings = []

    # Check assumption-reasoning coverage
    linked_ids = set()
    for rb in carmr.reasoningBlocks:
        linked_ids.update(rb.linkedAssumptions)
    assumption_ids = {a.id for a in carmr.assumptions}
    unlinked = assumption_ids - linked_ids
    if unlinked:
        warnings.append(f"Assumptions not linked to reasoning: {', '.join(sorted(unlinked))}")

    # Check falsification completeness
    for a in carmr.assumptions:
        if not a.falsification.strip():
            warnings.append(f"{a.id}: missing falsification condition")
        elif len(a.falsification.split()) < 15:
            warnings.append(f"{a.id}: falsification condition may be too brief - verify it names metric/threshold/timeframe")

    # Check meaning covers falsification terms
    meaning_term_words = {t.term.lower() for t in carmr.meaningTerms}
    all_falsification_text = " ".join(a.falsification.lower() for a in carmr.assumptions)
    for term in meaning_term_words:
        if term not in all_falsification_text:
            warnings.append(f"Meaning term '{term}' not referenced in any falsification condition - review necessity")

    # Check review triggers
    has_time = any(rt.type == "time" for rt in carmr.reviewTriggers)
    has_event = any(rt.type == "event" for rt in carmr.reviewTriggers)
    if not has_time:
        warnings.append("No time-based review trigger")
    if not has_event:
        warnings.append("No event-based review trigger")

    cis_result = _compute_cis(carmr)

    return {
        "cis": cis_result.get("cis", 0.0),
        "cis_breakdown": cis_result.get("breakdown", {}),
        "warnings": warnings,
    }


def _compute_cis(carmr) -> dict:
    rd = carmr.recordData
    assumptions = carmr.assumptions
    reasoning = carmr.reasoningBlocks
    meaning = carmr.meaningTerms
    triggers = carmr.reviewTriggers

    def non_empty(s):
        return isinstance(s, str) and len(s.strip()) > 0

    def clamp(n, lo=0, hi=100):
        return max(lo, min(hi, n))

    checks = [
        non_empty(rd.title), non_empty(rd.date), non_empty(rd.sponsor), non_empty(rd.owner),
        non_empty(rd.statementWhat) and non_empty(rd.statementWhyNow) and
        non_empty(rd.statementScope) and non_empty(rd.statementOutcomes),
    ]
    mandatory = (sum(1 for c in checks if c) / len(checks)) * 100
    rev = rd.reversibility
    if rev == "full":
        rev_score = 100
    elif rev == "partial":
        rev_score = 100 if (non_empty(rd.exitCostMin) and non_empty(rd.exitCostMax)) else 0
    elif rev == "irreversible":
        rev_score = 100 if rd.irreversibleAcknowledged else 0
    else:
        rev_score = 0
    c_score = clamp((mandatory + rev_score) / 2)

    n = len(assumptions)
    if n == 0:
        a_score = 0
    else:
        count_part = clamp((n / 6) * 100)
        def card_complete(a):
            return (non_empty(a.statement) and non_empty(a.owner) and
                    non_empty(a.falsification) and a.status in ["active","at-risk","failed","superseded"])
        complete_part = (sum(1 for a in assumptions if card_complete(a)) / n) * 100
        confidence_part = (sum(1 for a in assumptions if non_empty(a.confidence)) / n) * 100
        owners = [a.owner.strip().lower() for a in assumptions if a.owner.strip()]
        concentration = n > 1 and len(set(owners)) == 1
        a_score = clamp((count_part + complete_part + confidence_part) / 3 * (0.85 if concentration else 1))

    if n == 0:
        r_score = 0
    else:
        linked_ids = set()
        for rb in reasoning:
            linked_ids.update(rb.linkedAssumptions)
        link_pct = (sum(1 for a in assumptions if a.id in linked_ids) / n) * 100
        then_pct = (sum(1 for rb in reasoning if non_empty(rb.then)) / max(len(reasoning),1)) * 100
        because_pct = (sum(1 for rb in reasoning if non_empty(rb.because)) / max(len(reasoning),1)) * 100
        block_mix = 100 if len(reasoning) >= 2 else (65 if len(reasoning) == 1 else 0)
        r_score = clamp((link_pct + then_pct + because_pct + block_mix) / 4)

    terms = meaning
    if not terms:
        m_score = 40
    else:
        def complete_term(t):
            return non_empty(t.term) and non_empty(t.definition) and non_empty(t.driftRisk)
        m_score = clamp((sum(1 for t in terms if complete_term(t)) / len(terms)) * 100)

    time_triggers = [t for t in triggers if t.type == "time"]
    has_time_ok = any(non_empty(t.description) and non_empty(t.nextReviewDue) for t in time_triggers)
    creation_part = 100 if has_time_ok else 0
    overdue_flag = any(t.overdue for t in time_triggers)
    overdue_part = 58 if overdue_flag else 100
    events_part = 65
    rev_score_final = creation_part * 0.42 + overdue_part * 0.38 + events_part * 0.20

    weights = {"C": 0.15, "A": 0.35, "R": 0.25, "M": 0.10, "Review": 0.15}
    cis = clamp(
        weights["C"] * c_score + weights["A"] * a_score + weights["R"] * r_score +
        weights["M"] * m_score + weights["Review"] * rev_score_final
    )

    return {
        "cis": round(cis, 1),
        "breakdown": {
            "C": round(c_score, 1), "A": round(a_score, 1), "R": round(r_score, 1),
            "M": round(m_score, 1), "Review": round(rev_score_final, 1),
        }
    }


async def run_synthesis(running_context: dict, carmr) -> dict:
    return {"status": "complete"}
