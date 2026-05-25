"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { thongBaoApi } from "@/lib/api";
import { formatRelative } from "@/lib/utils";
import { BellOff, CheckCheck, Trash2 } from "lucide-react";
import { toast } from "sonner";

const typeIcon: Record<string, string> = {
  meeting_ready: "✅",
  meeting_rescheduled: "⚠️",
  evaluation_complete: "🤖",
  team_invite: "👥",
  meeting_reminder: "⏰",
  system: "🔔",
};

export default function ThongBaoPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["thong-bao"],
    queryFn: () => thongBaoApi.danhSach().then((r) => r.data),
  });

  const docTatCaMut = useMutation({
    mutationFn: thongBaoApi.docTatCa,
    onSuccess: () => {
      toast.success("Đã đánh dấu tất cả đã đọc");
      qc.invalidateQueries({ queryKey: ["thong-bao"] });
    },
  });

  const docMut = useMutation({
    mutationFn: thongBaoApi.danhDauDaDoc,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["thong-bao"] }),
  });

  const xoaMut = useMutation({
    mutationFn: thongBaoApi.xoa,
    onSuccess: () => {
      toast.success("Đã xóa thông báo");
      qc.invalidateQueries({ queryKey: ["thong-bao"] });
    },
  });

  const notifications = data?.items ?? [];

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Thông báo</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {data?.unread_count ? (
              <span className="text-violet-400 font-medium">{data.unread_count} chưa đọc</span>
            ) : "Tất cả đã đọc"}
          </p>
        </div>
        {(data?.unread_count ?? 0) > 0 && (
          <button
            onClick={() => docTatCaMut.mutate()}
            disabled={docTatCaMut.isPending}
            className="btn-secondary flex items-center gap-2 text-sm"
          >
            <CheckCheck size={15} />
            Đọc tất cả
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 glass rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <div className="glass rounded-2xl p-16 flex flex-col items-center text-slate-500">
          <BellOff size={48} className="mb-4 opacity-20" />
          <p className="text-slate-400">Chưa có thông báo nào</p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((n: any) => (
            <div
              key={n.id}
              className={`flex items-start gap-4 p-4 rounded-2xl border transition-colors ${
                n.is_read
                  ? "glass border-transparent"
                  : "bg-violet-500/[0.06] border-violet-500/20"
              }`}
            >
              <div className="text-xl flex-shrink-0 mt-0.5">
                {typeIcon[n.type] ?? "🔔"}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${n.is_read ? "text-slate-300" : "text-slate-100"}`}>
                  {n.title}
                </p>
                {n.body && <p className="text-xs text-slate-500 mt-0.5">{n.body}</p>}
                <p className="text-xs text-slate-600 mt-1">{formatRelative(n.created_at)}</p>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {!n.is_read && (
                  <button
                    onClick={() => docMut.mutate(n.id)}
                    className="p-1.5 rounded-lg text-violet-400 hover:bg-violet-500/10 transition-colors"
                    title="Đánh dấu đã đọc"
                  >
                    <CheckCheck size={15} />
                  </button>
                )}
                <button
                  onClick={() => xoaMut.mutate(n.id)}
                  className="p-1.5 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  title="Xóa"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
