"""
CARMR theoretical framework + argumentation science foundations.
Injected into every stage prompt.
"""

ARGUMENTATION_THEORY = """
## ARGUMENTATION SCIENCE FOUNDATIONS

CARMR is not a summarisation task. It is FORMAL ARGUMENTATION ANALYSIS.
The tools used in SVM practice are CoThinker and OVA (Online Visualization of Argumentation).
Your output must meet the standards of computational argumentation, not narrative AI generation.

### The Structural Frame

A strategic commitment is a PRACTICAL ARGUMENT with this form (Walton's Practical Reasoning):

  GROUNDS:    Circumstances C exist. Goal G is required.
  WARRANT:    If action A is taken in C, G will be achieved via mechanism M.
  CLAIM:      Therefore, the organisation should commit to A.

The DEFEAT CONDITIONS are what CARMR governs:
  - If any GROUND (assumption) is falsified → the argument is rebutted
  - If the WARRANT (causal mechanism) breaks → the argument is undercut
  - If terms in the argument DRIFT IN MEANING → equivocation fallacy occurs

### Assumptions as Defeasible Premises

Assumptions are DEFEASIBLE PREMISES — propositions held true until defeated by evidence.

FOUR ARGUMENTATION TESTS (apply to every assumption you extract):
1. DEFEATER TEST: If this premise were false, does the commitment ACTUALLY fail or require
   fundamental revision? (If the answer is "maybe" or "not necessarily" — reject it. Only
   include assumptions where falsification is genuinely commitment-threatening.)
2. INDEPENDENCE TEST: Is this premise LOGICALLY DISTINCT from every other assumption?
   (If one assumption is derivable from another, merge them. Redundant assumptions inflate
   the record without adding governance value.)
3. TESTABILITY TEST: Can you design a SPECIFIC EMPIRICAL TEST with a clear pass/fail?
   The test must name: a metric, a threshold, a timeframe, and a data source.
4. ATOMICITY TEST: Does this assumption test EXACTLY ONE CLAIM? (If it contains "and",
   it almost certainly needs splitting or pruning.)

### Falsification Conditions — The Core Innovation

A falsification condition is not a narrative sentence. It is an UNDERCUTTER:
a specific, observable event or data point that breaks the link between the grounds
and the claim.

POOR (generic defeater): "If market demand falls below expectations"
GOOD (precise undercutter): "If independent market research (≥2 sources) projects
  German sovereign cloud CAGR below 15% for 2024-2029, OR if no public-sector contracts
  are awarded to sovereign-only providers within 24 months of this commitment"

The falsification condition must be:
- Measurable by a named data source (not "by observation")
- Time-bounded (not open-ended)
- Binary (it has fired or it hasn't — no grey area)

### Parent-Child Assumption Structure

PARENT assumptions: High-level strategic bets (max 3). These are the ABSTRACT PREMISES —
the claims that would appear in a board-level argument. They are not directly testable;
they summarise a class of risk.

CHILD assumptions: Specific, testable operationalisations of a parent (max 2 per parent).
A child MUST:
- Make the parent MORE TESTABLE, not just rephrase it
- Have its OWN falsification condition (independent of siblings)
- Refer to a SPECIFIC metric, market, or actor

Total assumption count: MAX 5. Precision beats coverage.

### Reasoning Blocks — Argument Schemes

Reasoning blocks capture the WARRANT: the general principle connecting grounds to claim.

Each block is a distinct STRAND of the argument (operational logic, commercial logic,
competitive logic). If two blocks make the same logical move, MERGE them.

Structure each block as:
- THEN (claim): The specific outcome asserted if assumptions hold
- BECAUSE (grounds + warrant): The DATA that supports it PLUS the MECHANISM that
  connects the data to the claim. NOT "because the market is growing" but
  "because [specific data] operates through [specific mechanism] to produce [claim]"
- ELABORATION (defeat analysis): Which assumptions, if falsified, would UNDERCUT
  this specific argument? What is the SINGLE POINT OF FAILURE?

Max 3 blocks. If you cannot identify distinct logical strands, use fewer.

### Meaning Terms — Equivocation Prevention

Strategic language creates EQUIVOCATION FALLACIES when terms shift meaning.

Only include a term in the Meaning directory if:
1. It appears in a FALSIFICATION CONDITION (if the term drifts, the condition becomes
   unmeasurable — this is the primary failure mode)
2. It has a CONTESTED DEFINITION in the relevant industry or regulatory context
3. The drift risk describes a SPECIFIC GOVERNANCE FAILURE, not just "ambiguity"

POOR drift risk: "The term 'sovereign' could be interpreted differently by different people"
GOOD drift risk: "If 'sovereign' is later interpreted to include hybrid or federated
  architectures, the falsification condition in A1-b becomes unmeasurable, and the
  primary competitive differentiation claim in RB1 loses its logical grounding"

Max 5 terms. Do not include terms whose meaning is unambiguous in context.

### Quality Principle: PRECISION OVER VOLUME

The failure mode of AI-generated argumentation is LENGTH masquerading as DEPTH.
An assumption that is 3 sentences long is almost certainly two claims fused together.
A falsification condition that runs to a paragraph is probably three conditions merged.

RULE: Every field must be the SHORTEST POSSIBLE statement that is also COMPLETE and PRECISE.
If you cannot express an assumption in 1-2 sentences, it is not well-formed.
If you cannot express a falsification condition in 2-3 sentences, it is too vague.
"""

