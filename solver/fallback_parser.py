"""
solver/fallback_parser.py — Deterministic Rule-Based Fallback Parser

Khi LLM không khả dụng (quota, timeout, 429...), hệ thống
PHẢI vẫn chạy được bằng parser này.

Đặc điểm:
- Hoàn toàn KHÔNG dùng LLM
- Deterministic: cùng input → cùng output
- Không bao giờ raise exception (NEVER crash)
- Hỗ trợ tiếng Việt + English keywords
- Nếu parse hoàn toàn thất bại → safe default: "Manager_Free"

Thuật toán:
1. Normalize text (lowercase, remove punctuation thừa)
2. Map natural language phrases → canonical variable names
3. Map VN/EN conjunctions → logic operators
4. Sắp xếp tokens thành logic formula string
5. Validate bằng parser.py (recursive descent)
6. Fallback về safe default nếu vẫn fail

Function Contract:
    fallback_parse_rule(text: str) -> dict:
        {
            "logic_formula": str,       # e.g., "(Slide_Done or Sheet_Done) and Manager_Free"
            "variables": dict[str, str], # e.g., {"Slide_Done": "slide condition"}
            "execution_plan": list[str], # ordered steps
            "parse_mode": str,           # "full" | "partial" | "default"
            "confidence": float          # 0.0 - 1.0
        }
"""

import re
from typing import Dict, List, Optional, Tuple

from core.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────
# Keyword → Variable Mapping
# ─────────────────────────────────────────────
#
# Thứ tự QUAN TRỌNG: phrase dài trước, từ ngắn sau
# (để tránh match "slide" trong "slide cập nhật xong")

_PHRASE_TO_VAR: List[Tuple[str, str]] = [
    # ── Slide ──────────────────────────────────
    ("slide cập nhật",    "Slide_Done"),
    ("slide đã cập nhật", "Slide_Done"),
    ("slide xong",        "Slide_Done"),
    ("slide hoàn thành",  "Slide_Done"),
    ("slide done",        "Slide_Done"),
    ("slide updated",     "Slide_Done"),
    ("slide",             "Slide_Done"),
    ("slide_done",        "Slide_Done"),

    # ── Sheet ───────────────────────────────────
    ("sheet chốt số",    "Sheet_Done"),
    ("sheet đã chốt",    "Sheet_Done"),
    ("sheet chốt",       "Sheet_Done"),
    ("sheet xong",       "Sheet_Done"),
    ("sheet hoàn thành", "Sheet_Done"),
    ("sheet done",       "Sheet_Done"),
    ("sheet finalized",  "Sheet_Done"),
    ("sheet",            "Sheet_Done"),
    ("sheet_done",       "Sheet_Done"),

    # ── Manager ─────────────────────────────────
    ("manager rảnh",        "Manager_Free"),
    ("manager có mặt",      "Manager_Free"),
    ("manager available",   "Manager_Free"),
    ("manager free",        "Manager_Free"),
    ("quản lý rảnh",        "Manager_Free"),
    ("manager",             "Manager_Free"),
    ("manager_free",        "Manager_Free"),

    # ── Attendees ───────────────────────────────
    ("attendees xác nhận",  "Attendees_Confirmed"),
    ("mọi người xác nhận",  "Attendees_Confirmed"),
    ("mọi người confirm",   "Attendees_Confirmed"),
    ("attendees confirmed", "Attendees_Confirmed"),
    ("attendees",           "Attendees_Confirmed"),
    ("attendees_confirmed", "Attendees_Confirmed"),

    # ── Room ────────────────────────────────────
    ("phòng đã book",   "Room_Booked"),
    ("phòng book rồi",  "Room_Booked"),
    ("room booked",     "Room_Booked"),
    ("room",            "Room_Booked"),
    ("room_booked",     "Room_Booked"),
]


# ─────────────────────────────────────────────
# Conjunction Mapping
# ─────────────────────────────────────────────

