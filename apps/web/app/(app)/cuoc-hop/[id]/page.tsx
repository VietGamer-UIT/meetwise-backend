"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cuocHopApi } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ArrowLeft, Sparkles, CalendarDays, Clock, MapPin,
  Link as LinkIcon, FileCode2, History, CheckCircle2, XCircle,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

export default function ChiTietCuocHopPage({ params }: { params: { id: string } }) {
  const qc = useQueryClient();

  const { data: meeting, isLoading } = useQuery({
    queryKey: ["cuoc-hop", params.id],
    queryFn: () => cuocHopApi.chiTiet(params.id).then((r) => r.data),
  });

  const { data: lichSu } = useQuery({
    queryKey: ["lich-su-danh-gia", params.id],
    queryFn: () => cuocHopApi.lichSuDanhGia(params.id).then((r) => r.data),
    enabled: !!meeting,
  });

  const danhGiaMutation = useMutation({
    mutationFn: () => cuocHopApi.danhGia(params.id),
    onSuccess: () => {
      toast.success("AI đang phân tích...");
      // Poll lại sau 3 giây
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["cuoc-hop", params.id] });
        qc.invalidateQueries({ queryKey: ["lich-su-danh-gia", params.id] });
        qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
      }, 3000);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Đánh giá thất bại"),
  });

  if (isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-48 bg-white/5 rounded-xl" />
        <div className="h-64 glass rounded-2xl" />
      </div>
    );
  }
  if (!meeting) return <div className="text-slate-400">Không tìm thấy cuộc họp.</div>;

  const latestEval = lichSu?.records?.[0];
  const isReady = meeting.status === "ready";
  const isRescheduled = meeting.status === "rescheduled";

  return (
    <div className="max-w-3xl mx-auto space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <Link href="/cuoc-hop" className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 mb-4 w-fit">
          <ArrowLeft size={16} /> Quay lại danh sách
        </Link>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-100">{meeting.title}</h1>
            {meeting.description && (
              <p className="text-slate-400 text-sm mt-1">{meeting.description}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={meeting.status} />
            <button
              onClick={() => danhGiaMutation.mutate()}
              disabled={danhGiaMutation.isPending || meeting.status === "evaluating"}
              className="btn-primary flex items-center gap-2"
            >
              <Sparkles size={16} />
              {danhGiaMutation.isPending || meeting.status === "evaluating"
                ? "Đang đánh giá..."
                : "Đánh giá AI"}
            </button>
          </div>
        </div>
      </div>

      {/* AI Result Banner */}
      {(isReady || isRescheduled) && latestEval && (
        <div className={`rounded-2xl p-5 border ${
          isReady
            ? "bg-green-500/10 border-green-500/30"
            : "bg-red-500/10 border-red-500/30"
        }`}>
          <div className="flex items-start gap-4">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              isReady ? "bg-green-500/20" : "bg-red-500/20"
            }`}>
              {isReady
                ? <CheckCircle2 size={22} className="text-green-400" />
                : <XCircle size={22} className="text-red-400" />
              }
            </div>
            <div className="flex-1">
              <p className={`text-lg font-bold ${isReady ? "text-green-400" : "text-red-400"}`}>
                {isReady ? "Cuộc họp Sẵn sàng!" : "Cần dời lịch"}
              </p>
              <p className="text-sm text-slate-300 mt-1">{latestEval.reason}</p>
              {latestEval.unsatisfied_conditions?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="text-xs text-slate-500">Điều kiện chưa thỏa:</span>
                  {latestEval.unsatisfied_conditions.map((c: string) => (
                    <span key={c} className="badge text-red-400 bg-red-400/10 border-red-400/20 text-[11px]">
                      {c}
                    </span>
                  ))}
                </div>
              )}
              <p className="text-xs text-slate-600 mt-2">
                Đánh giá lúc {formatRelative(latestEval.evaluated_at)} · {latestEval.latency_ms}ms
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Meeting info */}
      <div className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-5">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
            <CalendarDays size={17} className="text-violet-400" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">Thời gian</p>
            <p className="text-sm text-slate-200 mt-0.5 font-medium">{formatDate(meeting.scheduled_at)}</p>
          </div>
        </div>

        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
            <Clock size={17} className="text-violet-400" />
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide">Thời lượng</p>
            <p className="text-sm text-slate-200 mt-0.5 font-medium">{meeting.duration_minutes} phút</p>
          </div>
        </div>

        {meeting.location && (
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
              <MapPin size={17} className="text-violet-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide">Địa điểm</p>
              <p className="text-sm text-slate-200 mt-0.5">{meeting.location}</p>
            </div>
          </div>
        )}

        {meeting.meeting_url && (
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
              <LinkIcon size={17} className="text-violet-400" />
            </div>
            <div>
              <p className="text-xs text-slate-500 uppercase tracking-wide">Link họp</p>
              <a
                href={meeting.meeting_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-violet-400 hover:underline mt-0.5 block truncate"
              >
                {meeting.meeting_url}
              </a>
            </div>
          </div>
        )}

        <div className="flex items-start gap-3 sm:col-span-2">
          <div className="w-9 h-9 rounded-xl bg-violet-500/10 flex items-center justify-center flex-shrink-0">
            <FileCode2 size={17} className="text-violet-400" />
          </div>
          <div className="flex-1">
            <p className="text-xs text-slate-500 uppercase tracking-wide">Điều kiện họp</p>
            <code className="text-sm text-violet-300 mt-0.5 block font-mono leading-relaxed">
              {meeting.rule}
            </code>
          </div>
        </div>
      </div>

      {/* Evaluation history */}
      {lichSu?.records?.length > 0 && (
        <div className="glass rounded-2xl p-6">
          <h2 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-4">
            <History size={16} className="text-violet-400" />
            Lịch sử đánh giá ({lichSu.total})
          </h2>
          <div className="space-y-3">
            {lichSu.records.map((r: any) => (
              <div key={r.id} className="flex items-start gap-3 p-3 rounded-xl bg-white/[0.02]">
                <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  r.ai_status === "READY" ? "bg-green-500/20" : "bg-red-500/20"
                }`}>
                  {r.ai_status === "READY"
                    ? <CheckCircle2 size={14} className="text-green-400" />
                    : <XCircle size={14} className="text-red-400" />
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className={`text-sm font-medium ${r.ai_status === "READY" ? "text-green-400" : "text-red-400"}`}>
                      {r.ai_status === "READY" ? "Sẵn sàng" : "Cần dời lịch"}
                    </span>
                    <span className="text-xs text-slate-600">{formatRelative(r.evaluated_at)}</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5 truncate">{r.reason}</p>
                  <p className="text-xs text-slate-600">{r.latency_ms}ms · {r.parse_source}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
