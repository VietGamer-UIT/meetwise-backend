"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { usersApi } from "@/lib/api";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useEffect } from "react";
import { toast } from "sonner";
import { User, Building2, Briefcase, Globe, Save } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const schema = z.object({
  full_name: z.string().min(1, "Tên không được để trống").max(100),
  organization: z.string().max(200).optional(),
  job_title: z.string().max(100).optional(),
  timezone: z.string().max(50).optional(),
});
type FormData = z.infer<typeof schema>;

export default function CaiDatPage() {
  const { user } = useAuth();
  const qc = useQueryClient();

  const { data: profile, isLoading } = useQuery({
    queryKey: ["ho-so"],
    queryFn: () => usersApi.hoSo().then((r) => r.data),
  });

  const { register, handleSubmit, reset, formState: { errors, isDirty, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  useEffect(() => {
    if (profile) {
      reset({
        full_name: profile.full_name ?? "",
        organization: profile.organization ?? "",
        job_title: profile.job_title ?? "",
        timezone: profile.timezone ?? "Asia/Ho_Chi_Minh",
      });
    }
  }, [profile, reset]);

  const mutation = useMutation({
    mutationFn: usersApi.capNhatHoSo,
    onSuccess: () => {
      toast.success("Đã lưu hồ sơ");
      qc.invalidateQueries({ queryKey: ["ho-so"] });
    },
    onError: () => toast.error("Lưu thất bại"),
  });

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-100">Cài đặt</h1>
        <p className="text-slate-400 text-sm mt-0.5">Cập nhật thông tin cá nhân</p>
      </div>

      {/* Avatar + email */}
      <div className="glass rounded-2xl p-6 flex items-center gap-4">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-2xl font-bold text-white flex-shrink-0">
          {user?.email?.[0]?.toUpperCase() ?? "U"}
        </div>
        <div>
          <p className="text-slate-100 font-semibold">{profile?.full_name ?? user?.email?.split("@")[0]}</p>
          <p className="text-sm text-slate-400">{user?.email}</p>
          <p className="text-xs text-violet-400 mt-1">MeetWise Member</p>
        </div>
      </div>

      {/* Form */}
      {isLoading ? (
        <div className="glass rounded-2xl p-6 space-y-4 animate-pulse">
          {[...Array(4)].map((_, i) => <div key={i} className="h-12 bg-white/5 rounded-xl" />)}
        </div>
      ) : (
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="glass rounded-2xl p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <User size={14} /> Họ và tên
            </label>
            <input {...register("full_name")} className="input" placeholder="Đoàn Hoàng Việt" />
            {errors.full_name && <p className="text-red-400 text-xs mt-1">{errors.full_name.message}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Building2 size={14} /> Tổ chức / Công ty
            </label>
            <input {...register("organization")} className="input" placeholder="Công ty ABC" />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Briefcase size={14} /> Chức danh
            </label>
            <input {...register("job_title")} className="input" placeholder="Trưởng nhóm phát triển" />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Globe size={14} /> Múi giờ
            </label>
            <select {...register("timezone")} className="input appearance-none cursor-pointer">
              <option value="Asia/Ho_Chi_Minh" style={{ background: "#0f172a" }}>Việt Nam (GMT+7)</option>
              <option value="Asia/Singapore" style={{ background: "#0f172a" }}>Singapore (GMT+8)</option>
              <option value="Asia/Bangkok" style={{ background: "#0f172a" }}>Bangkok (GMT+7)</option>
              <option value="UTC" style={{ background: "#0f172a" }}>UTC</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={!isDirty || isSubmitting || mutation.isPending}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            <Save size={16} />
            {mutation.isPending ? "Đang lưu..." : "Lưu thay đổi"}
          </button>
        </form>
      )}
    </div>
  );
}
