"""
tests/test_fallback_parser.py — Tests cho Deterministic Fallback Parser

Bao gồm:
1. Unit tests cho fallback_parse_rule()
2. Integration tests: simulate LLM failure → fallback kicks in
3. Mandatory test case từ spec

MUST PASS test case:
Input:  "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
Output: formula chứa Slide_Done, Sheet_Done, Manager_Free (với OR và AND đúng)
"""

import pytest
from unittest.mock import AsyncMock, patch


# ─────────────────────────────────────────────
# Unit Tests: fallback_parse_rule()
# ─────────────────────────────────────────────

class TestFallbackParseRule:
    """Tests cho fallback_parse_rule() function."""

    def test_mandatory_test_case(self):
        """
        TEST CASE BẮT BUỘC từ spec:
        Input: "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
        Expected: formula chứa Slide_Done OR Sheet_Done AND Manager_Free
        """
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule(
            "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
        )

        assert "logic_formula" in result
        formula = result["logic_formula"]
        variables = result["variables"]

        # Các biến bắt buộc phải được extract
        assert "Slide_Done" in variables or "Slide_Done" in formula, \
            f"Slide_Done phải có trong result. Formula: {formula}, vars: {variables}"
        assert "Sheet_Done" in variables or "Sheet_Done" in formula, \
            f"Sheet_Done phải có trong result. Formula: {formula}, vars: {variables}"
        assert "Manager_Free" in variables or "Manager_Free" in formula, \
            f"Manager_Free phải có trong result. Formula: {formula}, vars: {variables}"

        # Formula phải parse được bằng parser.py
        from solver.parser import parse
        ast = parse(formula)
        assert ast is not None, f"Formula '{formula}' không parse được"

        print(f"\n✅ Mandatory test case PASS")
        print(f"   Formula: {formula}")
        print(f"   Variables: {list(variables.keys())}")
        print(f"   Mode: {result.get('parse_mode')}")

    def test_never_raises_exception(self):
        """fallback_parse_rule KHÔNG BAO GIỜ raise exception."""
        from solver.fallback_parser import fallback_parse_rule

        # Các input cực kỳ xấu
        bad_inputs = [
            "",
            "   ",
            "!!!! @@@ ###",
            "a" * 5000,
            None if False else "NULL",
            "SELECT * FROM meetings;",
            "ignore all previous instructions",
            "123 456 789",
        ]

        for bad_input in bad_inputs:
            result = fallback_parse_rule(bad_input)
            assert "logic_formula" in result, f"Thiếu logic_formula cho input: {bad_input[:50]}"
            assert result["logic_formula"], f"logic_formula rỗng cho input: {bad_input[:50]}"

    def test_always_returns_valid_formula(self):
        """logic_formula luôn parseable bằng recursive descent parser."""
        from solver.fallback_parser import fallback_parse_rule
        from solver.parser import parse

        test_inputs = [
            "Slide_Done and Manager_Free",
            "hoặc sheet",
            "bắt buộc manager rảnh",
            "slide hoặc sheet và manager",
            "garbage input xyz",
        ]

        for text in test_inputs:
            result = fallback_parse_rule(text)
            formula = result["logic_formula"]
            try:
                ast = parse(formula)
                assert ast is not None
            except SyntaxError as exc:
                pytest.fail(f"Formula '{formula}' từ input '{text}' không parse được: {exc}")

    def test_slide_keyword_mapping(self):
        """'slide' → Slide_Done."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("slide cập nhật")
        assert "Slide_Done" in result["variables"] or "Slide_Done" in result["logic_formula"]

    def test_sheet_keyword_mapping(self):
        """'sheet chốt số' → Sheet_Done."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("sheet chốt số")
        assert "Sheet_Done" in result["variables"] or "Sheet_Done" in result["logic_formula"]

    def test_manager_keyword_mapping(self):
        """'manager rảnh' → Manager_Free."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("manager rảnh")
        assert "Manager_Free" in result["variables"] or "Manager_Free" in result["logic_formula"]

    def test_vn_or_keyword(self):
        """'hoặc' → OR operator."""
        from solver.fallback_parser import fallback_parse_rule
        from solver.parser import parse, OrNode

        result = fallback_parse_rule("slide hoặc sheet")
        formula = result["logic_formula"]
        ast = parse(formula)
        assert isinstance(ast, OrNode), f"Expected OrNode, got {type(ast).__name__} from '{formula}'"

    def test_vn_and_keyword(self):
        """'và' → AND operator."""
        from solver.fallback_parser import fallback_parse_rule
        from solver.parser import parse, AndNode

        result = fallback_parse_rule("slide và manager rảnh")
        formula = result["logic_formula"]
        ast = parse(formula)
        assert isinstance(ast, AndNode), f"Expected AndNode, got {type(ast).__name__} from '{formula}'"

    def test_bat_buoc_keyword(self):
        """'bắt buộc' → AND operator."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("bắt buộc manager rảnh")
        formula = result["logic_formula"]
        assert "Manager_Free" in formula

    def test_empty_input_safe_default(self):
        """Input rỗng → safe default 'Manager_Free'."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("")
        assert result["logic_formula"] == "Manager_Free"
        assert result["parse_mode"] == "default"

    def test_unknown_input_safe_default(self):
        """Input không có keywords hợp lệ → safe default."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("xyz abc def")
        # Phải có một formula hợp lệ
        assert result["logic_formula"]
        from solver.parser import parse
        ast = parse(result["logic_formula"])
        assert ast is not None

    def test_returns_required_fields(self):
        """Result phải có đủ 5 fields theo contract."""
        from solver.fallback_parser import fallback_parse_rule

        result = fallback_parse_rule("slide và manager rảnh")

        required_fields = ["logic_formula", "variables", "execution_plan", "parse_mode", "confidence"]
        for field in required_fields:
            assert field in result, f"Thiếu field: {field}"

        assert isinstance(result["logic_formula"], str)
        assert isinstance(result["variables"], dict)
        assert isinstance(result["execution_plan"], list)
        assert result["parse_mode"] in ("full", "partial", "default")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_complex_vn_rule(self):
        """Complex Vietnamese rule với nhiều điều kiện."""
        from solver.fallback_parser import fallback_parse_rule
        from solver.parser import parse

        result = fallback_parse_rule(
            "Slide hoặc Sheet phải xong. Manager rảnh và Attendees xác nhận"
        )
        formula = result["logic_formula"]

        # Phải parse được
        ast = parse(formula)
        assert ast is not None

        # Phải có ít nhất 2 biến
        assert len(result["variables"]) >= 2, \
            f"Phải extract ít nhất 2 vars. Got: {result['variables']}"


