"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { cuocHopApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { StatusBadge } from "@/components/StatusBadge";
import { Plus, Search, Filter, CalendarDays, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

export default function CuocHopPage() {
  const qc = useQueryClient();
  const [trangThai, setTrangThai] = useState("");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["cuoc-hop", trangThai],
    queryFn: () => cuocHopApi.danhSach({ trang_thai: trangThai || undefined }).then((r) => r.data),
  });

  const danhGiaMutation = useMutation({
    mutationFn: (id: string) => cuocHopApi.danhGia(id),
    onSuccess: (_, id) => {
      toast.success("AI đang đánh giá cuộc họp...");
      qc.invalidateQueries({ queryKey: ["cuoc-hop"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Đánh giá thất bại"),
  });

  const xoaMutation = useMutation({
    mutationFn: (id: string) => cuocHopApi.xoa(id),
    onSuccess: () => {
      toast.success("Đã xóa cuộc họp");
      qc.invalidateQueries({ queryKey: ["cuoc-hop"] });
    },
    onError: () => toast.error("Xóa thất bại"),
  });

  const meetings = data?.items ?? [];
  const filtered = search
    ? meetings.filter((m: any) => m.title.toLowerCase().includes(search.toLowerCase()))
    : meetings;

  const statusOptions = [
    { value: "", label: "Tất cả" },
    { value: "pending", label: "Chờ đánh giá" },
    { value: "ready", label: "Sẵn sàng" },
    { value: "rescheduled", label: "Cần dời lịch" },
    { value: "evaluating", label: "Đang đánh giá" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Cuộc họp</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            {data?.total ?? 0} cuộc họp — quản lý và đánh giá sẵn sàng
          </p>
        </div>
        <Link href="/cuoc-hop/tao-moi" className="btn-primary flex items-center gap-2 self-start">
          <Plus size={16} />
          Tạo cuộc họp
        </Link>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            className="input pl-10"
            placeholder="Tìm kiếm cuộc họp..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="relative">
          <Filter size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <select
            className="input pl-10 pr-4 appearance-none cursor-pointer"
            value={trangThai}
            onChange={(e) => setTrangThai(e.target.value)}
          >
            {statusOptions.map((o) => (
              <option key={o.value} value={o.value} style={{ background: "#0f172a" }}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Meeting list */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-24 glass rounded-2xl animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="glass rounded-2xl p-16 flex flex-col items-center text-slate-500">
          <CalendarDays size={48} className="mb-4 opacity-20" />
          <p className="text-lg font-medium text-slate-400">Không có cuộc họp nào</p>
          <Link href="/cuoc-hop/tao-moi" className="mt-4 btn-primary text-sm">
            Tạo cuộc họp đầu tiên
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((m: any) => (
            <div key={m.id} className="glass-hover rounded-2xl p-5 flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                <CalendarDays size={22} className="text-violet-400" />
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 flex-wrap">
                  <Link
                    href={`/cuoc-hop/${m.id}`}
                    className="text-slate-100 font-semibold hover:text-violet-300 transition-colors"
                  >
                    {m.title}
                  </Link>
                  <StatusBadge status={m.status} size="sm" />
                </div>
                <p className="text-xs text-slate-500 mt-1">{formatDate(m.scheduled_at)}</p>
                <p className="text-xs text-slate-600 mt-0.5 truncate max-w-md">{m.rule}</p>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => danhGiaMutation.mutate(m.id)}
                  disabled={danhGiaMutation.isPending || m.status === "evaluating"}
                  className="btn-secondary flex items-center gap-1.5 text-sm py-1.5 px-3"
                  title="Kích hoạt AI đánh giá"
                >
                  <Sparkles size={14} className="text-violet-400" />
                  <span className="hidden sm:inline">Đánh giá AI</span>
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Xóa cuộc họp "${m.title}"?`)) xoaMutation.mutate(m.id);
                  }}
                  className="btn-danger p-2 rounded-xl"
                  title="Xóa cuộc họp"
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
