"""
tests/test_solver.py — Unit tests cho Parser và Z3 Engine

Bao gồm test case bắt buộc:
- Input: "Chỉ họp nếu Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
- Facts: Slide_Done=False, Sheet_Done=True, Manager_Free=False
- Expected: RESCHEDULED, unsatisfied=["Manager_Free"]
"""

import pytest
from solver.parser import (
    parse,
    get_atoms,
    AndNode,
    OrNode,
    NotNode,
    AtomNode,
)
from solver.z3_engine import z3_engine


# ─────────────────────────────────────────────
# Parser Tests
# ─────────────────────────────────────────────

class TestParser:
    """Tests cho recursive descent parser."""

    def test_simple_atom(self):
        """Parse atom đơn giản."""
        ast = parse("Slide_Done")
        assert isinstance(ast, AtomNode)
        assert ast.name == "Slide_Done"

    def test_and_expression(self):
        """Parse biểu thức AND."""
        ast = parse("Slide_Done and Sheet_Done")
        assert isinstance(ast, AndNode)
        assert isinstance(ast.left, AtomNode)
        assert isinstance(ast.right, AtomNode)
        assert ast.left.name == "Slide_Done"
        assert ast.right.name == "Sheet_Done"

    def test_or_expression(self):
        """Parse biểu thức OR."""
        ast = parse("Slide_Done or Sheet_Done")
        assert isinstance(ast, OrNode)

    def test_not_expression(self):
        """Parse biểu thức NOT."""
        ast = parse("not Manager_Free")
        assert isinstance(ast, NotNode)
        assert isinstance(ast.operand, AtomNode)
        assert ast.operand.name == "Manager_Free"

    def test_complex_expression(self):
        """Parse biểu thức phức tạp với ngoặc."""
        ast = parse("(Slide_Done or Sheet_Done) and Manager_Free")
        assert isinstance(ast, AndNode)
        assert isinstance(ast.left, OrNode)
        assert isinstance(ast.right, AtomNode)

    def test_vietnamese_keywords(self):
        """Parse với từ khóa tiếng Việt."""
        ast = parse("Slide_Done hoặc Sheet_Done")
        assert isinstance(ast, OrNode)

        ast2 = parse("Slide_Done và Manager_Free")
        assert isinstance(ast2, AndNode)

    def test_mixed_case(self):
        """Parse với AND/OR/NOT viết hoa."""
        ast = parse("Slide_Done AND Manager_Free")
        assert isinstance(ast, AndNode)

    def test_get_atoms(self):
        """get_atoms trả về tất cả biến."""
        ast = parse("(Slide_Done or Sheet_Done) and Manager_Free")
        atoms = get_atoms(ast)
        assert set(atoms) == {"Slide_Done", "Sheet_Done", "Manager_Free"}

    def test_invalid_syntax_raises(self):
        """Cú pháp không hợp lệ → SyntaxError."""
        with pytest.raises(SyntaxError):
            parse("and Slide_Done")  # AND ở đầu

        with pytest.raises(SyntaxError):
            parse("Slide_Done and")  # AND ở cuối

        with pytest.raises(SyntaxError):
            parse("(Slide_Done and Sheet_Done")  # Thiếu ')'

    def test_empty_expression_raises(self):
        """Expression rỗng → SyntaxError."""
        with pytest.raises(SyntaxError):
            parse("")

    def test_trailing_punctuation_ignored(self):
        """Dấu chấm ở cuối câu được bỏ qua."""
        # Dấu chấm cuối câu → bỏ qua
        ast = parse("Slide_Done or Sheet_Done.")
        assert isinstance(ast, OrNode)
        atoms = get_atoms(ast)
        assert set(atoms) == {"Slide_Done", "Sheet_Done"}

    def test_comma_ignored(self):
        """Dấu phẩy trong danh sách được bỏ qua."""
        # Dấu phẩy bị bỏ qua
        ast = parse("Slide_Done, Sheet_Done and Manager_Free")
        assert get_atoms(ast)


# ─────────────────────────────────────────────
# Z3 Engine Tests
# ─────────────────────────────────────────────

