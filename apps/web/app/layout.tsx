import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { QueryProvider } from "@/contexts/QueryProvider";
import { Toaster } from "sonner";

const inter = Inter({ subsets: ["latin", "vietnamese"] });

export const metadata: Metadata = {
  title: {
    template: "%s | MeetWise",
    default: "MeetWise — AI Meeting Readiness Platform",
  },
  description:
    "Nền tảng AI giúp doanh nghiệp đánh giá mức độ sẵn sàng cuộc họp, tránh các cuộc họp vô bổ và tốn thời gian.",
  authors: [{ name: "Đoàn Hoàng Việt (Việt Gamer)" }],
  keywords: ["meeting", "AI", "productivity", "SaaS", "cuộc họp"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className="dark">
      <body className={inter.className}>
        <QueryProvider>
          <AuthProvider>
            {children}
            <Toaster
              position="top-right"
              richColors
              toastOptions={{
                style: {
                  background: "#1e293b",
                  border: "1px solid #334155",
                  color: "#f8fafc",
                },
              }}
            />
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
