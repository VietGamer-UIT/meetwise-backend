"use client";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cuocHopApi } from "@/lib/api";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { CalendarDays, FileText, MapPin, Clock, Link as LinkIcon, ArrowLeft, Sparkles } from "lucide-react";
import Link from "next/link";

const schema = z.object({
  title: z.string().min(1, "Tiêu đề không được để trống").max(200),
  description: z.string().max(2000).optional(),
  scheduled_at: z.string().min(1, "Vui lòng chọn ngày giờ"),
  duration_minutes: z.coerce.number().min(5).max(480),
  location: z.string().max(500).optional(),
  meeting_url: z.string().url("URL không hợp lệ").optional().or(z.literal("")),
  rule: z.string().min(1, "Điều kiện họp không được để trống").max(2000),
});

type FormData = z.infer<typeof schema>;

const ruleExamples = [
  { label: "Logic đơn giản", value: "Slide_Done AND Manager_Free" },
  { label: "Hoặc điều kiện", value: "(Slide_Done OR Sheet_Done) AND Manager_Free" },
  { label: "Tiếng Việt", value: "Slide cập nhật hoặc Sheet chốt số, bắt buộc Manager rảnh" },
];

export default function TaoMoiCuocHopPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const {
    register, handleSubmit, setValue, watch,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { duration_minutes: 60 },
  });

  const mutation = useMutation({
    mutationFn: cuocHopApi.taoMoi,
    onSuccess: (res) => {
      toast.success("Đã tạo cuộc họp thành công!");
      qc.invalidateQueries({ queryKey: ["cuoc-hop"] });
      router.push(`/cuoc-hop/${res.data.id}`);
    },
    onError: (e: any) => toast.error(e.response?.data?.detail ?? "Tạo thất bại"),
  });

  const onSubmit = (data: FormData) => {
    const payload = {
      ...data,
      scheduled_at: new Date(data.scheduled_at).toISOString(),
      meeting_url: data.meeting_url || undefined,
    };
    mutation.mutate(payload);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <Link href="/cuoc-hop" className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-200 mb-4 w-fit">
          <ArrowLeft size={16} /> Quay lại
        </Link>
        <h1 className="text-2xl font-bold text-slate-100">Tạo cuộc họp mới</h1>
        <p className="text-slate-400 text-sm mt-1">
          AI sẽ đánh giá điều kiện khi bạn nhấn "Đánh giá".
        </p>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
        {/* Tiêu đề */}
        <div className="glass rounded-2xl p-5 space-y-5">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide flex items-center gap-2">
            <FileText size={15} /> Thông tin cơ bản
          </h2>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">
              Tiêu đề <span className="text-red-400">*</span>
            </label>
            <input {...register("title")} className="input" placeholder="VD: Kickoff Q1 2026" />
            {errors.title && <p className="text-red-400 text-xs mt-1">{errors.title.message}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Mô tả</label>
            <textarea
              {...register("description")}
              className="input resize-none h-24"
              placeholder="Mục tiêu, chương trình họp..."
            />
          </div>
        </div>

        {/* Thời gian & địa điểm */}
        <div className="glass rounded-2xl p-5 space-y-5">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide flex items-center gap-2">
            <CalendarDays size={15} /> Thời gian & Địa điểm
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Ngày giờ <span className="text-red-400">*</span>
              </label>
              <input
                type="datetime-local"
                {...register("scheduled_at")}
                className="input"
                style={{ colorScheme: "dark" }}
              />
              {errors.scheduled_at && (
                <p className="text-red-400 text-xs mt-1">{errors.scheduled_at.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Clock size={14} /> Thời lượng (phút)
              </label>
              <input
                type="number"
                {...register("duration_minutes")}
                className="input"
                placeholder="60"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <MapPin size={14} /> Địa điểm
            </label>
            <input {...register("location")} className="input" placeholder="Phòng họp 3A hoặc Online" />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <LinkIcon size={14} /> Link họp
            </label>
            <input {...register("meeting_url")} className="input" placeholder="https://meet.google.com/..." />
            {errors.meeting_url && (
              <p className="text-red-400 text-xs mt-1">{errors.meeting_url.message}</p>
            )}
          </div>
        </div>

        {/* Điều kiện AI */}
        <div className="glass rounded-2xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-wide flex items-center gap-2">
            <Sparkles size={15} className="text-violet-400" /> Điều kiện AI đánh giá
            <span className="text-red-400">*</span>
          </h2>

          <div>
            <textarea
              {...register("rule")}
              className="input resize-none h-28 font-mono text-sm"
              placeholder="VD: (Slide_Done OR Sheet_Done) AND Manager_Free"
            />
            {errors.rule && <p className="text-red-400 text-xs mt-1">{errors.rule.message}</p>}
          </div>

          <div>
            <p className="text-xs text-slate-500 mb-2">Ví dụ nhanh:</p>
            <div className="flex flex-wrap gap-2">
              {ruleExamples.map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  onClick={() => setValue("rule", ex.value)}
                  className="text-xs px-3 py-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20 text-violet-400 hover:bg-violet-500/20 transition-colors"
                >
                  {ex.label}
                </button>
              ))}
            </div>
          </div>

          <div className="bg-violet-500/5 border border-violet-500/20 rounded-xl p-3 text-xs text-slate-400 space-y-1">
            <p className="font-medium text-violet-300">💡 Cú pháp điều kiện:</p>
            <p>• Dùng <code className="text-violet-300">AND</code> / <code className="text-violet-300">OR</code> / ngoặc để kết hợp</p>
            <p>• Tên điều kiện không dấu, không khoảng trắng (VD: <code className="text-violet-300">Slide_Done</code>)</p>
            <p>• AI hỗ trợ cả tiếng Việt tự nhiên</p>
          </div>
        </div>

        {/* Submit */}
        <div className="flex gap-3">
          <Link href="/cuoc-hop" className="btn-secondary flex-1 text-center">
            Hủy
          </Link>
          <button
            type="submit"
            disabled={isSubmitting || mutation.isPending}
            className="btn-primary flex-1"
          >
            {mutation.isPending ? "Đang tạo..." : "Tạo cuộc họp"}
          </button>
        </div>
      </form>
    </div>
  );
}