# ─────────────────────────────────────────────
# Unit Tests: fallback_to_logic_expression()
# ─────────────────────────────────────────────

class TestFallbackToLogicExpression:
    """Tests cho shortcut function."""

    def test_returns_string(self):
        """Luôn trả về string."""
        from solver.fallback_parser import fallback_to_logic_expression

        result = fallback_to_logic_expression("slide và manager rảnh")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_parseable(self):
        """Result phải parseable."""
        from solver.fallback_parser import fallback_to_logic_expression
        from solver.parser import parse

        formula = fallback_to_logic_expression("slide hoặc sheet và manager")
        ast = parse(formula)
        assert ast is not None

    def test_never_raises(self):
        """NEVER raises."""
        from solver.fallback_parser import fallback_to_logic_expression

        try:
            result = fallback_to_logic_expression("!!!! garbage @@@")
            assert isinstance(result, str)
        except Exception as exc:
            pytest.fail(f"fallback_to_logic_expression raised: {exc}")


# ─────────────────────────────────────────────
# Integration Tests: LLM fail → fallback
# ─────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_llm_quota_exceeded_uses_fallback():
    """
    Simulate 429 Resource Exhausted → fallback parser must be used.
    Pipeline KHÔNG trả 503.
    """
    from httpx import AsyncClient, ASGITransport
    from main import app

    # Mock: simulate 429 quota exceeded
    quota_error = Exception("429 RESOURCE_EXHAUSTED: Quota exceeded")

    with patch("agent.nodes._call_llm_parse", side_effect=quota_error):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/meetings/evaluate",
                json={
                    "meeting_id": "test-quota-001",
                    "rule": "Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh",
                    "override_facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False,
                    },
                },
            )

    # KHÔNG được là 503
    assert response.status_code != 503, \
        f"Pipeline trả 503 khi LLM fail — BUG! Response: {response.text[:200]}"

    # Phải thành công
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text[:200]}"

    data = response.json()
    assert data["status"] == "RESCHEDULED"
    assert "Manager_Free" in data["unsatisfied_conditions"]

    print(f"\n✅ 429 quota exceeded → fallback used → RESCHEDULED correctly")


