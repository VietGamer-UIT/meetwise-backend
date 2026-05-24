"use client";
import { cn, getMeetingStatusColor, getMeetingStatusLabel } from "@/lib/utils";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

const statusDot: Record<string, string> = {
  pending: "bg-yellow-400",
  evaluating: "bg-blue-400 evaluating-pulse",
  ready: "bg-green-400",
  rescheduled: "bg-red-400",
  cancelled: "bg-slate-400",
};

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "badge",
        getMeetingStatusColor(status),
        size === "sm" && "text-[11px] px-2 py-px"
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", statusDot[status] ?? "bg-slate-400")} />
      {getMeetingStatusLabel(status)}
    </span>
  );
}
