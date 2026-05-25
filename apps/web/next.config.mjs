/** @type {import('next').NextConfig} */
const nextConfig = {
  // Tắt strict mode để tránh double-render trong dev
  reactStrictMode: false,

  // Cho phép ảnh từ Supabase Storage
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "*.supabase.co" },
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
    ],
  },

  // Biến môi trường public (expose ra client)
  env: {
    NEXT_PUBLIC_APP_NAME: "MeetWise",
    NEXT_PUBLIC_APP_VERSION: "2.0.0",
  },
};

export default nextConfig;
