"""
Deterministic semantic divergence module for CARMR Stage 5 (Meaning).

Responsibilities:
  1. Verbatim quote verification against doc_context.
  2. Duplicate-merge using embedding distance.
  3. Classification: cardinality, modality, scenarioType, scenarioName.
  4. defId reassignment in document order.
  5. Divergence / variance score computation.
  6. Band assignment.
  7. Legacy field assembly (contextQuote, definition, driftRisk).

No LLM calls. Given the same inputs, always produces the same output.
"""

import logging
import re
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# ── Module constants ──────────────────────────────────────────────────────────

EMBED_MODEL       = "all-MiniLM-L6-v2"
MAX_TERMS         = 5
MAX_DEFS_PER_TERM = 6
MERGE_EPSILON     = 0.08   # pairs closer than this are the same meaning
BAND_LOW_MAX      = 0.20   # score < 0.20  -> "low"
BAND_MODERATE_MAX = 0.40   # 0.20 <= score < 0.40 -> "moderate"
                           # score >= 0.40          -> "high"

# Scenario names (human labels). Machine enums are fixed; only these strings change
# if Brian updates S2/S3 names.
_SCENARIO_NAMES = {
    "defined_term":       "Defined Term",
    "assumed_term":       "Assumed Term",
    "contested_meanings": "Contested Meanings",
    "classic_ambiguity":  "Classic Ambiguity",
    "hidden_divergence":  "Hidden Divergence",
    "undefined_term":     "Undefined Term",
}

# ── Embedding model (lazy singleton) ─────────────────────────────────────────

_embedding_model = None
_embedding_model_version: Optional[str] = None
_using_fallback = False


def _get_embedding_model():
    """
    Load sentence-transformers model once, cache as module-level singleton.
    Returns (model_or_None, version_string, using_fallback_bool).
    """
    global _embedding_model, _embedding_model_version, _using_fallback
    if _embedding_model is not None or _using_fallback:
        return _embedding_model, _embedding_model_version, _using_fallback

    try:
        from sentence_transformers import SentenceTransformer
        import sentence_transformers as st_module
        model = SentenceTransformer(EMBED_MODEL)
        _embedding_model = model
        _embedding_model_version = getattr(st_module, "__version__", "unknown")
        _using_fallback = False
        logger.info(f"Semantic divergence: loaded {EMBED_MODEL} (sentence-transformers {_embedding_model_version})")
    except Exception as exc:
        logger.warning(
            f"Semantic divergence: could not load sentence-transformers model ({exc}). "
            f"Using lexical-Jaccard fallback for all divergence scores."
        )
        _embedding_model = None
        _embedding_model_version = None
        _using_fallback = True

    return _embedding_model, _embedding_model_version, _using_fallback


# ── Quote normalisation ───────────────────────────────────────────────────────

def _normalise_for_quote_check(text: str) -> str:
    """
    Normalise text for verbatim quote verification:
    - Collapse all whitespace runs to a single space.
    - Convert curly quotes to straight quotes.
    - Trim.
    - Do NOT lowercase (case is part of fidelity).
    """
    # Curly quotes -> straight
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # Other Unicode apostrophe-likes
    text = text.replace("\u02bc", "'").replace("\u02b9", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _quote_passes(quote: str, doc_context: str) -> bool:
    """Return True if the normalised quote is a substring of the normalised doc_context."""
    if not quote or not quote.strip():
        return False
    return _normalise_for_quote_check(quote) in _normalise_for_quote_check(doc_context)


# ── Lexical Jaccard fallback distance ────────────────────────────────────────

_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "is", "it",
    "at", "on", "for", "with", "by", "as", "be", "this", "that", "are",
    "was", "were", "we", "our", "its", "from", "not", "which", "has",
    "have", "had", "their", "they", "will", "would", "can", "all", "one",
    "if", "so", "do", "no", "up", "more", "what", "he", "she",
}


def _lexical_tokens(text: str):
    """Lowercase, strip punctuation (keep hyphens), drop stop words."""
    text = text.lower()
    # Remove punctuation except hyphens
    text = re.sub(r"[^\w\s\-]", " ", text)
    tokens = {t for t in text.split() if t and t not in _STOP_WORDS}
    return tokens


def _jaccard_distance(a: str, b: str) -> float:
    """1 - Jaccard similarity on token sets. Returns float in [0, 1]."""
    ta, tb = _lexical_tokens(a), _lexical_tokens(b)
    if not ta and not tb:
        return 0.0
    intersection = len(ta & tb)
    union = len(ta | tb)
    return round(1.0 - (intersection / union if union else 0.0), 3)


