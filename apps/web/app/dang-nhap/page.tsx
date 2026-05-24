"use client";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { authApi } from "@/lib/api";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { Zap, Mail, Lock, Eye, EyeOff } from "lucide-react";
import Link from "next/link";

const schema = z.object({
  email: z.string().email("Email không hợp lệ"),
  password: z.string().min(6, "Mật khẩu tối thiểu 6 ký tự"),
});
type FormData = z.infer<typeof schema>;

export default function DangNhapPage() {
  const router = useRouter();
  const [showPass, setShowPass] = useState(false);

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    try {
      const res = await authApi.dangNhap(data.email, data.password);
      // Lưu token vào localStorage
      localStorage.setItem("meetwise_token", res.data.access_token);
      toast.success("Đăng nhập thành công!");
      router.push("/dashboard");
    } catch (e: any) {
      toast.error(e.response?.data?.detail ?? "Email hoặc mật khẩu không đúng");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      {/* Gradient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-96 h-96 bg-violet-600/20 rounded-full blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 bg-blue-600/15 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-md relative animate-slide-up">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-xl shadow-violet-500/30">
            <Zap size={20} className="text-white" />
          </div>
          <span className="text-2xl font-bold gradient-text">MeetWise</span>
        </div>

        <div className="glass rounded-2xl p-8">
          <h1 className="text-xl font-bold text-slate-100 mb-1">Chào mừng trở lại</h1>
          <p className="text-slate-400 text-sm mb-6">Đăng nhập để quản lý cuộc họp thông minh</p>

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5 flex items-center gap-1.5">
                <Mail size={14} /> Email
              </label>
              <input
                {...register("email")}
                type="email"
                className="input"
                placeholder="ban@congty.vn"
                autoComplete="email"
              />
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
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="btn-primary w-full mt-2"
            >
              {isSubmitting ? "Đang đăng nhập..." : "Đăng nhập"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-500">
            Chưa có tài khoản?{" "}
            <Link href="/dang-ky" className="text-violet-400 hover:text-violet-300 font-medium">
              Đăng ký miễn phí
            </Link>
          </div>
        </div>

        <p className="text-center text-xs text-slate-600 mt-6">
          Built by <span className="text-violet-500">Đoàn Hoàng Việt (Việt Gamer)</span>
        </p>
      </div>
    </div>
  );
}
