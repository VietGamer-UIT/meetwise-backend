"""
services/meeting_crud_service.py — Business Logic cho Meeting CRUD

Tất cả operations đều async, dùng Supabase AsyncClient.

Thiết kế:
  - Mỗi method nhận user_id để enforce ownership
  - Không bao giờ trả về data của user khác
  - Lỗi DB → raise ValueError (HTTP 400) hoặc RuntimeError (HTTP 500)
"""

from typing import Optional
from uuid import UUID

from core.logging import get_logger
from models.meeting import MeetingCreate, MeetingListResponse, MeetingResponse, MeetingUpdate

logger = get_logger(__name__)


class MeetingCRUDService:
    """Service xử lý toàn bộ CRUD logic cho cuộc họp."""

    async def create(
        self,
        user_id: str,
        data: MeetingCreate,
    ) -> MeetingResponse:
        """
        Tạo cuộc họp mới.

        Args:
            user_id: ID của chủ sở hữu cuộc họp.
            data:    Dữ liệu cuộc họp từ request body.

        Returns:
            MeetingResponse: Cuộc họp vừa tạo.

        Raises:
            ValueError: Nếu dữ liệu không hợp lệ.
            RuntimeError: Nếu database lỗi.
        """
        from integrations.supabase_client import get_supabase

        supabase = await get_supabase()

        insert_data = {
            "owner_id": user_id,
            "title": data.title,
            "description": data.description,
            "scheduled_at": data.scheduled_at.isoformat(),
            "duration_minutes": data.duration_minutes,
            "location": data.location,
            "meeting_url": data.meeting_url,
            "rule": data.rule,
            "status": "pending",
            "team_id": str(data.team_id) if data.team_id else None,
        }

        try:
            result = await supabase.table("meetings").insert(insert_data).execute()
            if not result.data:
                raise RuntimeError("Không nhận được dữ liệu từ database sau khi tạo.")
            row = result.data[0]
            logger.info(
                f"Cuộc họp mới được tạo: {row['id']}",
                extra={"event": "meeting_created", "meeting_id": row["id"], "user_id": user_id},
            )
            return MeetingResponse(**row)
        except Exception as exc:
            if "duplicate" in str(exc).lower():
                raise ValueError("Cuộc họp với tiêu đề này đã tồn tại.")
            logger.error(f"Lỗi tạo cuộc họp: {exc}", extra={"event": "meeting_create_error"})
            raise RuntimeError(f"Không thể tạo cuộc họp: {exc}")

    async def list_meetings(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
    ) -> MeetingListResponse:
        """
        Lấy danh sách cuộc họp của user, có phân trang.

        Args:
            user_id:       ID user hiện tại.
            page:          Trang hiện tại (bắt đầu từ 1).
            page_size:     Số cuộc họp mỗi trang (tối đa 100).
            status_filter: Lọc theo trạng thái (optional).

        Returns:
            MeetingListResponse: Danh sách có phân trang.
        """
        from integrations.supabase_client import get_supabase

        supabase = await get_supabase()
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        try:
            query = (
                supabase.table("meetings")
                .select("*", count="exact")
                .eq("owner_id", user_id)
                .order("scheduled_at", desc=False)
                .range(offset, offset + page_size - 1)
            )

            if status_filter:
                query = query.eq("status", status_filter)

            result = await query.execute()

            total = result.count or 0
            items = [MeetingResponse(**row) for row in (result.data or [])]

            return MeetingListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                has_next=(offset + page_size) < total,
            )
        except Exception as exc:
            logger.error(f"Lỗi lấy danh sách cuộc họp: {exc}")
            raise RuntimeError(f"Không thể lấy danh sách cuộc họp: {exc}")

    async def get_by_id(self, user_id: str, meeting_id: str) -> MeetingResponse:
        """
        Lấy chi tiết một cuộc họp theo ID.

        Raises:
            ValueError: Nếu cuộc họp không tồn tại hoặc user không có quyền.
        """
        from integrations.supabase_client import get_supabase

        supabase = await get_supabase()

        try:
            result = (
                await supabase.table("meetings")
                .select("*")
                .eq("id", meeting_id)
                .eq("owner_id", user_id)
                .maybe_single()
                .execute()
            )

            if not result.data:
                raise ValueError("Cuộc họp không tồn tại hoặc bạn không có quyền truy cập.")

            return MeetingResponse(**result.data)
        except ValueError:
            raise
        except Exception as exc:
            logger.error(f"Lỗi lấy cuộc họp {meeting_id}: {exc}")
            raise RuntimeError(f"Không thể lấy thông tin cuộc họp: {exc}")

    async def update(
        self,
        user_id: str,
        meeting_id: str,
        data: MeetingUpdate,
    ) -> MeetingResponse:
        """
        Cập nhật cuộc họp. Chỉ cập nhật các fields được cung cấp.

        Raises:
            ValueError: Nếu cuộc họp không tồn tại.
        """
        from integrations.supabase_client import get_supabase

        supabase = await get_supabase()

        # Chỉ lấy các fields không phải None
        update_data = {
            k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if isinstance(v, UUID) else v)
            for k, v in data.model_dump(exclude_none=True).items()
        }

        try:
            result = (
                await supabase.table("meetings")
                .update(update_data)
                .eq("id", meeting_id)
                .eq("owner_id", user_id)
                .execute()
            )

            if not result.data:
                raise ValueError("Cuộc họp không tồn tại hoặc bạn không có quyền cập nhật.")

            logger.info(
                f"Cuộc họp cập nhật: {meeting_id}",
                extra={"event": "meeting_updated", "meeting_id": meeting_id},
            )
            return MeetingResponse(**result.data[0])
        except ValueError:
            raise
        except Exception as exc:
            logger.error(f"Lỗi cập nhật cuộc họp: {exc}")
            raise RuntimeError(f"Không thể cập nhật cuộc họp: {exc}")

    async def delete(self, user_id: str, meeting_id: str) -> None:
        """
        Xóa cuộc họp. Cascade delete tài liệu và lịch sử đánh giá.

        Raises:
            ValueError: Nếu cuộc họp không tồn tại.
        """
        from integrations.supabase_client import get_supabase

        supabase = await get_supabase()

        try:
            result = (
                await supabase.table("meetings")
                .delete()
                .eq("id", meeting_id)
                .eq("owner_id", user_id)
                .execute()
            )

            if not result.data:
                raise ValueError("Cuộc họp không tồn tại hoặc bạn không có quyền xóa.")

            logger.info(
                f"Cuộc họp đã xóa: {meeting_id}",
                extra={"event": "meeting_deleted", "meeting_id": meeting_id},
            )
        except ValueError:
            raise
        except Exception as exc:
            logger.error(f"Lỗi xóa cuộc họp: {exc}")
            raise RuntimeError(f"Không thể xóa cuộc họp: {exc}")

    async def trigger_ai_evaluation(
        self,
        user_id: str,
        meeting_id: str,
        override_facts: Optional[dict] = None,
    ) -> dict:
        """
        Kích hoạt AI evaluation cho cuộc họp.

        Flow:
          1. Lấy meeting data từ DB
          2. Cập nhật status → 'evaluating'
          3. Gọi AI engine (evaluate_service)
          4. Lưu kết quả vào evaluation_records
          5. Cập nhật meeting status → 'ready' | 'rescheduled'
          6. Tạo notification cho user

        Args:
            user_id:        ID user thực hiện đánh giá.
            meeting_id:     ID cuộc họp cần đánh giá.
            override_facts: Facts ghi đè (optional, dùng cho testing).

        Returns:
            dict: Kết quả AI evaluation (EvaluateResponse.model_dump()).

        Raises:
            ValueError: Nếu cuộc họp không tồn tại hoặc đang được đánh giá.
        """
        from integrations.supabase_client import get_supabase
        from schemas.request import EvaluateRequest
        from services.evaluate_service import evaluate_meeting_service
        from core.trace import generate_trace_id, set_trace_id, reset_trace_id
        from schemas.response import MeetingStatus
        import time

        # Lấy meeting data
        meeting = await self.get_by_id(user_id, meeting_id)

        if meeting.status == "evaluating":
            raise ValueError("Cuộc họp đang được đánh giá. Vui lòng đợi kết quả.")

        supabase = await get_supabase()

        # Cập nhật status → evaluating
        await supabase.table("meetings").update(
            {"status": "evaluating"}
        ).eq("id", meeting_id).execute()

        trace_id = generate_trace_id()
        token = set_trace_id(trace_id)
        request_start = time.perf_counter()

        try:
            eval_request = EvaluateRequest(
                meeting_id=meeting_id,
                rule=meeting.rule,
                override_facts=override_facts,
            )

            initial_state = {
                "trace_id": trace_id,
                "meeting_id": meeting_id,
                "request_start_time": request_start,
                "raw_rule": meeting.rule,
                "raw_facts": override_facts or {},
                "step_latencies": {},
            }

            result = await evaluate_meeting_service(eval_request, initial_state)

            if result is None:
                raise RuntimeError("AI pipeline trả về None.")

            ai_status = result.get("final_status", "RESCHEDULED")
            reason = result.get("final_reason", "Không xác định")
            unsatisfied = result.get("unsatisfied_conditions", [])
            latency_ms = round((time.perf_counter() - request_start) * 1000, 2)

            # Lưu evaluation record
            from schemas.response import AIReasoning
            fetched_facts = result.get("fetched_facts") or {}
            logic_expr = result.get("logic_expression", meeting.rule)

            ai_reasoning = {
                "logic": logic_expr,
                "evaluation": fetched_facts,
                "decision_trace": [
                    f"{k} = {'TRUE' if v else 'FALSE'}" for k, v in fetched_facts.items()
                ] + [f"Kết luận = {ai_status}"],
            }

            await supabase.table("evaluation_records").insert({
                "meeting_id": meeting_id,
                "trace_id": trace_id,
                "ai_status": ai_status,
                "reason": reason,
                "unsatisfied_conditions": unsatisfied,
                "ai_reasoning": ai_reasoning,
                "parse_source": result.get("parse_source", "unknown"),
                "latency_ms": latency_ms,
            }).execute()

            # Cập nhật meeting status
            new_status = "ready" if ai_status == MeetingStatus.READY else "rescheduled"
            await supabase.table("meetings").update({
                "status": new_status,
                "last_evaluated_at": "now()",
            }).eq("id", meeting_id).execute()

            # Tạo notification
            await self._create_evaluation_notification(
                user_id=user_id,
                meeting_id=meeting_id,
                meeting_title=meeting.title,
                ai_status=ai_status,
            )

            logger.info(
                f"AI evaluation hoàn thành: {meeting_id} → {ai_status}",
                extra={
                    "event": "ai_evaluation_complete",
                    "meeting_id": meeting_id,
                    "status": ai_status,
                    "latency_ms": latency_ms,
                },
            )

            return {
                "trace_id": trace_id,
                "meeting_id": meeting_id,
                "status": ai_status,
                "reason": reason,
                "unsatisfied_conditions": unsatisfied,
                "ai_reasoning": ai_reasoning,
                "latency_ms": latency_ms,
                "confidence": 1.0,
                "actions": [a for a in (result.get("executed_actions") or [])],
            }

        except Exception as exc:
            # Rollback meeting status về pending nếu evaluation fail
            await supabase.table("meetings").update(
                {"status": "pending"}
            ).eq("id", meeting_id).execute()
            logger.error(f"AI evaluation thất bại: {exc}", exc_info=True)
            raise RuntimeError(f"Đánh giá cuộc họp thất bại: {exc}")
        finally:
            reset_trace_id(token)

    async def _create_evaluation_notification(
        self,
        user_id: str,
        meeting_id: str,
        meeting_title: str,
        ai_status: str,
    ) -> None:
        """Tạo notification sau khi AI đánh giá xong (fire-and-forget)."""
        try:
            from integrations.supabase_client import get_supabase
            supabase = await get_supabase()

            is_ready = ai_status == "READY"
            notif_type = "meeting_ready" if is_ready else "meeting_rescheduled"
            title = f"✅ '{meeting_title}' sẵn sàng" if is_ready else f"⚠️ '{meeting_title}' cần dời lịch"

            await supabase.table("notifications").insert({
                "user_id": user_id,
                "meeting_id": meeting_id,
                "type": notif_type,
                "title": title,
                "body": "Nhấn để xem chi tiết kết quả đánh giá.",
                "action_url": f"/cuoc-hop/{meeting_id}",
            }).execute()
        except Exception as exc:
            # Notification fail không được ảnh hưởng evaluation
            logger.warning(f"Tạo notification thất bại (non-critical): {exc}")


# Singleton instance
meeting_crud_service = MeetingCRUDService()
