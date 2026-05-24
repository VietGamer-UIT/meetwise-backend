"use client";
import { useQuery } from "@tanstack/react-query";
import { cuocHopApi } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import { History, CheckCircle2, XCircle } from "lucide-react";

export default function LichSuPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["lich-su-all"],
    queryFn: () => cuocHopApi.danhSach({ trang_thai: undefined, kich_thuoc: 50 }).then((r) => r.data),
  });

  // Lấy các cuộc họp đã được đánh giá
  const evaluated = (data?.items ?? []).filter(
    (m: any) => ["ready", "rescheduled"].includes(m.status)
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Lịch sử đánh giá</h1>
        <p className="text-slate-400 text-sm mt-0.5">
          {evaluated.length} cuộc họp đã được AI đánh giá
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 glass rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : evaluated.length === 0 ? (
        <div className="glass rounded-2xl p-16 flex flex-col items-center text-slate-500">
          <History size={48} className="mb-4 opacity-20" />
          <p className="text-slate-400">Chưa có cuộc họp nào được đánh giá</p>
        </div>
      ) : (
        <div className="space-y-3">
          {evaluated.map((m: any) => (
            <div key={m.id} className="glass-hover rounded-2xl p-5 flex items-center gap-4">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                m.status === "ready" ? "bg-green-500/10" : "bg-red-500/10"
              }`}>
                {m.status === "ready"
                  ? <CheckCircle2 size={20} className="text-green-400" />
                  : <XCircle size={20} className="text-red-400" />
                }
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 font-medium truncate">{m.title}</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  Lịch họp: {formatDate(m.scheduled_at)}
                </p>
                {m.last_evaluated_at && (
                  <p className="text-xs text-slate-600">
                    Đánh giá {formatRelative(m.last_evaluated_at)}
                  </p>
                )}
              </div>
              <StatusBadge status={m.status} size="sm" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
