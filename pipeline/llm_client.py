"""
LLM client - wraps Anthropic Claude Opus with extended thinking.
Provides structured JSON extraction with self-critique and retry logic.
"""
import os
import json
import asyncio
import logging
from typing import Any, AsyncGenerator, Optional
import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPUS_MODEL = os.getenv("OPUS_MODEL", "claude-opus-4-5")

# Extended thinking budget (tokens) - generous for agentic quality
THINKING_BUDGET = 8000


def get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env file.")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


async def extract_structured(
    system_prompt: str,
    user_prompt: str,
    output_schema_description: str,
    max_retries: int = 3,
    thinking: bool = True,
) -> tuple[dict, float, list[str]]:
    """
    Call Claude Opus and extract structured JSON output.
    Returns: (parsed_dict, quality_score 0-1, list_of_issues)

    The model is asked to:
    1. Think (extended thinking enabled)
    2. Extract the requested fields
    3. Self-critique for completeness and quality
    4. Return JSON + quality assessment
    """
    client = get_client()

    full_prompt = f"""{user_prompt}

---
OUTPUT INSTRUCTIONS:
Return ONLY a valid JSON object with this structure:
{{
  "extracted": {{ {output_schema_description} }},
  "quality_score": <float 0.0-1.0>,
  "quality_issues": ["<issue 1>", "<issue 2>", ...],
  "confidence_notes": ["<field: note>", ...]
}}

quality_score: 1.0 = all fields complete, governance-grade, fully specific.
0.7-0.9 = minor gaps. 0.5-0.7 = significant gaps. Below 0.5 = major problems.
quality_issues: List specific problems. Be honest. This feeds a validation step.
Do not include any text outside the JSON object.
"""

    for attempt in range(1, max_retries + 1):
        try:
            kwargs = {
                "model": OPUS_MODEL,
                "max_tokens": 8000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": full_prompt}],
            }

            if thinking:
                # claude-opus-4-7+ uses adaptive thinking + output_config.effort
                model_name = kwargs.get("model", "")
                if any(x in model_name for x in ["4-7", "4-6"]):
                    kwargs["thinking"] = {"type": "adaptive"}
                    kwargs["output_config"] = {"effort": "high"}
                else:
                    kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": THINKING_BUDGET,
                    }
                kwargs["max_tokens"] = max(8000, THINKING_BUDGET + 4000)

            # Run sync client in thread pool to not block event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.messages.create(**kwargs)
            )

            # Extract text content (skip thinking blocks)
            text_content = ""
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    text_content = block.text
                    break

            if not text_content:
                logger.warning(f"Attempt {attempt}: Empty text response")
                continue

            # Parse JSON
            parsed = _extract_json(text_content)
            if parsed is None:
                logger.warning(f"Attempt {attempt}: Failed to parse JSON from response")
                if attempt < max_retries:
                    continue
                return {}, 0.0, ["Failed to parse structured JSON response"]

            extracted = parsed.get("extracted", {})
            quality_score = float(parsed.get("quality_score", 0.5))
            quality_issues = parsed.get("quality_issues", [])

            return extracted, quality_score, quality_issues

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error on attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(2 ** attempt)

    return {}, 0.0, ["All extraction attempts failed"]


async def research_and_revise(
    system_prompt: str,
    original_extraction: dict,
    research_findings: str,
    stage_name: str,
) -> tuple[dict, float, list[str]]:
    """
    Second pass: given research findings, revise the extraction.
    Returns updated extraction with improved quality.
    """
    client = get_client()

    revision_prompt = f"""You previously extracted the following {stage_name} data:

{json.dumps(original_extraction, indent=2)}

You have now received the following research findings:

{research_findings}

Based on this research:
1. Correct any factual inaccuracies in the extraction
2. Strengthen falsification conditions where market data supports specificity
3. Add any implicit assumptions revealed by the research
4. Tighten definitions using domain-standard terminology found in the research
5. Flag any assumptions that are already at-risk based on current market conditions

Return the revised extraction as JSON in the same format:
{{
  "extracted": {{ ...revised fields... }},
  "quality_score": <float 0.0-1.0>,
  "quality_issues": ["..."],
  "research_incorporated": ["what changed and why"]
}}
"""

    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=OPUS_MODEL,
                max_tokens=max(8000, THINKING_BUDGET + 4000),
                system=system_prompt,
                messages=[{"role": "user", "content": revision_prompt}],
                **({"thinking": {"type": "adaptive"}, "output_config": {"effort": "high"}}
                   if any(x in OPUS_MODEL for x in ["4-7", "4-6"])
                   else {"thinking": {"type": "enabled", "budget_tokens": THINKING_BUDGET}}),
            )
        )

        text_content = ""
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                text_content = block.text
                break

        parsed = _extract_json(text_content)
        if parsed:
            return (
                parsed.get("extracted", original_extraction),
                float(parsed.get("quality_score", 0.6)),
                parsed.get("quality_issues", []),
            )
    except Exception as e:
        logger.error(f"Revision pass error: {e}")

    return original_extraction, 0.6, ["Research revision pass failed - using original extraction"]


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    import re
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding the outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None
