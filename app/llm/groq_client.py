import time
import json
from typing import List, Optional, Any, Dict
from groq import AsyncGroq, APIConnectionError, RateLimitError
from app.config.settings import settings
from app.schemas.schemas import TestCase, TestCaseList
from loguru import logger

# Fallback models in priority order
GROQ_MODEL_FALLBACKS: List[str] = [
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
]

_SYSTEM_PROMPT = """You are an expert QA Engineer specializing in medical device software testing.
Your task is to generate QA test cases from the provided technical manual sections.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON. No markdown code fences, no extra text, no commentary.
- Generate between 3 and 5 test cases.
- Each test case must have ALL of the following fields:
  - test_case_id: unique string like "TC-001"
  - title: short descriptive title
  - requirement_reference: the manual section or heading this tests
  - preconditions: string describing setup conditions
  - steps: array of strings, each a distinct test step
  - expected_result: string describing the expected outcome
  - priority: one of "High", "Medium", "Low"
  - risk_level: one of "Critical", "High", "Medium", "Low"
  - category: one of "Functional", "Safety", "Usability", "Performance", "Data Management"

Return JSON in this EXACT format:
{
  "test_cases": [
    {
      "test_case_id": "TC-001",
      "title": "...",
      "requirement_reference": "...",
      "preconditions": "...",
      "steps": ["Step 1", "Step 2"],
      "expected_result": "...",
      "priority": "High",
      "risk_level": "Critical",
      "category": "Safety"
    }
  ]
}"""


async def _call_groq_with_fallback(user_content: str) -> tuple[str, str, float]:
    """
    Calls Groq API using the preferred model, falling back through alternatives.
    Returns (raw_response_text, model_used, elapsed_seconds).
    Raises RuntimeError if all models fail.
    """
    client = AsyncGroq(api_key=settings.GROQ_API_KEY)

    for model in GROQ_MODEL_FALLBACKS:
        logger.info(f"Attempting Groq call with model: {model}")
        t0 = time.perf_counter()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=4096,
            )
            elapsed = time.perf_counter() - t0
            raw = response.choices[0].message.content
            logger.info(f"Groq call succeeded with model '{model}' in {elapsed:.2f}s.")
            return raw, model, elapsed
        except (APIConnectionError, RateLimitError) as exc:
            logger.warning(f"Model '{model}' failed: {exc}. Trying next fallback...")
        except Exception as exc:
            logger.error(f"Unexpected error with model '{model}': {exc}")
            raise

    raise RuntimeError("All Groq model fallbacks exhausted. Could not generate test cases.")


def _parse_test_cases(raw: str) -> TestCaseList:
    """
    Attempts to parse the raw JSON response into a TestCaseList.
    Raises ValueError on failure.
    """
    try:
        # Strip potential code-fence wrappers just in case
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(cleaned)
        return TestCaseList.model_validate(data)
    except (json.JSONDecodeError, Exception) as exc:
        raise ValueError(f"JSON parse failure: {exc}")


async def generate_test_cases(selection_text: str) -> tuple[TestCaseList, str, str, float]:
    """
    Generates structured QA test cases from selection text using Groq.

    Returns:
        (TestCaseList, raw_response, model_used, response_time)

    If the first parse attempt fails, a single retry is performed with the
    error injected into the prompt. If retry also fails, raises RuntimeError
    so the caller can store the failed state and return an appropriate error.
    """
    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured. Cannot generate test cases.")

    user_content = f"""Please generate QA test cases for the following technical manual sections:

---
{selection_text}
---

Remember: Return ONLY valid JSON matching the exact schema described."""

    raw, model_used, response_time = await _call_groq_with_fallback(user_content)
    logger.debug(f"Raw LLM response ({len(raw)} chars): {raw[:300]}...")

    try:
        parsed = _parse_test_cases(raw)
        logger.info(f"Successfully parsed {len(parsed.test_cases)} test cases.")
        return parsed, raw, model_used, response_time
    except ValueError as first_err:
        logger.warning(f"First parse attempt failed: {first_err}. Retrying with error context...")

        retry_content = (
            f"{user_content}\n\n"
            f"IMPORTANT: Your previous response failed to parse with this error:\n{first_err}\n"
            "Ensure your response is ONLY valid JSON with no extra text."
        )
        raw2, model_used2, response_time2 = await _call_groq_with_fallback(retry_content)
        logger.debug(f"Retry raw response ({len(raw2)} chars): {raw2[:300]}...")

        try:
            parsed2 = _parse_test_cases(raw2)
            logger.info(f"Retry succeeded. Parsed {len(parsed2.test_cases)} test cases.")
            return parsed2, raw2, model_used2, response_time2
        except ValueError as second_err:
            logger.error(f"Retry parse also failed: {second_err}. Storing raw response as FAILED.")
            raise RuntimeError(
                f"Could not parse LLM response after 1 retry. Last error: {second_err}. "
                f"Raw response stored for inspection."
            ) from second_err


async def check_groq_connectivity() -> bool:
    """Sends a minimal ping to Groq to verify API key validity and connectivity."""
    if not settings.GROQ_API_KEY:
        return False
    try:
        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        # Use the lightest model for a cheap health check
        response = await client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
        )
        return bool(response)
    except Exception as exc:
        logger.warning(f"Groq connectivity check failed: {exc}")
        return False
