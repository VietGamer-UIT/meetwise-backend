"""
solver/parser.py — Tokenizer + Recursive Descent Parser cho logic conditions

Hỗ trợ:
- Toán tử: AND (và), OR (hoặc), NOT (không/không phải)
- Dấu ngoặc: ( )
- Atoms: tên biến boolean (e.g., Slide_Done, Manager_Free)
- Cả Tiếng Việt và English keywords

Grammar (BNF):
    expr   := term (OR term)*
    term   := factor (AND factor)*
    factor := NOT factor | '(' expr ')' | atom
    atom   := IDENTIFIER

Ví dụ input:
    "Slide hoặc Sheet và không Manager_Free"
    "Slide_Done or Sheet_Done and not Manager_Free"
    "(Slide_Done or Sheet_Done) and Manager_Free"
"""

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Any


# ─────────────────────────────────────────────
# AST Nodes
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class AndNode:
    """Biểu diễn A AND B."""
    left: Any  # ConditionNode
    right: Any  # ConditionNode

    def __repr__(self) -> str:
        return f"AND({self.left!r}, {self.right!r})"


@dataclass(frozen=True)
class OrNode:
    """Biểu diễn A OR B."""
    left: Any
    right: Any

    def __repr__(self) -> str:
        return f"OR({self.left!r}, {self.right!r})"


@dataclass(frozen=True)
class NotNode:
    """Biểu diễn NOT A."""
    operand: Any

    def __repr__(self) -> str:
        return f"NOT({self.operand!r})"


@dataclass(frozen=True)
class AtomNode:
    """Biểu diễn một biến boolean đơn (leaf node)."""
    name: str

    def __repr__(self) -> str:
        return f"Atom({self.name!r})"


# Type alias
ConditionNode = AndNode | OrNode | NotNode | AtomNode


# ─────────────────────────────────────────────
# Tokenizer
# ─────────────────────────────────────────────

class TokenType(Enum):
    AND = auto()
    OR = auto()
    NOT = auto()
    LPAREN = auto()
    RPAREN = auto()
    IDENTIFIER = auto()
    COMMA = auto()   # Dấu phẩy = implicit AND trong văn bản tự nhiên
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    pos: int


# Mapping từ keywords (cả VN + EN) sang TokenType
_KEYWORDS: dict[str, TokenType] = {
    # Tiếng Việt
    "và": TokenType.AND,
    "hoặc": TokenType.OR,
    "không": TokenType.NOT,
    "khong": TokenType.NOT,  # không dấu
    "không phải": TokenType.NOT,
    # English
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    # Viết tắt
    "&&": TokenType.AND,
    "||": TokenType.OR,
    "!": TokenType.NOT,
}

# Regex cho identifier: chữ cái, số, gạch dưới (không bắt đầu bằng số)
_IDENTIFIER_RE = re.compile(r"[A-Za-zÀ-ỹ_][A-Za-zÀ-ỹ0-9_]*")
_WHITESPACE_RE = re.compile(r"\s+")


def tokenize(text: str) -> List[Token]:
    """
    Tokenize chuỗi điều kiện thành danh sách tokens.

    Args:
        text: Chuỗi điều kiện (đã sanitized)

    Returns:
        Danh sách Token

    Raises:
        SyntaxError: Nếu gặp ký tự không hợp lệ
    """
    tokens: List[Token] = []
    i = 0
    n = len(text)

    while i < n:
        # Skip whitespace
        m = _WHITESPACE_RE.match(text, i)
        if m:
            i = m.end()
            continue

        # Dấu ngoặc
        if text[i] == "(":
            tokens.append(Token(TokenType.LPAREN, "(", i))
            i += 1
            continue

        if text[i] == ")":
            tokens.append(Token(TokenType.RPAREN, ")", i))
            i += 1
            continue

        # Toán tử ký tự đặc biệt
        if text[i:i+2] == "&&":
            tokens.append(Token(TokenType.AND, "&&", i))
            i += 2
            continue
        if text[i:i+2] == "||":
            tokens.append(Token(TokenType.OR, "||", i))
            i += 2
            continue
        if text[i] == "!":
            tokens.append(Token(TokenType.NOT, "!", i))
            i += 1
            continue

        # Identifier hoặc keyword
        m = _IDENTIFIER_RE.match(text, i)
        if m:
            word = m.group(0)
            pos = i
            i = m.end()

            # Kiểm tra multi-word keyword "không phải"
            if word.lower() == "không":
                # Xem có "phải" theo sau không
                rest = _WHITESPACE_RE.match(text, i)
                j = rest.end() if rest else i
                next_m = _IDENTIFIER_RE.match(text, j)
                if next_m and next_m.group(0).lower() == "phải":
                    tokens.append(Token(TokenType.NOT, "không phải", pos))
                    i = next_m.end()
                    continue

            # Kiểm tra từ khóa
            token_type = _KEYWORDS.get(word.lower())
            if token_type is not None:
                tokens.append(Token(token_type, word, pos))
            else:
                tokens.append(Token(TokenType.IDENTIFIER, word, pos))
            continue

        # Ký tự không hợp lệ — bỏ qua các dấu câu phổ biến
        # Dấu phẩy = implicit AND (sẽ là COMMA token)
        if text[i] == ',':
            tokens.append(Token(TokenType.COMMA, ',', i))
            i += 1
            continue

        # Dấu chấm, chấm phẩy, dấu hỏi, dấu chấm than = bỏ qua được
        if text[i] in ".;:\"'!?":
            i += 1
            continue

        raise SyntaxError(
            f"Ký tự không hợp lệ tại vị trí {i}: '{text[i]}'"
        )

    tokens.append(Token(TokenType.EOF, "", n))
    return tokens


