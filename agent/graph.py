"""
agent/graph.py — LangGraph StateGraph Definition

Flow: START → parse_input → fetch_facts → verify_logic → decide_action → END

Đặc điểm:
- Conditional routing: nếu error → skip to END
- Immutable state: mỗi node return new state fields
- Timeout toàn pipeline: 10s
"""

from langgraph.graph import StateGraph, END

from agent.state import MeetingState
from agent.nodes import (
    parse_input_node,
    fetch_facts_node,
    verify_logic_node,
    decide_action_node,
)
from core.logging import get_logger

logger = get_logger(__name__)


def _has_error(state: MeetingState) -> str:
    """
    Conditional edge: kiểm tra có error không.
    Nếu có → route to END sớm.
    """
    if state.get("error_code"):
        return "end_with_error"
    return "continue"


def build_graph() -> StateGraph:
    """
    Xây dựng LangGraph StateGraph cho Meeting Evaluation Pipeline.

    Topology:
        START
          ↓
        parse_input ──(error)──→ END
          ↓
        fetch_facts ──(error)──→ END
          ↓
        verify_logic ──(error)──→ END
          ↓
        decide_action
          ↓
        END
    """
    graph = StateGraph(MeetingState)

    # Đăng ký nodes
    graph.add_node("parse_input", parse_input_node)
    graph.add_node("fetch_facts", fetch_facts_node)
    graph.add_node("verify_logic", verify_logic_node)
    graph.add_node("decide_action", decide_action_node)

    # Entry point
    graph.set_entry_point("parse_input")

    # Edges với conditional error routing
    graph.add_conditional_edges(
        "parse_input",
        _has_error,
        {
            "continue": "fetch_facts",
            "end_with_error": END,
        },
    )

    graph.add_conditional_edges(
        "fetch_facts",
        _has_error,
        {
            "continue": "verify_logic",
            "end_with_error": END,
        },
    )

    graph.add_conditional_edges(
        "verify_logic",
        _has_error,
        {
            "continue": "decide_action",
            "end_with_error": END,
        },
    )

    graph.add_edge("decide_action", END)

    return graph


# Compile graph một lần duy nhất (singleton)
_compiled_graph = None


def get_compiled_graph():
    """
    Lấy compiled graph (lazy singleton).
    Compile chỉ một lần, tái sử dụng cho mọi request.
    """
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_graph()
        _compiled_graph = graph.compile()
        logger.info(
            "LangGraph đã được compile thành công",
            extra={"event": "graph_compiled"},
        )
    return _compiled_graph