# Pattern → operator token (sẽ replace trong text)
_CONJUNCTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # AND triggers
    (re.compile(r"\bvà\b",        re.I | re.U), " and "),
    (re.compile(r"\bbắt buộc\b",  re.I | re.U), " and "),
    (re.compile(r"\bphải\b",      re.I | re.U), " and "),
    (re.compile(r"\bngoài ra\b",  re.I | re.U), " and "),
    (re.compile(r"\bthêm\b",      re.I | re.U), " and "),
    (re.compile(r"\bkèm\b",       re.I | re.U), " and "),
    (re.compile(r"\band\b",       re.I),         " and "),

    # OR triggers
    (re.compile(r"\bhoặc\b",      re.I | re.U), " or "),
    (re.compile(r"\bhoac\b",      re.I | re.U), " or "),   # không dấu
    (re.compile(r"\bor\b",        re.I),         " or "),

    # NOT triggers
    (re.compile(r"\bkhông phải\b", re.I | re.U), " not "),
    (re.compile(r"\bchưa\b",       re.I | re.U), " not "),
    (re.compile(r"\bnot\b",        re.I),         " not "),
    (re.compile(r"\bkhông\b",      re.I | re.U), " not "),
]

# Phrases gợi ý conditional (hay xuất hiện trước điều kiện, bỏ qua)
_IGNORE_PHRASES: List[re.Pattern] = [
    re.compile(r"chỉ họp nếu",       re.I | re.U),
    re.compile(r"chỉ khi",           re.I | re.U),
    re.compile(r"cuộc họp diễn ra",  re.I | re.U),
    re.compile(r"điều kiện",         re.I | re.U),
    re.compile(r"yêu cầu",           re.I | re.U),
    re.compile(r"cần thiết",         re.I | re.U),
    re.compile(r"cần có",            re.I | re.U),
    re.compile(r"meeting can proceed", re.I),
    re.compile(r"only if",           re.I),
    re.compile(r"only when",         re.I),
    re.compile(r"requires",          re.I),
]

# Safe default khi không parse được gì
_SAFE_DEFAULT_FORMULA = "Manager_Free"
_SAFE_DEFAULT_VARIABLES = {"Manager_Free": "manager availability (default fallback)"}


# ─────────────────────────────────────────────
# Main Function
# ─────────────────────────────────────────────

def fallback_parse_rule(text: str) -> Dict:
    """
    Parse rule text thành logic formula — KHÔNG dùng LLM.

    KHÔNG BAO GIỜ raise exception.
    Luôn trả về một dict hợp lệ với logic_formula.

    Args:
        text: Rule text ngôn ngữ tự nhiên (VN hoặc EN)

    Returns:
        {
            "logic_formula": str,         # logic expression hợp lệ
            "variables": dict[str, str],   # var → mô tả
            "execution_plan": list[str],   # ordered steps để debug
            "parse_mode": str,             # "full"|"partial"|"default"
            "confidence": float            # độ tin cậy 0.0-1.0
        }
    """
    plan: List[str] = []

    try:
        plan.append(f"input: {text[:100]}")

        # Bước 1: Pre-process
        cleaned = _preprocess(text)
        plan.append(f"after_preprocess: {cleaned[:100]}")

        # Bước 2: Extract variables (phrase → var mapping)
        extracted_vars: Dict[str, str] = {}
        normalized = _extract_variables(cleaned, extracted_vars)
        plan.append(f"extracted_vars: {list(extracted_vars.keys())}")
        plan.append(f"normalized: {normalized[:100]}")

        if not extracted_vars:
            logger.warning(
                "Fallback parser: không extract được variable nào, dùng default",
                extra={"event": "fallback_no_vars", "text_preview": text[:80]},
            )
            return _safe_default(plan, text)

        # Bước 3: Apply conjunctions
        formula_raw = _apply_conjunctions(normalized)
        plan.append(f"after_conjunctions: {formula_raw[:100]}")

        # Bước 4: Build logic formula string
        formula = _build_formula(formula_raw, extracted_vars)
        plan.append(f"built_formula: {formula}")

        # Bước 5: Validate với recursive descent parser
        is_valid, formula = _validate_and_fix(formula, extracted_vars)
        plan.append(f"validated: {formula} (valid={is_valid})")

        if not formula:
            return _safe_default(plan, text)

        # Tính confidence
        confidence = _estimate_confidence(extracted_vars, is_valid)
        parse_mode = "full" if is_valid else "partial"

        logger.info(
            f"Fallback parser: {parse_mode} mode, formula='{formula}', "
            f"vars={list(extracted_vars.keys())}, confidence={confidence:.2f}",
            extra={
                "event": "fallback_parse_success",
                "formula": formula,
                "variables": list(extracted_vars.keys()),
                "parse_mode": parse_mode,
                "confidence": confidence,
            },
        )

        return {
            "logic_formula": formula,
            "variables": extracted_vars,
            "execution_plan": plan,
            "parse_mode": parse_mode,
            "confidence": confidence,
        }

    except Exception as exc:
        # NEVER crash — log và trả safe default
        logger.error(
            f"Fallback parser exception (returning safe default): {exc}",
            extra={"event": "fallback_parse_exception", "error": str(exc)},
        )
        plan.append(f"exception: {exc}")
        return _safe_default(plan, text)


