-- ============================================================
-- MeetWise V2 — Supabase Database Schema
-- Migration: 001_initial_schema.sql
--
-- Thứ tự tạo bảng (theo dependency):
--   1. user_profiles     (phụ thuộc auth.users của Supabase)
--   2. teams             (tổ chức/nhóm)
--   3. team_members      (thành viên nhóm)
--   4. meetings          (cuộc họp - dữ liệu CRUD)
--   5. meeting_documents (tài liệu đính kèm)
--   6. evaluation_records (lịch sử AI đánh giá)
--   7. notifications     (thông báo)
--
-- Row Level Security (RLS) được bật cho tất cả bảng.
-- Chạy với Supabase service_role key.
-- ============================================================

-- Bật extension cần thiết
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- 1. Bảng hồ sơ người dùng
--    Supabase Auth tự quản lý auth.users.
--    Bảng này lưu thêm thông tin profile.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.user_profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name       TEXT,
    organization    TEXT,                    -- Tên công ty/tổ chức
    job_title       TEXT,                    -- Chức danh
    avatar_url      TEXT,                    -- URL ảnh đại diện (Supabase Storage)
    timezone        TEXT DEFAULT 'Asia/Ho_Chi_Minh',
    language        TEXT DEFAULT 'vi',       -- Ngôn ngữ giao diện
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger tự cập nhật updated_at
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Trigger tự tạo profile khi user đăng ký
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, full_name)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', split_part(NEW.email, '@', 1))
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- RLS cho user_profiles
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Người dùng xem profile của chính mình"
    ON public.user_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Người dùng cập nhật profile của chính mình"
    ON public.user_profiles FOR UPDATE
    USING (auth.uid() = id);