# ── Embedding distance ────────────────────────────────────────────────────────

def _embed_distance(text_a: str, text_b: str, model) -> float:
    """
    Cosine distance between two L2-normalised embeddings.
    Clamped to [0, 1]. Rounded to 3 decimal places.
    """
    import numpy as np
    embeddings = model.encode([text_a, text_b], normalize_embeddings=True)
    cosine_sim = float(np.dot(embeddings[0], embeddings[1]))
    distance = max(0.0, min(1.0, 1.0 - cosine_sim))
    return round(distance, 3)


def _pairwise_distance(text_a: str, text_b: str) -> tuple[float, str]:
    """
    Return (distance, method_string). Uses embeddings if available, else Jaccard.
    """
    model, version, using_fallback = _get_embedding_model()
    if not using_fallback and model is not None:
        dist = _embed_distance(text_a, text_b, model)
        method = f"cosine|{EMBED_MODEL}|{version}"
    else:
        dist = _jaccard_distance(text_a, text_b)
        method = "lexical-jaccard-fallback"
    return dist, method


# ── Duplicate-merge ───────────────────────────────────────────────────────────

def _merge_duplicates(defs: list[dict]) -> list[dict]:
    """
    Merge definition pairs whose text distance < MERGE_EPSILON.
    Keep the earlier-in-document one (lower defId index). Repeat until stable.
    Returns the reduced list (order preserved).
    """
    changed = True
    while changed:
        changed = False
        surviving = list(range(len(defs)))
        to_remove = set()
        for i in range(len(defs)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(defs)):
                if j in to_remove:
                    continue
                dist, _ = _pairwise_distance(
                    defs[i].get("definition", ""),
                    defs[j].get("definition", ""),
                )
                if dist < MERGE_EPSILON:
                    to_remove.add(j)
                    changed = True
        if to_remove:
            defs = [d for idx, d in enumerate(defs) if idx not in to_remove]
    return defs


# ── defId reassignment in document order ─────────────────────────────────────

def _find_quote_position(quote: str, doc_context: str) -> int:
    """Return the character index of the quote in doc_context, or sys.maxsize if not found."""
    import sys
    norm_doc = _normalise_for_quote_check(doc_context)
    norm_quote = _normalise_for_quote_check(quote)
    pos = norm_doc.find(norm_quote)
    return pos if pos >= 0 else sys.maxsize


def _reassign_def_ids(defs: list[dict], doc_context: str) -> list[dict]:
    """
    Sort definitions by their evidenceQuote's position in doc_context (earliest first),
    then reassign defId as D1, D2, ...
    """
    defs_with_pos = [
        (d, _find_quote_position(d.get("evidenceQuote", ""), doc_context))
        for d in defs
    ]
    defs_with_pos.sort(key=lambda x: x[1])
    result = []
    for idx, (d, _) in enumerate(defs_with_pos):
        d = dict(d)
        d["defId"] = f"D{idx + 1}"
        result.append(d)
    return result


# ── Classification ────────────────────────────────────────────────────────────

def _classify_term(term_dict: dict) -> dict:
    """
    Given a term dict with verified, merged, reordered definitionsInUse,
    compute and set: definitionCardinality, definitionModality, scenarioType, scenarioName.
    Returns the updated dict.
    """
    defs = term_dict.get("definitionsInUse", [])
    usage_quotes = term_dict.get("usageQuotes", [])

    n = len(defs)

    if n == 0:
        if usage_quotes:
            cardinality = "none"
        else:
            # Empty and no usage quotes - caller should drop this term
            cardinality = "none"
        modality = "none"
    elif n == 1:
        cardinality = "single"
        modality = defs[0].get("modality", "explicit")
    else:
        cardinality = "multiple"
        modalities = {d.get("modality", "explicit") for d in defs}
        if modalities == {"explicit"}:
            modality = "explicit"
        elif modalities == {"implicit"}:
            modality = "implicit"
        else:
            modality = "mixed"

    # Scenario type matrix
    if cardinality == "none":
        scenario_type = "undefined_term"
    elif cardinality == "single" and modality == "explicit":
        scenario_type = "defined_term"
    elif cardinality == "single" and modality == "implicit":
        scenario_type = "assumed_term"
    elif cardinality == "multiple" and modality == "explicit":
        scenario_type = "contested_meanings"
    elif cardinality == "multiple" and modality == "implicit":
        scenario_type = "classic_ambiguity"
    elif cardinality == "multiple" and modality == "mixed":
        scenario_type = "hidden_divergence"
    else:
        scenario_type = "defined_term"  # safe fallback

    term_dict = dict(term_dict)
    term_dict["definitionCardinality"] = cardinality
    term_dict["definitionModality"] = modality
    term_dict["scenarioType"] = scenario_type
    term_dict["scenarioName"] = _SCENARIO_NAMES.get(scenario_type, scenario_type)
    return term_dict


