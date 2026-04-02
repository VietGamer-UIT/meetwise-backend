"""
solver/z3_engine.py — Z3 SMT Solver Engine

Chức năng:
- Chuyển đổi AST → Z3 formulas
- assert_and_track() để lấy unsat_core chính xác
- Trả về {satisfied, unsatisfied_conditions}

Quy tắc:
- Z3 fail → raise RuntimeError → caller trả về INTERNAL_ERROR (500)
- Unsat core → danh sách điều kiện chưa thỏa mãn chính xác
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import z3

from solver.parser import (
    ConditionNode,
    AndNode,
    OrNode,
    NotNode,
    AtomNode,
    get_atoms,
)
from core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# Result Type
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class VerifyResult:
    """Kết quả từ Z3 verification."""
    satisfied: bool
    unsatisfied_conditions: List[str]
    explanation: str


# ─────────────────────────────────────────────
# AST → Z3 Converter
# ─────────────────────────────────────────────

def _ast_to_z3(
    node: ConditionNode,
    z3_vars: Dict[str, z3.BoolRef],
) -> z3.BoolRef:
    """
    Đệ quy chuyển đổi AST node thành Z3 formula.

    Args:
        node: AST node
        z3_vars: mapping tên biến → Z3 Bool variable

    Returns:
        Z3 BoolRef formula

    Raises:
        RuntimeError: Nếu gặp node type không hỗ trợ
    """
    if isinstance(node, AtomNode):
        var = z3_vars.get(node.name)
        if var is None:
            raise RuntimeError(
                f"Biến '{node.name}' không tồn tại trong facts. "
                f"Các biến hợp lệ: {list(z3_vars.keys())}"
            )
        return var

    elif isinstance(node, AndNode):
        left = _ast_to_z3(node.left, z3_vars)
        right = _ast_to_z3(node.right, z3_vars)
        return z3.And(left, right)

    elif isinstance(node, OrNode):
        left = _ast_to_z3(node.left, z3_vars)
        right = _ast_to_z3(node.right, z3_vars)
        return z3.Or(left, right)

    elif isinstance(node, NotNode):
        operand = _ast_to_z3(node.operand, z3_vars)
        return z3.Not(operand)

    else:
        raise RuntimeError(f"Node type không hỗ trợ: {type(node)}")


# ─────────────────────────────────────────────
# Z3 Engine
# ─────────────────────────────────────────────

class Z3Engine:
    """
    Z3 SMT Solver Engine cho Meeting Readiness Evaluation.

    Quy trình:
    1. Tạo Z3 Bool variables từ facts
    2. Assert giá trị từng variable theo facts
    3. Assert condition formula
    4. Check satisfiability
    5. Nếu UNSAT → extract unsat_core để biết điều kiện nào fail
    """

    def verify(
        self,
        ast: ConditionNode,
        facts: Dict[str, bool],
    ) -> VerifyResult:
        """
        Kiểm tra xem tập facts có thỏa mãn condition AST không.

        Args:
            ast: Root node của condition AST
            facts: Dict mapping variable_name → bool value

        Returns:
            VerifyResult với satisfied=True/False và unsat_core

        Raises:
            RuntimeError: Nếu Z3 gặp lỗi internal
        """
        try:
            return self._do_verify(ast, facts)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Z3 engine gặp lỗi không mong đợi: {exc}"
            ) from exc

    def _do_verify(
        self,
        ast: ConditionNode,
        facts: Dict[str, bool],
    ) -> VerifyResult:
        """Internal verification logic."""

        # 1. Lấy tất cả atoms cần thiết từ AST
        required_atoms = list(set(get_atoms(ast)))

        # 2. Tạo Z3 variables cho mỗi atom
        z3_vars: Dict[str, z3.BoolRef] = {
            name: z3.Bool(name) for name in required_atoms
        }

        # 3. Tạo Solver với unsat_core support
        try:
            solver = z3.Solver()
            solver.set(unsat_core=True)
        except Exception as e:
            raise RuntimeError(f"Z3 lỗi: {e}")

        # 4. Assert giá trị từng variable từ facts
        #    Dùng assert_and_track để có thể extract unsat_core
        fact_labels: Dict[str, z3.BoolRef] = {}
        for atom_name in required_atoms:
            if atom_name not in facts:
                # Biến chưa có fact → mặc định False
                logger.warning(
                    f"Biến '{atom_name}' không có trong facts → mặc định False",
                    extra={
                        "event": "missing_fact",
                        "variable": atom_name,
                    },
                )
                facts = {**facts, atom_name: False}

            z3_var = z3_vars[atom_name]
            fact_value = facts[atom_name]

            # Label để track trong unsat_core
            label_name = f"fact_{atom_name}"
            label = z3.Bool(label_name)
            fact_labels[label_name] = atom_name

            if fact_value:
                solver.assert_and_track(z3_var, label)
            else:
                solver.assert_and_track(z3.Not(z3_var), label)

        # 5. Assert điều kiện chính cần thỏa mãn
        condition_formula = _ast_to_z3(ast, z3_vars)
        condition_label = z3.Bool("condition_main")
        solver.assert_and_track(condition_formula, condition_label)

        # 6. Check
        result = solver.check()

        logger.info(
            "Z3 check hoàn thành",
            extra={
                "event": "z3_check",
                "result": str(result),
                "facts": facts,
                "required_atoms": required_atoms,
            },
        )

        if result == z3.sat:
            return VerifyResult(
                satisfied=True,
                unsatisfied_conditions=[],
                explanation="Tất cả điều kiện đã thỏa mãn. Cuộc họp có thể diễn ra.",
            )

        elif result == z3.unsat:
            # Extract unsat_core để biết điều kiện nào vi phạm
            unsat_core = solver.unsat_core()
            unsatisfied = self._extract_unsatisfied(
                unsat_core, fact_labels, facts
            )

            explanation = (
                f"Các điều kiện chưa thỏa mãn: {', '.join(unsatisfied)}. "
                "Cuộc họp cần được dời lại."
                if unsatisfied
                else "Điều kiện chính không thể thỏa mãn với facts hiện tại."
            )

            return VerifyResult(
                satisfied=False,
                unsatisfied_conditions=unsatisfied,
                explanation=explanation,
            )

        else:
            # z3.unknown — không xác định được
            raise RuntimeError(
                "Z3 không thể xác định kết quả (unknown). "
                "Vui lòng kiểm tra lại điều kiện."
            )

    def _extract_unsatisfied(
        self,
        unsat_core: Any,
        fact_labels: Dict[str, str],  # label_name → atom_name
        facts: Dict[str, bool],
    ) -> List[str]:
        """
        Phân tích unsat_core để tìm các biến gây ra conflict.

        Logic:
        - Nếu condition_main có trong core → check từng fact label
        - Tìm các fact label trong core → đó là biến gây fail
        """
        unsatisfied = []

        core_names = {str(label) for label in unsat_core}

        # Kiểm tra từng fact label xem có trong core không
        for label_name, atom_name in fact_labels.items():
            if label_name in core_names:
                unsatisfied.append(atom_name)

        # Nếu không extract được → trả về tất cả atoms có value False
        if not unsatisfied:
            # Fallback:
            logger.warning(
                "Không extract được unsatisfied từ core, dùng fallback",
                extra={"event": "unsat_core_fallback"},
            )
            unsatisfied = [k for k, v in facts.items() if v is False]

        return sorted(unsatisfied)  # Sort để deterministic


# Singleton
z3_engine = Z3Engine()