# ─────────────────────────────────────────────
# Step Helpers
# ─────────────────────────────────────────────

def _preprocess(text: str) -> str:
    """
    Normalize text:
    - Lowercase
    - Remove các phrase dẫn nhập (prefix phrases)
    - Normalize whitespace
    - Keep Vietnamese chars
    """
    s = text.lower().strip()

    # Loại bỏ các phrase dẫn nhập
    for pattern in _IGNORE_PHRASES:
        s = pattern.sub(" ", s)

    # Dấu phẩy → "and" (natural language list)
    s = s.replace(",", " and ")

    # Dấu chấm, chấm phẩy → khoảng trắng
    s = re.sub(r"[.;:!?]", " ", s)

    # Normalize whitespace
    s = re.sub(r"\s+", " ", s).strip()

    return s


def _extract_variables(text: str, var_map: Dict[str, str]) -> str:
    """
    Thay thế phrases tự nhiên → tên biến chuẩn.

    Dùng longest-match strategy (phrases dài → match trước).
    Điền var_map in-place.

    Returns:
        Text đã replace phrases bằng tên biến
    """
    result = text

    for phrase, var_name in _PHRASE_TO_VAR:
        if phrase.lower() in result:
            # Thay thế phrase → tên biến
            result = result.replace(phrase.lower(), f" {var_name} ")
            var_map[var_name] = phrase  # ghi nhận mapping

    # Normalize whitespace sau replace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _apply_conjunctions(text: str) -> str:
    """
    Thay thế VN/EN conjunctions → logic operators chuẩn.
    """
    result = text
    for pattern, replacement in _CONJUNCTION_PATTERNS:
        result = pattern.sub(replacement, result)

    # Normalize whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _build_formula(text: str, var_map: Dict[str, str]) -> str:
    """
    Xây dựng logic formula từ text đã normalize.

    Strategy:
    1. Extract tokens (vars + operators)
    2. Detect implicit AND: hai variables liền kề
    3. Assemble formula string

    Returns:
        Logic formula string (e.g., "(Slide_Done or Sheet_Done) and Manager_Free")
    """
    # Extract chỉ các parts liên quan (vars và operators)
    var_names = set(var_map.keys())

    # Tokenize thô: tách thành list parts
    parts = []
    remaining = text

    # Tìm tất cả var names có trong text (theo order xuất hiện)
    all_positions: List[Tuple[int, int, str]] = []  # (start, end, token)

    for var in var_names:
        for m in re.finditer(re.escape(var), remaining, re.I):
            all_positions.append((m.start(), m.end(), var))

    # Operator positions
    op_patterns = [
        (re.compile(r'\band\b', re.I), "and"),
        (re.compile(r'\bor\b',  re.I), "or"),
        (re.compile(r'\bnot\b', re.I), "not"),
    ]
    for pat, op in op_patterns:
        for m in pat.finditer(remaining):
            all_positions.append((m.start(), m.end(), op))

    # Sort by position
    all_positions.sort(key=lambda x: x[0])

    if not all_positions:
        # Không tìm thấy gì → trả về join vars bằng AND
        if len(var_names) == 1:
            return list(var_names)[0]
        return " and ".join(sorted(var_names))

    # Build token list từ positions
    tokens = [token for _, _, token in all_positions]

    if not tokens:
        return _safe_formula_from_vars(var_names)

    # Repair: thêm AND giữa hai identifiers liền kề (không có operator)
    repaired = []
    for i, tok in enumerate(tokens):
        repaired.append(tok)
        # Nếu tok là var và next cũng là var → chèn AND
        if i + 1 < len(tokens):
            next_tok = tokens[i + 1]
            tok_is_var = tok in var_names
            next_is_var = next_tok in var_names
            if tok_is_var and next_is_var:
                repaired.append("and")

    formula = " ".join(repaired)

    # Heuristic: nếu có cả OR và AND → wrap OR groups trong ngoặc
    formula = _add_parens_heuristic(formula, var_names)

    return formula.strip()