# ─────────────────────────────────────────────
# Recursive Descent Parser
# ─────────────────────────────────────────────

class Parser:
    """
    Recursive descent parser cho logic condition expressions.

    Grammar:
        expr   := term (OR term)*
        term   := factor (AND factor)*
        factor := NOT factor | '(' expr ')' | atom
        atom   := IDENTIFIER
    """

    def __init__(self, tokens: List[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def current(self) -> Token:
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return Token(TokenType.EOF, "", -1)

    def consume(self, expected_type: Optional[TokenType] = None) -> Token:
        token = self.current()
        if expected_type is not None and token.type != expected_type:
            raise SyntaxError(
                f"Mong đợi {expected_type.name} nhưng nhận được "
                f"{token.type.name} ('{token.value}') tại vị trí {token.pos}"
            )
        self.pos += 1
        return token

    def parse(self) -> ConditionNode:
        """Parse toàn bộ expression và trả về AST root."""
        if self.current().type == TokenType.EOF:
            raise SyntaxError("Expression rỗng: không có điều kiện nào")

        node = self.parse_expr()

        if self.current().type != TokenType.EOF:
            token = self.current()
            raise SyntaxError(
                f"Token thừa tại vị trí {token.pos}: '{token.value}'"
            )
        return node

    def parse_expr(self) -> ConditionNode:
        """expr := term (OR term)*"""
        node = self.parse_term()

        while self.current().type == TokenType.OR:
            self.consume(TokenType.OR)
            right = self.parse_term()
            node = OrNode(left=node, right=right)

        return node

    def parse_term(self) -> ConditionNode:
        """term := factor (AND | COMMA factor)*
        
        Dấu phẩy được xử lý như implicit AND trong văn bản tự nhiên.
        Ví dụ: "Slide_Done, Sheet_Done" → Slide_Done AND Sheet_Done
        """
        node = self.parse_factor()

        while self.current().type in (TokenType.AND, TokenType.COMMA):
            self.consume()  # consume AND hoặc COMMA
            # Nếu ngay sau còn COMMA liên tiếp → bỏ qua
            while self.current().type == TokenType.COMMA:
                self.consume()
            right = self.parse_factor()
            node = AndNode(left=node, right=right)

        return node

    def parse_factor(self) -> ConditionNode:
        """factor := NOT factor | '(' expr ')' | atom"""
        token = self.current()

        if token.type == TokenType.NOT:
            self.consume(TokenType.NOT)
            operand = self.parse_factor()
            return NotNode(operand=operand)

        if token.type == TokenType.LPAREN:
            self.consume(TokenType.LPAREN)
            node = self.parse_expr()
            if self.current().type != TokenType.RPAREN:
                raise SyntaxError(
                    f"Thiếu dấu ')' tại vị trí {self.current().pos}"
                )
            self.consume(TokenType.RPAREN)
            return node

        return self.parse_atom()

    def parse_atom(self) -> AtomNode:
        """atom := IDENTIFIER"""
        token = self.current()
        if token.type != TokenType.IDENTIFIER:
            raise SyntaxError(
                f"Mong đợi tên biến (identifier) nhưng nhận được "
                f"'{token.value}' ({token.type.name}) tại vị trí {token.pos}"
            )
        self.consume(TokenType.IDENTIFIER)
        return AtomNode(name=token.value)


def get_atoms(node: ConditionNode) -> List[str]:
    """
    Thu thập tất cả tên biến (atoms) từ AST, deduplicated.

    Giữ nguyên thứ tự xuất hiện đầu tiên (first-occurrence order) —
    quan trọng cho Z3 deterministic behavior và debug readability.

    Tại sao cần dedup:
      - Expression như "A and A" → get_atoms trả ["A", "A"]
      - Z3 sẽ tạo 2 Bool("A") riêng biệt → assertion conflict
      - dict.fromkeys() loại bỏ duplicate nhưng GIỮ NGUYÊN THỨ TỰ
        (Python 3.7+ dict là ordered)
      - sorted(set(...)) cũng dedup nhưng PHÁ VỠ thứ tự → không dùng

    Args:
        node: Root hoặc sub-node của condition AST.

    Returns:
        List[str]: Tên biến không trùng lặp, theo thứ tự xuất hiện đầu tiên.
    """
    def _collect(n: ConditionNode) -> List[str]:
        """Đệ quy thu thập atoms (có thể trùng lặp)."""
        if isinstance(n, AtomNode):
            return [n.name]
        elif isinstance(n, NotNode):
            return _collect(n.operand)
        elif isinstance(n, (AndNode, OrNode)):
            return _collect(n.left) + _collect(n.right)
        return []

    # dict.fromkeys(): O(n), giữ thứ tự xuất hiện đầu tiên, loại trùng lặp
    return list(dict.fromkeys(_collect(node)))


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

def parse(rule: str) -> ConditionNode:
    """
    Parse chuỗi rule ngôn ngữ tự nhiên thành AST.

    Args:
        rule: Chuỗi điều kiện (đã sanitized)

    Returns:
        Root node của AST

    Raises:
        SyntaxError: Nếu cú pháp không hợp lệ → caller nên return 400
    """
    tokens = tokenize(rule)
    parser = Parser(tokens)
    return parser.parse()