class TestZ3Engine:
    """Tests cho Z3 SMT Solver Engine."""

    def test_all_satisfied(self):
        """Tất cả điều kiện thỏa mãn → satisfied=True."""
        ast = parse("Slide_Done and Manager_Free")
        facts = {"Slide_Done": True, "Manager_Free": True}

        result = z3_engine.verify(ast, facts)

        assert result.satisfied is True
        assert result.unsatisfied_conditions == []

    def test_one_fails(self):
        """Một điều kiện fail → satisfied=False."""
        ast = parse("Slide_Done and Manager_Free")
        facts = {"Slide_Done": True, "Manager_Free": False}

        result = z3_engine.verify(ast, facts)

        assert result.satisfied is False
        # Manager_Free=False gây ra fail
        assert "Manager_Free" in result.unsatisfied_conditions

    def test_or_with_one_true(self):
        """OR: chỉ cần một điều kiện True là đủ."""
        ast = parse("Slide_Done or Sheet_Done")
        facts = {"Slide_Done": False, "Sheet_Done": True}

        result = z3_engine.verify(ast, facts)

        assert result.satisfied is True

    def test_or_both_false(self):
        """OR: cả hai False → fail."""
        ast = parse("Slide_Done or Sheet_Done")
        facts = {"Slide_Done": False, "Sheet_Done": False}

        result = z3_engine.verify(ast, facts)

        assert result.satisfied is False

    # ─── MANDATORY TEST CASE ─────────────────────────
    def test_mandatory_case(self):
        """
        TEST CASE BẮT BUỘC PHẢI PASS:

        Rule: (Slide_Done or Sheet_Done) and Manager_Free
        (Tương đương: "Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh")

        Facts:
            Slide_Done  = False
            Sheet_Done  = True
            Manager_Free = False

        Expected:
            satisfied = False (RESCHEDULED)
            unsatisfied_conditions = ["Manager_Free"]
        """
        # Logic expression sau khi LLM parse
        ast = parse("(Slide_Done or Sheet_Done) and Manager_Free")

        facts = {
            "Slide_Done": False,
            "Sheet_Done": True,
            "Manager_Free": False,
        }

        result = z3_engine.verify(ast, facts)

        # Assertions
        assert result.satisfied is False, (
            f"Expected RESCHEDULED nhưng nhận được READY. "
            f"Manager_Free=False phải gây fail."
        )
        assert "Manager_Free" in result.unsatisfied_conditions, (
            f"Manager_Free phải có trong unsatisfied_conditions. "
            f"Actual: {result.unsatisfied_conditions}"
        )

    def test_not_operator(self):
        """NOT operator hoạt động đúng."""
        ast = parse("not Slide_Done")
        facts = {"Slide_Done": False}
        result = z3_engine.verify(ast, facts)
        assert result.satisfied is True  # NOT False = True

        facts2 = {"Slide_Done": True}
        result2 = z3_engine.verify(ast, facts2)
        assert result2.satisfied is False  # NOT True = False

    def test_missing_fact_defaults_false(self):
        """Biến chưa có fact → mặc định False."""
        ast = parse("Slide_Done")
        facts = {}  # Không có Slide_Done

        result = z3_engine.verify(ast, facts)

        assert result.satisfied is False

    def test_complex_compound(self):
        """Test điều kiện phức tạp nhiều tầng."""
        ast = parse("(Slide_Done or Sheet_Done) and (Manager_Free or Attendees_Confirmed)")
        facts = {
            "Slide_Done": False,
            "Sheet_Done": True,
            "Manager_Free": False,
            "Attendees_Confirmed": True,
        }

        result = z3_engine.verify(ast, facts)

        # Sheet_Done=True thỏa OR đầu, Attendees_Confirmed=True thỏa OR sau
        assert result.satisfied is True


# ─────────────────────────────────────────────
# Integration: Parser + Z3
# ─────────────────────────────────────────────

class TestParserZ3Integration:
    """Integration tests: Parser → Z3."""

    def test_full_pipeline_vietnamese(self):
        """
        Test pipeline đầy đủ với điều kiện tiếng Việt đã được parse.
        Giả lập kết quả LLM đã chuyển sang logic expression.
        """
        # LLM đã convert "Slide cập nhật hoặc Sheet chốt số. Bắt buộc Manager rảnh"
        # thành:
        logic_expression = "(Slide_Done or Sheet_Done) and Manager_Free"

        ast = parse(logic_expression)
        atoms = get_atoms(ast)

        assert "Slide_Done" in atoms
        assert "Sheet_Done" in atoms
        assert "Manager_Free" in atoms

        # Case 1: RESCHEDULED (test case bắt buộc)
        facts_fail = {
            "Slide_Done": False,
            "Sheet_Done": True,
            "Manager_Free": False,
        }
        result_fail = z3_engine.verify(ast, facts_fail)
        assert result_fail.satisfied is False
        assert "Manager_Free" in result_fail.unsatisfied_conditions

        # Case 2: READY
        facts_pass = {
            "Slide_Done": True,
            "Sheet_Done": True,
            "Manager_Free": True,
        }
        result_pass = z3_engine.verify(ast, facts_pass)
        assert result_pass.satisfied is True
        assert result_pass.unsatisfied_conditions == []