def _add_parens_heuristic(formula: str, var_names) -> str:
    """
    Heuristic: nếu có OR trong formula → wrap phần OR vào ngoặc
    để đảm bảo precedence đúng với AND bên ngoài.

    Ví dụ:
        "Slide_Done or Sheet_Done and Manager_Free"
        → "(Slide_Done or Sheet_Done) and Manager_Free"
    """
    tokens = formula.split()
    if "or" not in tokens:
        return formula  # Không có OR → không cần parens

    if "and" not in tokens:
        return formula  # Chỉ có OR → không cần parens

    # Tìm vị trí AND cuối
    # Phân tích pattern: [A or B] and C
    # Strategy đơn giản: tách tại "and" ngoài cùng cuối
    # Tìm OR group và AND group
    or_group: List[str] = []
    and_mandatory: List[str] = []

    # Tách: collect từng "X and Y" nếu có mandatory context
    # Đơn giản hóa: nếu "and" xuất hiện sau cụm "or"
    # → phần trước "and" cuối cùng là OR group
    # → phần sau là mandatory condition

    # Tìm tất cả positions của "and" token
    and_positions = [i for i, t in enumerate(tokens) if t.lower() == "and"]
    or_positions = [i for i, t in enumerate(tokens) if t.lower() == "or"]

    if not and_positions or not or_positions:
        return formula

    # Pattern đơn giản nhất: (or_group) and mandatory
    # Tìm AND cuối cùng ở level ngoài cùng
    last_and = and_positions[-1]

    # Phần trước AND cuối
    before_and = tokens[:last_and]
    # Phần sau AND cuối
    after_and = tokens[last_and + 1:]

    if not before_and or not after_and:
        return formula

    # Kiểm tra phần trước có OR không
    has_or_before = any(t.lower() == "or" for t in before_and)

    if has_or_before:
        # Wrap phần trước vào ngoặc
        before_str = " ".join(before_and)
        after_str = " ".join(after_and)

        # Tránh double-wrap nếu đã có parens
        if not before_str.startswith("("):
            before_str = f"({before_str})"

        return f"{before_str} and {after_str}"

    return formula


def _safe_formula_from_vars(var_names) -> str:
    """Tạo formula an toàn từ set var names."""
    if not var_names:
        return _SAFE_DEFAULT_FORMULA
    if len(var_names) == 1:
        return next(iter(var_names))
    return " and ".join(sorted(var_names))


def _validate_and_fix(
    formula: str,
    var_map: Dict[str, str],
) -> Tuple[bool, str]:
    """
    Validate formula bằng recursive descent parser.
    Nếu fail → thử simple join của các variables.

    Returns:
        (is_valid, formula_string)
    """
    try:
        from solver.parser import parse as parse_ast
        parse_ast(formula)
        return True, formula
    except SyntaxError:
        pass

    # Try đơn giản nhất: join vars bằng "and"
    try:
        if var_map:
            simple = " and ".join(sorted(var_map.keys()))
            from solver.parser import parse as parse_ast
            parse_ast(simple)
            logger.info(
                f"Fallback parser: dùng simple AND join: '{simple}'",
                extra={"event": "fallback_simple_join"},
            )
            return False, simple
    except Exception:
        pass

    # Cuối cùng trả formula gốc kể cả invalid (caller sẽ dùng default)
    return False, ""


def _estimate_confidence(var_map: Dict[str, str], is_valid: bool) -> float:
    """Ước lượng độ tin cậy của parse result."""
    if not var_map:
        return 0.0
    base = 0.6 if is_valid else 0.3
    # Nhiều vars hơn → confidence cao hơn (đã extract được nhiều thông tin)
    bonus = min(0.3, len(var_map) * 0.1)
    return round(min(1.0, base + bonus), 2)


def _safe_default(plan: List[str], original_text: str) -> Dict:
    """Trả về safe default result."""
    plan.append("using_safe_default")
    logger.warning(
        "Fallback parser: dùng safe default 'Manager_Free'",
        extra={
            "event": "fallback_safe_default",
            "original_text": original_text[:100],
        },
    )
    return {
        "logic_formula": _SAFE_DEFAULT_FORMULA,
        "variables": _SAFE_DEFAULT_VARIABLES,
        "execution_plan": plan,
        "parse_mode": "default",
        "confidence": 0.1,
    }


# ─────────────────────────────────────────────
# Convenience API
# ─────────────────────────────────────────────

def fallback_to_logic_expression(text: str) -> str:
    """
    Shortcut: trả về logic_formula string từ text.
    Được gọi từ parse_input_node khi LLM fail.

    NEVER raises.
    """
    result = fallback_parse_rule(text)
    return result["logic_formula"]