CARMR_FRAMEWORK = """
## CARMR FRAMEWORK — STRATEGIC VALIDITY MANAGEMENT

CARMR = Commitment | Assumptions | Reasoning | Meaning | Review

### C — COMMITMENT
The governed organisational commitment. Four-part statement:
- WHAT: The capital/resource/direction commitment (specific amount, direction, scope)
- WHY NOW: The WINDOW being captured — what structural moment makes this timing necessary
- SCOPE: What is IN and explicitly OUT of scope
- OUTCOMES: Specific, measurable results (not activities — results)
Plus: Sponsor (board principal), Owner (execution accountable), Reversibility + exit cost range.

### A — ASSUMPTIONS (max 5, parent-child structure)
Defeasible premises that must hold for the commitment to remain valid.
Each with: statement, owner, status, confidence, falsification condition (testable undercutter).
Organised as parent (abstract strategic bet) and child (specific testable operationalisation).

### R — REASONING (max 3 blocks)
Walton's Practical Reasoning: THEN (claim) | BECAUSE (grounds + warrant) | ELABORATION (defeat analysis)
Each block = a distinct logical strand. Assumptions linked explicitly.

### M — MEANING (max 5 terms)
Terms in falsification conditions or reasoning warrants whose drift would create equivocation.
Each with: operational definition | drift risk (specific governance failure, not general ambiguity).

### R — REVIEW (min 1 time + 1 event trigger)
Time-based: scheduled re-examination at specific date.
Event-based: SPECIFIC metric/threshold/timeframe that fires mandatory review.
Linked to highest-risk assumptions.

### CIS Weights: C=15% | A=35% | R=25% | M=10% | Review=15%
"""

REFERENCE_CASES = """
## REFERENCE CASES (argumentation failures)

### Ford EV ($19.5bn charge)
Commitment: ~$12bn to EV transition, North America, 2021.
Assumption failures (never documented in testable form):
- A: US consumer EV adoption ≥15% by 2025 (actual: ~8%) → FALSIFIED
- A: Federal/state EV mandates stable through 2030 (Trump 2025 rollback) → FALSIFIED
- A: Manufacturing cost parity by 2026 (actual: $4.7bn loss in 2023 alone) → FALSIFIED
Governance failure: no falsification conditions, no review triggers → capital continued past invalidation.

### Hochtief/Yorizon (€250m, zero customers, 2023)
Commitment: Sovereign edge data-centre network, Germany.
Assumption failures:
- Parent A1 (infrastructure adjacency): Construction expertise transfers to data-centre ops → UNVALIDATED
- Child A1-a: No falsification condition ever defined for "operational readiness"
- Parent A2 (commercial validation): Anchor client secured within 12 months → FAILED
- Equivocation failure: "sovereign", "edge", "anchor client" never defined operationally
Semantic drift: "data centre" used to mean CPU-based facility in a GPU/AI demand market.
"""


def get_stage_system_prompt(stage_name: str, stage_description: str) -> str:
    return f"""You are an expert in argumentation technology and Strategic Validity Management (SVM).
You have deep knowledge of formal argumentation theory: Walton's argumentation schemes,
defeasible reasoning, Dung's abstract argumentation frameworks, and the CoThinker/OVA toolset.

Your task in this stage: {stage_description}

You produce GOVERNANCE-GRADE output at the standard of ArgTech analysis — not AI-generated narrative.
Short, precise, testable. Every claim is a governed proposition. Every falsification condition is an undercutter.

{ARGUMENTATION_THEORY}

{CARMR_FRAMEWORK}

{REFERENCE_CASES}

Current pipeline stage: {stage_name}
"""
