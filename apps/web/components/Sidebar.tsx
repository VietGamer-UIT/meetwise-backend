"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, CalendarDays, History,
  Bell, Settings, LogOut, Zap, Menu, X,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { href: "/dashboard", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/cuoc-hop", label: "Cuộc họp", icon: CalendarDays },
  { href: "/lich-su", label: "Lịch sử", icon: History },
  { href: "/thong-bao", label: "Thông báo", icon: Bell },
  { href: "/cai-dat", label: "Cài đặt", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  const NavContent = () => (
    <>
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-3 py-1 mb-6">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-violet-700 flex items-center justify-center shadow-lg shadow-violet-500/30">
          <Zap size={16} className="text-white" />
        </div>
        <span className="text-lg font-bold gradient-text">MeetWise</span>
      </div>

      {/* Nav links */}
      <nav className="flex-1 space-y-1">
        {navItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={() => setMobileOpen(false)}
              className={cn("nav-link", active && "nav-link-active")}
            >
              <Icon size={18} />
              {label}
              {href === "/thong-bao" && (
                <span className="ml-auto w-2 h-2 rounded-full bg-violet-500 animate-pulse" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="mt-auto pt-4 border-t border-white/[0.08]">
        <div className="flex items-center gap-3 px-3 py-2 mb-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-sm font-bold text-white">
            {user?.email?.[0]?.toUpperCase() ?? "U"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-200 truncate">
              {user?.email?.split("@")[0] ?? "Người dùng"}
            </p>
            <p className="text-xs text-slate-500 truncate">{user?.email}</p>
          </div>
        </div>
        <button
          onClick={signOut}
          className="nav-link w-full text-red-400 hover:text-red-300 hover:bg-red-500/10"
        >
          <LogOut size={18} />
          Đăng xuất
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-60 min-h-screen glass border-r border-white/[0.06] p-4 fixed left-0 top-0 bottom-0 z-30">
        <NavContent />
      </aside>

      {/* Mobile toggle */}
      <div className="md:hidden fixed top-4 left-4 z-50">
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="glass p-2.5 rounded-xl text-slate-300"
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 bg-black/60 z-40"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile drawer */}
      <aside
        className={cn(
          "md:hidden fixed left-0 top-0 bottom-0 w-72 z-50 glass border-r border-white/[0.06] p-4 flex flex-col transition-transform duration-300",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <NavContent />
      </aside>
    </>
  );
}
