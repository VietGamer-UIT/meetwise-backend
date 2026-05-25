"use client";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  CalendarDays, CheckCircle2, XCircle, Clock,
  TrendingUp, Plus, ChevronRight, Zap,
} from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
} from "recharts";

export default function DashboardPage() {
  const { user } = useAuth();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => dashboardApi.thongKe().then((r) => r.data),
  });

  const { data: upcomingData, isLoading: upcomingLoading } = useQuery({
    queryKey: ["upcoming-meetings"],
    queryFn: () => dashboardApi.cuocHopGanDay().then((r) => r.data),
  });

  const readinessData = [
    { value: stats?.ti_le_san_sang ?? 0, fill: "#7c3aed" },
  ];

  const statCards = [
    {
      label: "Tổng cuộc họp",
      value: stats?.tong_cuoc_hop ?? 0,
      icon: CalendarDays,
      color: "text-blue-400",
      bg: "bg-blue-500/10",
    },
    {
      label: "Sẵn sàng",
      value: stats?.san_sang ?? 0,
      icon: CheckCircle2,
      color: "text-green-400",
      bg: "bg-green-500/10",
    },
    {
      label: "Cần dời lịch",
      value: stats?.can_doi_lich ?? 0,
      icon: XCircle,
      color: "text-red-400",
      bg: "bg-red-500/10",
    },
    {
      label: "Chờ đánh giá",
      value: stats?.cho_danh_gia ?? 0,
      icon: Clock,
      color: "text-yellow-400",
      bg: "bg-yellow-500/10",
    },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">
            Chào buổi tối, {user?.email?.split("@")[0] ?? "bạn"} 👋
          </h1>
          <p className="text-slate-400 mt-1">
            Đây là tổng quan cuộc họp của bạn hôm nay.
          </p>
        </div>
        <Link href="/cuoc-hop/tao-moi" className="btn-primary flex items-center gap-2">
          <Plus size={16} />
          <span className="hidden sm:inline">Tạo cuộc họp</span>
        </Link>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statCards.map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className="stat-card animate-slide-up">
            <div className={`w-10 h-10 rounded-xl ${bg} flex items-center justify-center mb-3`}>
              <Icon size={20} className={color} />
            </div>
            <div className="text-3xl font-bold text-slate-100">
              {statsLoading ? (
                <div className="h-8 w-12 bg-white/5 rounded animate-pulse" />
              ) : value}
            </div>
            <div className="text-sm text-slate-400">{label}</div>
          </div>
        ))}
      </div>

      {/* Charts + Upcoming */}
      <div className="grid lg:grid-cols-3 gap-6">
        {/* Readiness gauge */}
        <div className="glass rounded-2xl p-6 flex flex-col items-center justify-center gap-3">
          <div className="flex items-center gap-2 text-slate-300 font-semibold self-start">
            <TrendingUp size={18} className="text-violet-400" />
            Tỉ lệ sẵn sàng
          </div>
          <div className="relative w-full h-44">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                cx="50%" cy="80%"
                innerRadius="70%" outerRadius="100%"
                startAngle={180} endAngle={0}
                data={readinessData}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar background={{ fill: "#1e293b" }} dataKey="value" cornerRadius={8} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-end justify-center pb-2">
              <div className="text-center">
                <div className="text-4xl font-bold gradient-text">
                  {statsLoading ? "—" : `${stats?.ti_le_san_sang ?? 0}%`}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">cuộc họp sẵn sàng</div>
              </div>
            </div>
          </div>
          <div className="text-sm text-slate-500 text-center">
            Hôm nay: <span className="text-violet-400 font-medium">
              {stats?.da_danh_gia_hom_nay ?? 0} cuộc họp
            </span> đã được AI đánh giá
          </div>
        </div>

        {/* Upcoming meetings */}
        <div className="glass rounded-2xl p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-2 text-slate-300 font-semibold">
              <Zap size={18} className="text-violet-400" />
              Cuộc họp sắp tới
            </div>
            <Link href="/cuoc-hop" className="text-xs text-violet-400 hover:text-violet-300 flex items-center gap-1">
              Xem tất cả <ChevronRight size={14} />
            </Link>
          </div>

          {upcomingLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-16 bg-white/[0.03] rounded-xl animate-pulse" />
              ))}
            </div>
          ) : !upcomingData?.length ? (
            <div className="flex flex-col items-center justify-center py-10 text-slate-500">
              <CalendarDays size={36} className="mb-3 opacity-30" />
              <p className="text-sm">Không có cuộc họp nào sắp tới</p>
              <Link href="/cuoc-hop/tao-moi" className="mt-3 text-violet-400 text-sm hover:underline">
                Tạo cuộc họp đầu tiên →
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {upcomingData.map((m: any) => (
                <Link
                  key={m.id}
                  href={`/cuoc-hop/${m.id}`}
                  className="flex items-center gap-4 p-3 rounded-xl hover:bg-white/[0.04] transition-colors group"
                >
                  <div className="w-10 h-10 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center flex-shrink-0">
                    <CalendarDays size={18} className="text-violet-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate group-hover:text-white">
                      {m.title}
                    </p>
                    <p className="text-xs text-slate-500">{formatDate(m.scheduled_at)}</p>
                  </div>
                  <StatusBadge status={m.status} size="sm" />
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