# ── Divergence computation ────────────────────────────────────────────────────

def _compute_divergence(term_dict: dict) -> Optional[dict]:
    """
    Compute divergence object for a term with cardinality == "multiple".
    Returns a dict matching the Divergence model, or None for non-multiple terms.
    """
    if term_dict.get("definitionCardinality") != "multiple":
        return None

    defs = term_dict.get("definitionsInUse", [])
    if len(defs) < 2:
        return None

    # Truncate to MAX_DEFS_PER_TERM (already enforced before, but be safe)
    defs = defs[:MAX_DEFS_PER_TERM]

    # Compute all pairwise distances
    def_ids = [d["defId"] for d in defs]
    def_texts = [d.get("definition", "") for d in defs]

    pairs = []
    methods_seen = set()
    for i in range(len(defs)):
        for j in range(i + 1, len(defs)):
            dist, method = _pairwise_distance(def_texts[i], def_texts[j])
            pairs.append({"pair": [def_ids[i], def_ids[j]], "distance": dist})
            methods_seen.add(method)

    method_str = list(methods_seen)[0] if len(methods_seen) == 1 else "|".join(sorted(methods_seen))

    if len(defs) == 2:
        score = pairs[0]["distance"]
        metric = "divergence"
        most_divergent = [def_ids[0], def_ids[1]]
        pairwise_out = []
    else:
        # 3+ definitions: variance = mean of pairwise distances
        score = round(sum(p["distance"] for p in pairs) / len(pairs), 3)
        metric = "variance"
        # Most divergent pair: max distance, tie-break by lowest defId indices
        max_pair = max(pairs, key=lambda p: (p["distance"], -_def_index(p["pair"][0]), -_def_index(p["pair"][1])))
        most_divergent = max_pair["pair"]
        pairwise_out = sorted(pairs, key=lambda p: (p["pair"][0], p["pair"][1]))

    band = _score_to_band(score)

    return {
        "metric": metric,
        "score": score,
        "band": band,
        "method": method_str,
        "mostDivergentPair": most_divergent,
        "pairwise": pairwise_out,
    }


def _def_index(def_id: str) -> int:
    """Extract numeric index from defId like 'D1' -> 1."""
    try:
        return int(def_id[1:])
    except (ValueError, IndexError):
        return 0


def _score_to_band(score: float) -> str:
    if score < BAND_LOW_MAX:
        return "low"
    elif score < BAND_MODERATE_MAX:
        return "moderate"
    else:
        return "high"


# ── Legacy field assembly ─────────────────────────────────────────────────────

def _build_legacy_fields(term_dict: dict) -> dict:
    """
    Populate contextQuote, definition, driftRisk from structured data.
    All strings assembled in code - no LLM. No em-dashes.
    """
    term_dict = dict(term_dict)
    cardinality = term_dict.get("definitionCardinality", "single")
    defs = term_dict.get("definitionsInUse", [])
    usage_quotes = term_dict.get("usageQuotes", [])
    usage_count = term_dict.get("usageCount", 0)
    term_name = term_dict.get("term", "this term")

    # contextQuote
    if cardinality in ("single", "multiple") and defs:
        term_dict["contextQuote"] = defs[0].get("evidenceQuote", "")
    elif cardinality == "none" and usage_quotes:
        term_dict["contextQuote"] = usage_quotes[0]
    else:
        term_dict["contextQuote"] = ""

    # definition
    if cardinality in ("single", "multiple") and defs:
        term_dict["definition"] = defs[0].get("definition", "")
    else:
        term_dict["definition"] = ""

    # driftRisk
    if cardinality == "multiple":
        short_names = [d.get("shortName", "") for d in defs if d.get("shortName")]
        n = len(defs)
        names_str = ", ".join(short_names) if short_names else f"{n} distinct meanings"
        term_dict["driftRisk"] = (
            f"This term carries {n} different definitions-in-use ({names_str}). "
            f"The decision is not anchored to one meaning; outcomes diverge depending on "
            f"which definition governs."
        )
    elif cardinality == "single":
        term_dict["driftRisk"] = (
            "Single consistent definition-in-use detected. "
            "No equivocation within this document set."
        )
    else:
        count_str = str(usage_count) if usage_count else "multiple"
        term_dict["driftRisk"] = (
            f"Term used {count_str} times but never defined, explicitly or implicitly. "
            f"Meaning is unconstrained and open to divergent interpretation."
        )

    return term_dict


