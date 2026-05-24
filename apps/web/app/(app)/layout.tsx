import type { Metadata } from "next";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = { title: "Ứng dụng" };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 md:ml-60 min-h-screen">
        <div className="p-4 md:p-8 max-w-6xl mx-auto animate-fade-in">
          {children}
        </div>
      </main>
    </div>
  );
}
