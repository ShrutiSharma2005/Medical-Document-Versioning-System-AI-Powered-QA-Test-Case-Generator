"""
Tests for Groq client: JSON parsing, retry logic, and fallback model detection.
Uses unittest.mock to avoid live API calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.llm.groq_client import _parse_test_cases, generate_test_cases
from app.schemas.schemas import TestCaseList

VALID_JSON = """{
  "test_cases": [
    {
      "test_case_id": "TC-001",
      "title": "Power-on sequence",
      "requirement_reference": "Section 3.1",
      "preconditions": "Device is off, batteries installed.",
      "steps": ["Hold power button for 1 second.", "Observe LCD."],
      "expected_result": "LCD displays home screen.",
      "priority": "High",
      "risk_level": "Medium",
      "category": "Functional"
    }
  ]
}"""

INVALID_JSON = "This is not JSON at all."

PARTIAL_JSON = '{"test_cases": [{"test_case_id": "TC-001"}]}'  # Missing required fields


class TestParseTestCases:
    def test_parses_valid_json(self):
        result = _parse_test_cases(VALID_JSON)
        assert isinstance(result, TestCaseList)
        assert len(result.test_cases) == 1
        assert result.test_cases[0].test_case_id == "TC-001"

    def test_raises_on_invalid_json(self):
        with pytest.raises(ValueError):
            _parse_test_cases(INVALID_JSON)

    def test_raises_on_missing_fields(self):
        with pytest.raises(ValueError):
            _parse_test_cases(PARTIAL_JSON)

    def test_strips_code_fence_wrapper(self):
        fenced = f"```json\n{VALID_JSON}\n```"
        result = _parse_test_cases(fenced)
        assert len(result.test_cases) == 1


class TestGenerateTestCases:
    @pytest.mark.asyncio
    async def test_successful_generation(self):
        """Mock a successful Groq response and verify parsing."""
        with patch(
            "app.llm.groq_client._call_groq_with_fallback",
            new_callable=AsyncMock,
            return_value=(VALID_JSON, "llama-3.3-70b-versatile", 1.23),
        ):
            result, raw, model, time = await generate_test_cases("Sample text.")
            assert isinstance(result, TestCaseList)
            assert len(result.test_cases) == 1
            assert model == "llama-3.3-70b-versatile"
            assert time == pytest.approx(1.23)

    @pytest.mark.asyncio
    async def test_retry_on_first_parse_failure(self):
        """First response is invalid, second response is valid. Retry should succeed."""
        call_count = 0

        async def mock_call(user_content):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (INVALID_JSON, "llama-3.3-70b-versatile", 0.5)
            return (VALID_JSON, "llama-3.3-70b-versatile", 0.8)

        with patch("app.llm.groq_client._call_groq_with_fallback", side_effect=mock_call):
            result, raw, model, time = await generate_test_cases("Sample text.")
            assert isinstance(result, TestCaseList)
            assert call_count == 2  # Retry was performed

    @pytest.mark.asyncio
    async def test_raises_after_two_failures(self):
        """Both the original and retry attempts fail parsing → RuntimeError."""
        with patch(
            "app.llm.groq_client._call_groq_with_fallback",
            new_callable=AsyncMock,
            return_value=(INVALID_JSON, "llama-3.3-70b-versatile", 0.5),
        ):
            with pytest.raises(RuntimeError, match="Could not parse LLM response"):
                await generate_test_cases("Sample text.")

    @pytest.mark.asyncio
    async def test_raises_if_no_api_key(self):
        with patch("app.llm.groq_client.settings") as mock_settings:
            mock_settings.GROQ_API_KEY = ""
            with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
                await generate_test_cases("Some content.")