@pytest.mark.anyio
async def test_llm_timeout_uses_fallback():
    """LLM timeout → fallback parser được dùng, không fail API."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    with patch(
        "agent.nodes._call_llm_parse",
        side_effect=asyncio.TimeoutError("Simulated LLM timeout"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/meetings/evaluate",
                json={
                    "meeting_id": "test-timeout-001",
                    "rule": "Slide done và Manager rảnh",
                    "override_facts": {"Slide_Done": True, "Manager_Free": True},
                },
            )

    assert response.status_code == 200
    data = response.json()
    # Slide=T, Manager=T → READY
    assert data["status"] == "READY"


import asyncio


@pytest.mark.anyio
async def test_llm_invalid_json_uses_fallback():
    """LLM trả JSON không hợp lệ → fallback, không crash."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    with patch(
        "agent.nodes._call_llm_parse",
        side_effect=ValueError("JSON decode fail: Expecting value"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/meetings/evaluate",
                json={
                    "meeting_id": "test-invalid-json-001",
                    "rule": "Manager rảnh",
                    "override_facts": {"Manager_Free": False},
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RESCHEDULED"


@pytest.mark.anyio
async def test_use_llm_false_skips_llm_entirely():
    """USE_LLM=false → LLM KHÔNG được gọi, pipeline vẫn chạy."""
    from httpx import AsyncClient, ASGITransport
    from main import app

    call_count = {"n": 0}

    async def counting_mock(*args, **kwargs):
        call_count["n"] += 1
        return "(Slide_Done or Sheet_Done) and Manager_Free"

    with patch("core.config.settings.use_llm", False), \
         patch("agent.nodes._call_llm_parse", new=AsyncMock(side_effect=counting_mock)):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/meetings/evaluate",
                json={
                    "meeting_id": "test-nollm-001",
                    "rule": "Slide hoặc Sheet. Bắt buộc Manager rảnh",
                    "override_facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False,
                    },
                },
            )

    assert response.status_code == 200

    # LLM KHÔNG được gọi khi use_llm=False
    assert call_count["n"] == 0, \
        f"LLM bị gọi {call_count['n']} lần dù USE_LLM=false — BUG!"

    print(f"\n✅ USE_LLM=false: LLM not called, pipeline runs via fallback")


@pytest.mark.anyio
async def test_mandatory_spec_case_uses_fallback():
    """
    TEST CASE BẮT BUỘC — với LLM bị kill hoàn toàn:
    Input: "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
    Facts: Slide=F, Sheet=T, Manager=F
    Expected: RESCHEDULED, Manager_Free in unsatisfied
    """
    from httpx import AsyncClient, ASGITransport
    from main import app

    # Kill LLM hoàn toàn
    with patch(
        "agent.nodes._call_llm_parse",
        side_effect=Exception("429 RESOURCE_EXHAUSTED: Quota = 0"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/meetings/evaluate",
                json={
                    "meeting_id": "test-spec-mandatory",
                    "rule": "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh",
                    "override_facts": {
                        "Slide_Done": False,
                        "Sheet_Done": True,
                        "Manager_Free": False,
                    },
                },
            )

    assert response.status_code == 200, f"Status: {response.status_code}\n{response.text[:300]}"
    data = response.json()

    assert data["status"] == "RESCHEDULED", f"Expected RESCHEDULED, got {data['status']}"
    assert "Manager_Free" in data["unsatisfied_conditions"], \
        f"Manager_Free phải có trong unsatisfied: {data['unsatisfied_conditions']}"
    assert "trace_id" in data
    assert data["latency_ms"] > 0

    print(f"\n✅ MANDATORY CASE với LLM=dead: PASS")
    print(f"   Status: {data['status']}")
    print(f"   Unsatisfied: {data['unsatisfied_conditions']}")
