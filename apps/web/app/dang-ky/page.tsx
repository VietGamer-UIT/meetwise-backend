"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { Zap, Mail, Lock, User, Eye, EyeOff } from "lucide-react";
import Link from "next/link";

const schema = z.object({
  full_name: z.string().min(1, "Vui lòng nhập họ tên"),
  email: z.string().email("Email không hợp lệ"),
  password: z.string().min(6, "Mật khẩu tối thiểu 6 ký tự"),
});
type FormData = z.infer<typeof schema>;

export default function DangKyPage() {
  const router = useRouter();
  const [showPass, setShowPass] = useState(false);

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    try {
      await authApi.dangKy(data.email, data.password, data.full_name);
      toast.success("Đăng ký thành công! Vui lòng kiểm tra email để xác nhận.");
      router.push("/dang-nhap");
    } catch (e: any) {
      toast.error(e.response?.data?.detail ?? "Đăng ký thất bại");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-violet-600/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-blue-600/15 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-md relative animate-slide-up">
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-xl shadow-violet-500/30">
            <Zap size={20} className="text-white" />
          </div>
          <span className="text-2xl font-bold gradient-text">MeetWise</span>
        </div>

        <div className="glass rounded-2xl p-8">
          <h1 className="text-xl font-bold text-slate-100 mb-1">Tạo tài khoản</h1>
          <p className="text-slate-400 text-sm mb-6">Miễn phí — không cần thẻ tín dụng</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
                <User size={14} /> Họ và tên
              </label>
              <input {...register("full_name")} className="input" placeholder="Đoàn Hoàng Việt" />
              {errors.full_name && <p className="text-red-400 text-xs mt-1">{errors.full_name.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Mail size={14} /> Email
              </label>
              <input {...register("email")} type="email" className="input" placeholder="ban@congty.vn" />
              {errors.email && <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Lock size={14} /> Mật khẩu
              </label>
              <div className="relative">
                <input
                  {...register("password")}
                  type={showPass ? "text" : "password"}
                  className="input pr-11"
                  placeholder="Tối thiểu 6 ký tự"
                />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
            </div>

            <button type="submit" disabled={isSubmitting} className="btn-primary w-full mt-2">
              {isSubmitting ? "Đang tạo tài khoản..." : "Tạo tài khoản miễn phí"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-500">
            Đã có tài khoản?{" "}
            <Link href="/dang-nhap" className="text-violet-400 hover:text-violet-300 font-medium">
              Đăng nhập
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
