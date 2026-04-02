import asyncio
from typing import Any, Dict, Optional
from agent.graph import get_compiled_graph
from schemas.request import EvaluateRequest

async def evaluate_meeting_service(request: EvaluateRequest, initial_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    graph = get_compiled_graph()
    # Chạy pipeline với overall timeout
    # Dùng getattr thay vì settings import trực tiếp để tránh circular error
    from core.config import settings
    return await asyncio.wait_for(
        graph.ainvoke(initial_state),
        timeout=settings.request_timeout_seconds,
    )
