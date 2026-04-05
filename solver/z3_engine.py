"""
solver/z3_engine.py — Z3 SMT Solver Engine (v4 Thread-Safe + Timeout)

Thread-Safety Architecture:
────────────────────────────
  SỐNG CÒN: z3.Solver() KHÔNG thread-safe. Nếu dùng như class attribute
  hoặc singleton bên trong solver, concurrent requests sẽ chia sẻ
  trạng thái → state bleed → kết quả sai, crash, hoặc undefined behavior.

  Fix: verify() tạo z3.Solver() CỤC BỘ mỗi lần gọi. Stateless hoàn toàn.
  Mỗi request có solver riêng, không bao giờ chia sẻ.

Timeout Defense:
────────────────
  solver.set("timeout", 3000): 3 giây hard limit cho Z3 solver.
  Ngăn chặn ReDoS-style vòng lặp vô hạn trên complex formulas.
  Nếu Z3 trả về z3.unknown → raise RuntimeError để caller xử lý.

Empty Unsat Core Fallback:
───────────────────────────
  Z3 có thể tối ưu hoá quá mức và trả về UNSAT với empty unsat_core().
  Trong trường hợp này: Smart Fallback — duyệt qua facts và gắn cờ
  tất cả điều kiện có value False là "thủ phạm".

Kết hợp verify_logic_node + run_in_executor:
  Mỗi request gọi verify() trong ThreadPoolExecutor → hoàn toàn concurrency-safe.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
    """
    Kết quả không thay đổi sau mỗi Z3 verification.

    Attributes:
        satisfied:               True nếu tất cả điều kiện thỏa mãn.
        unsatisfied_conditions:  Danh sách biến gây ra conflict (sorted).
        explanation:             Mô tả kết quả bằng tiếng Việt.
    """
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
        node:    AST node (AtomNode, AndNode, OrNode, NotNode).
        z3_vars: Mapping tên biến → Z3 Bool variable.

    Returns:
        Z3 BoolRef formula.

    Raises:
        RuntimeError: Nếu gặp biến chưa có trong facts hoặc node type không hỗ trợ.
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
# Z3 Engine (Stateless — Thread-Safe)
# ─────────────────────────────────────────────

class Z3Engine:
    """
    Z3 SMT Solver Engine cho Meeting Readiness Evaluation.

    THIẾT KẾ STATELESS:
    Không có instance state nào.
    z3.Solver() được tạo CỤC BỘ trong mỗi lần gọi verify() →
    hoàn toàn thread-safe cho concurrent requests.

    Quy trình verify():
    1. Lấy tất cả atoms từ AST (deduplicated, order-preserved)
    2. Tạo Z3 Bool variables (local, không chia sẻ)
    3. Tạo local z3.Solver() với timeout 3000ms
    4. assert_and_track() từng fact để có unsat_core chính xác
    5. Assert điều kiện chính
    6. Check → SAT / UNSAT / UNKNOWN
    7. UNSAT → extract unsatisfied conditions từ core
       → Empty core → Smart Fallback (False facts)
    """

    def verify(
        self,
        ast: ConditionNode,
        facts: Dict[str, bool],
    ) -> VerifyResult:
        """
        Kiểm tra xem tập facts có thỏa mãn condition AST không.

        Method này được gọi từ asyncio.run_in_executor(), có thể chạy
        đồng thời bởi nhiều thread. Hoàn toàn stateless — an toàn.

        Args:
            ast:   Root node của condition AST.
            facts: Dict mapping variable_name → bool value.

        Returns:
            VerifyResult (frozen dataclass, immutable).

        Raises:
            RuntimeError: Nếu Z3 gặp lỗi internal hoặc UNKNOWN result.
        """
        try:
            return self._do_verify(ast, dict(facts))  # Tạo bản copy để tránh mutation
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
        """Internal: thực hiện verification với local solver."""

        # 1. Lấy atoms từ AST (deduplicated nhưng giữ nguyên thứ tự xuất hiện đầu tiên)
        required_atoms = get_atoms(ast)  # get_atoms đã được fixed với dict.fromkeys()

        # 2. Tạo Z3 Bool variables (local — KHÔNG shared state)
        z3_vars: Dict[str, z3.BoolRef] = {
            name: z3.Bool(name) for name in required_atoms
        }

        # 3. Tạo Solver CỤC BỘ với unsat_core support và timeout 3000ms.
        #    CRITICAL: z3.Solver() PHẢI được tạo ở đây, không phải ở class level.
        #    Nếu tạo ở class level → shared state giữa threads → state bleed.
        solver = z3.Solver()
        solver.set(unsat_core=True)
        solver.set("timeout", 3000)  # 3 giây — ngăn ReDoS / vòng lặp vô hạn

        # 4. Assert giá trị từng variable với assert_and_track()
        #    Label cho phép extract chính xác biến nào gây ra conflict.
        fact_labels: Dict[str, str] = {}  # label_name → atom_name

        for atom_name in required_atoms:
            if atom_name not in facts:
                # Biến chưa có fact → mặc định False (pessimistic)
                logger.warning(
                    f"Biến '{atom_name}' không có trong facts → mặc định False",
                    extra={"event": "missing_fact", "variable": atom_name},
                )
                facts[atom_name] = False

            z3_var = z3_vars[atom_name]
            fact_value = facts[atom_name]

            label_name = f"fact_{atom_name}"
            label = z3.Bool(label_name)
            fact_labels[label_name] = atom_name

            if fact_value:
                solver.assert_and_track(z3_var, label)
            else:
                solver.assert_and_track(z3.Not(z3_var), label)

        # 5. Assert điều kiện chính
        condition_formula = _ast_to_z3(ast, z3_vars)
        condition_label = z3.Bool("condition_main")
        solver.assert_and_track(condition_formula, condition_label)

        # 6. Check satisfiability
        result = solver.check()

        logger.info(
            "Z3 check hoàn thành",
            extra={
                "event": "z3_check",
                "result": str(result),
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
            unsat_core = solver.unsat_core()
            unsatisfied = self._extract_unsatisfied(
                unsat_core=unsat_core,
                fact_labels=fact_labels,
                facts=facts,
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
            # z3.unknown — timeout hoặc solver bị overwhelmed
            raise RuntimeError(
                "Z3 không thể xác định kết quả (unknown/timeout). "
                "Có thể do formula quá phức tạp hoặc timeout 3000ms bị vượt quá."
            )

    def _extract_unsatisfied(
        self,
        unsat_core: Any,
        fact_labels: Dict[str, str],  # label_name → atom_name
        facts: Dict[str, bool],
    ) -> List[str]:
        """
        Phân tích unsat_core để tìm các biến gây ra conflict.

        Smart Fallback cho Empty Unsat Core:
        Z3 có thể tối ưu formula và trả về unsat_core rỗng khi:
        - Formula bị short-circuit
        - Solver quyết định bằng unit propagation không cần tracking

        Trong trường hợp đó: duyệt qua facts và gắn cờ tất cả điều kiện
        có value False là thủ phạm (conservative/safe fallback).

        Args:
            unsat_core: z3 unsat core expression list.
            fact_labels: Mapping từ Z3 label name → atom name.
            facts:       Dict fact values (để fallback).

        Returns:
            Sorted list of unsatisfied atom names.
        """
        unsatisfied = []
        core_names = {str(label) for label in unsat_core}

        # Primary: extract từ unsat_core labels
        for label_name, atom_name in fact_labels.items():
            if label_name in core_names:
                unsatisfied.append(atom_name)

        # Smart Fallback: unsat_core rỗng (Z3 over-optimization)
        if not unsatisfied:
            logger.warning(
                "Unsat core rỗng (Z3 over-optimization) — dùng Smart Fallback: "
                "flag all False facts as unsatisfied",
                extra={"event": "unsat_core_empty_fallback"},
            )
            # Chỉ flag các facts thuộc required atoms (không phải toàn bộ facts dict)
            unsatisfied = [
                atom_name
                for label_name, atom_name in fact_labels.items()
                if facts.get(atom_name) is False
            ]

        return sorted(unsatisfied)  # Sort để deterministic output


# ─────────────────────────────────────────────
# Singleton (stateless engine — safe to share)
# ─────────────────────────────────────────────

z3_engine = Z3Engine()
