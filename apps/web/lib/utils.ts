import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow } from "date-fns";
import { vi } from "date-fns/locale";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date) {
  return format(new Date(date), "dd/MM/yyyy HH:mm", { locale: vi });
}

export function formatRelative(date: string | Date) {
  return formatDistanceToNow(new Date(date), { addSuffix: true, locale: vi });
}

export function getMeetingStatusLabel(status: string) {
  const map: Record<string, string> = {
    pending: "Chờ đánh giá",
    evaluating: "Đang đánh giá",
    ready: "Sẵn sàng",
    rescheduled: "Cần dời lịch",
    cancelled: "Đã hủy",
  };
  return map[status] ?? status;
}

export function getMeetingStatusColor(status: string) {
  const map: Record<string, string> = {
    pending: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
    evaluating: "text-blue-400 bg-blue-400/10 border-blue-400/20",
    ready: "text-green-400 bg-green-400/10 border-green-400/20",
    rescheduled: "text-red-400 bg-red-400/10 border-red-400/20",
    cancelled: "text-slate-400 bg-slate-400/10 border-slate-400/20",
  };
  return map[status] ?? "text-slate-400 bg-slate-400/10";
}