-- ─────────────────────────────────────────────
-- 2. Bảng nhóm/tổ chức
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.teams (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT,
    owner_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER teams_updated_at
    BEFORE UPDATE ON public.teams
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Thành viên nhóm xem được nhóm"
    ON public.teams FOR SELECT
    USING (
        owner_id = auth.uid() OR
        id IN (SELECT team_id FROM public.team_members WHERE user_id = auth.uid())
    );

CREATE POLICY "Owner quản lý nhóm"
    ON public.teams FOR ALL
    USING (owner_id = auth.uid());


-- ─────────────────────────────────────────────
-- 3. Bảng thành viên nhóm
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.team_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id     UUID NOT NULL REFERENCES public.teams(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'member',   -- owner | admin | member
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(team_id, user_id)
);

ALTER TABLE public.team_members ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Xem danh sách thành viên nhóm của mình"
    ON public.team_members FOR SELECT
    USING (
        user_id = auth.uid() OR
        team_id IN (SELECT id FROM public.teams WHERE owner_id = auth.uid())
    );


-- ─────────────────────────────────────────────
-- 4. Bảng cuộc họp (CRUD — tách biệt AI state)
--
--    QUAN TRỌNG: Bảng này lưu metadata cuộc họp.
--    Kết quả AI đánh giá lưu trong evaluation_records.
--    Firestore (ai_lifecycle_status) lưu trạng thái pipeline.
-- ─────────────────────────────────────────────

CREATE TYPE meeting_status AS ENUM (
    'pending',      -- Mới tạo, chưa đánh giá
    'evaluating',   -- Đang chạy AI pipeline
    'ready',        -- AI trả về READY
    'rescheduled',  -- AI trả về RESCHEDULED
    'cancelled'     -- Đã hủy
);

CREATE TABLE IF NOT EXISTS public.meetings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    team_id         UUID REFERENCES public.teams(id) ON DELETE SET NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    scheduled_at    TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    location        TEXT,
    meeting_url     TEXT,                    -- Link Google Meet / Zoom
    rule            TEXT NOT NULL,           -- Điều kiện họp (tiếng Việt/Anh) → gửi AI
    status          meeting_status NOT NULL DEFAULT 'pending',
    last_evaluated_at TIMESTAMPTZ,           -- Thời điểm AI đánh giá gần nhất
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER meetings_updated_at
    BEFORE UPDATE ON public.meetings
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Index để tăng tốc query phổ biến
CREATE INDEX idx_meetings_owner_id ON public.meetings(owner_id);
CREATE INDEX idx_meetings_scheduled_at ON public.meetings(scheduled_at);
CREATE INDEX idx_meetings_status ON public.meetings(status);
CREATE INDEX idx_meetings_team_id ON public.meetings(team_id);

ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Chủ sở hữu quản lý cuộc họp của mình"
    ON public.meetings FOR ALL
    USING (owner_id = auth.uid());

CREATE POLICY "Thành viên nhóm xem cuộc họp của nhóm"
    ON public.meetings FOR SELECT
    USING (
        team_id IN (
            SELECT team_id FROM public.team_members WHERE user_id = auth.uid()
        )
    );


-- ─────────────────────────────────────────────
-- 5. Bảng tài liệu đính kèm cuộc họp
-- ─────────────────────────────────────────────

CREATE TYPE document_type AS ENUM (
    'slide',    -- Tài liệu trình bày
    'sheet',    -- Bảng tính số liệu
    'report',   -- Báo cáo
    'agenda',   -- Chương trình họp
    'other'     -- Khác
);

CREATE TABLE IF NOT EXISTS public.meeting_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id  UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL,               -- URL file (Supabase Storage hoặc Google Drive)
    type        document_type DEFAULT 'other',
    file_size   BIGINT,                      -- Kích thước file (bytes)
    mime_type   TEXT,
    uploaded_by UUID REFERENCES auth.users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_meeting_documents_meeting_id ON public.meeting_documents(meeting_id);

ALTER TABLE public.meeting_documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Chủ sở hữu cuộc họp quản lý tài liệu"
    ON public.meeting_documents FOR ALL
    USING (
        meeting_id IN (SELECT id FROM public.meetings WHERE owner_id = auth.uid())
    );


-- ─────────────────────────────────────────────
-- 6. Bảng lịch sử AI đánh giá
--    Mỗi lần gọi /evaluate tạo một record mới.
--    Giữ toàn bộ lịch sử để analytics.
-- ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.evaluation_records (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id              UUID NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
    trace_id                TEXT NOT NULL,           -- UUID trace từ FastAPI pipeline
    ai_status               TEXT NOT NULL,           -- READY | RESCHEDULED
    reason                  TEXT,                    -- Giải thích lý do quyết định
    unsatisfied_conditions  TEXT[],                  -- Mảng tên điều kiện chưa thỏa
    ai_reasoning            JSONB,                   -- Full AIReasoning object từ API
    parse_source            TEXT,                    -- llm | fallback | skip_llm
    latency_ms              FLOAT,                   -- Thời gian xử lý (ms)
    evaluated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_evaluation_records_meeting_id ON public.evaluation_records(meeting_id);
CREATE INDEX idx_evaluation_records_ai_status ON public.evaluation_records(ai_status);
CREATE INDEX idx_evaluation_records_evaluated_at ON public.evaluation_records(evaluated_at DESC);

ALTER TABLE public.evaluation_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Chủ sở hữu cuộc họp xem lịch sử đánh giá"
    ON public.evaluation_records FOR SELECT
    USING (
        meeting_id IN (SELECT id FROM public.meetings WHERE owner_id = auth.uid())
    );

CREATE POLICY "Chỉ service role được ghi evaluation records"
    ON public.evaluation_records FOR INSERT
    WITH CHECK (true);   -- Backend dùng service_role key, bypass RLS


-- ─────────────────────────────────────────────
-- 7. Bảng thông báo
-- ─────────────────────────────────────────────

CREATE TYPE notification_type AS ENUM (
    'evaluation_complete',   -- AI đánh giá xong
    'meeting_rescheduled',   -- Cuộc họp bị dời
    'meeting_ready',         -- Cuộc họp đủ điều kiện
    'meeting_reminder',      -- Nhắc nhở trước giờ họp
    'team_invite',           -- Được mời vào nhóm
    'system'                 -- Thông báo hệ thống
);

CREATE TABLE IF NOT EXISTS public.notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    meeting_id  UUID REFERENCES public.meetings(id) ON DELETE CASCADE,
    type        notification_type NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT,
    action_url  TEXT,                        -- URL khi click vào thông báo
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    read_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user_id ON public.notifications(user_id);
CREATE INDEX idx_notifications_is_read ON public.notifications(user_id, is_read);
CREATE INDEX idx_notifications_created_at ON public.notifications(created_at DESC);

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Người dùng chỉ xem thông báo của mình"
    ON public.notifications FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Người dùng đánh dấu đã đọc"
    ON public.notifications FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Chỉ service role được tạo thông báo"
    ON public.notifications FOR INSERT
    WITH CHECK (true);


-- ─────────────────────────────────────────────
-- Views tiện ích
-- ─────────────────────────────────────────────

-- Dashboard stats: số liệu tổng quan theo user
CREATE OR REPLACE VIEW public.dashboard_stats AS
SELECT
    m.owner_id,
    COUNT(*) AS total_meetings,
    COUNT(*) FILTER (WHERE m.status = 'ready') AS ready_count,
    COUNT(*) FILTER (WHERE m.status = 'rescheduled') AS rescheduled_count,
    COUNT(*) FILTER (WHERE m.status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE m.last_evaluated_at >= NOW() - INTERVAL '24 hours') AS evaluated_today,
    ROUND(
        COUNT(*) FILTER (WHERE m.status = 'ready')::NUMERIC /
        NULLIF(COUNT(*) FILTER (WHERE m.status IN ('ready', 'rescheduled')), 0) * 100,
        1
    ) AS readiness_rate
FROM public.meetings m
GROUP BY m.owner_id;

-- ─────────────────────────────────────────────
-- Dữ liệu mẫu (Dev seed — xóa trước production)
-- ─────────────────────────────────────────────

-- KHÔNG thêm dữ liệu mẫu trong migration production.
-- Xem file: database/seeds/dev_seed.sql