# ── Main entry point ──────────────────────────────────────────────────────────

def process_meaning_terms(raw_terms: list[dict], doc_context: str) -> tuple[list[dict], list[str]]:
    """
    Full deterministic processing pipeline for raw LLM meaning term output.

    Steps (in order, per spec):
      1. Cap to MAX_TERMS (take first MAX_TERMS by LLM ordering).
      2. Quote verification - drop failed evidenceQuotes and usageQuotes.
      3. Cap each term's definitionsInUse to MAX_DEFS_PER_TERM (earliest kept).
      4. Duplicate-merge.
      5. Classification.
      6. Drop terms with no definitions and no usageQuotes.
      7. defId reassignment in document order.
      8. Divergence computation.
      9. Legacy field assembly.

    Returns (processed_terms, issues_list).
    """
    issues: list[str] = []
    processed: list[dict] = []

    # Step 1: cap to MAX_TERMS
    terms = raw_terms[:MAX_TERMS]

    for term_raw in terms:
        term = dict(term_raw)
        term_id = term.get("id", "M?")
        term_name = term.get("term", "")

        # Step 2: verify evidenceQuotes
        raw_defs = term.get("definitionsInUse", [])
        verified_defs = []
        for d in raw_defs:
            eq = d.get("evidenceQuote", "")
            if eq and not _quote_passes(eq, doc_context):
                issues.append(
                    f"{term_id}/{d.get('defId', '?')}: evidence quote not found verbatim - "
                    f"definition dropped. Quote: \"{eq[:80]}...\""
                )
            else:
                verified_defs.append(dict(d))

        # Step 2b: verify usageQuotes
        raw_usage = term.get("usageQuotes", [])
        verified_usage = []
        for uq in raw_usage:
            if uq and not _quote_passes(uq, doc_context):
                issues.append(
                    f"{term_id}: usage quote not found verbatim - dropped. "
                    f"Quote: \"{uq[:80]}...\""
                )
            else:
                verified_usage.append(uq)

        term["definitionsInUse"] = verified_defs
        term["usageQuotes"] = verified_usage

        # Step 3: cap to MAX_DEFS_PER_TERM (earliest in document order - sort before cap)
        if len(term["definitionsInUse"]) > MAX_DEFS_PER_TERM:
            # Sort by document position then cap
            defs_with_pos = [
                (d, _find_quote_position(d.get("evidenceQuote", ""), doc_context))
                for d in term["definitionsInUse"]
            ]
            defs_with_pos.sort(key=lambda x: x[1])
            kept = [d for d, _ in defs_with_pos[:MAX_DEFS_PER_TERM]]
            dropped_count = len(term["definitionsInUse"]) - MAX_DEFS_PER_TERM
            issues.append(
                f"{term_id}: {dropped_count} definition(s) beyond MAX_DEFS_PER_TERM={MAX_DEFS_PER_TERM} "
                f"dropped (earliest in document kept)."
            )
            term["definitionsInUse"] = kept

        # Step 4: duplicate-merge
        if len(term["definitionsInUse"]) >= 2:
            before = len(term["definitionsInUse"])
            term["definitionsInUse"] = _merge_duplicates(term["definitionsInUse"])
            after = len(term["definitionsInUse"])
            if after < before:
                issues.append(
                    f"{term_id}: {before - after} definition(s) merged as duplicates "
                    f"(distance < MERGE_EPSILON={MERGE_EPSILON})."
                )

        # Step 5: classify
        term = _classify_term(term)

        # Step 6: drop terms with no usable content
        if (term.get("definitionCardinality") == "none"
                and not term.get("usageQuotes")):
            issues.append(
                f"{term_id} ('{term_name}'): no definitions and no usage quotes after "
                f"verification - term dropped."
            )
            continue

        # Step 7: reassign defIds in document order
        if term["definitionsInUse"]:
            term["definitionsInUse"] = _reassign_def_ids(
                term["definitionsInUse"], doc_context
            )

        # Step 8: compute divergence
        divergence_dict = _compute_divergence(term)
        term["divergence"] = divergence_dict  # None for single/none

        # Step 9: legacy fields
        term = _build_legacy_fields(term)

        # Set usageCount from actual verified usageQuotes length if not set by LLM
        if term.get("definitionCardinality") == "none":
            term["usageCount"] = max(term.get("usageCount", 0), len(term.get("usageQuotes", [])))

        processed.append(term)

    return processed, issues
