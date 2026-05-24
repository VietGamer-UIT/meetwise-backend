import axios from "axios";
import { supabase } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
});

// Tự động gắn Bearer token từ Supabase vào mọi request
api.interceptors.request.use(async (config) => {
  const { data } = await supabase.auth.getSession();
  if (data.session?.access_token) {
    config.headers.Authorization = `Bearer ${data.session.access_token}`;
  }
  return config;
});

// Interceptor: 401 → redirect về đăng nhập
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      window.location.href = "/dang-nhap";
    }
    return Promise.reject(error);
  }
);

// ─── API Calls ───────────────────────────────────────────

// Auth
export const authApi = {
  dangNhap: (email: string, password: string) =>
    api.post("/v1/auth/dang-nhap", { email, password }),
  dangKy: (email: string, password: string, full_name: string) =>
    api.post("/v1/auth/dang-ky", { email, password, full_name }),
  dangXuat: () => api.post("/v1/auth/dang-xuat"),
  toi: () => api.get("/v1/auth/toi"),
};

// Dashboard
export const dashboardApi = {
  thongKe: () => api.get("/v1/bang-dieu-khien/thong-ke"),
  cuocHopGanDay: () => api.get("/v1/bang-dieu-khien/cuoc-hop-gan-day"),
};

// Cuộc họp
export const cuocHopApi = {
  danhSach: (params?: { trang?: number; kich_thuoc?: number; trang_thai?: string }) =>
    api.get("/v1/cuoc-hop", { params }),
  chiTiet: (id: string) => api.get(`/v1/cuoc-hop/${id}`),
  taoMoi: (data: any) => api.post("/v1/cuoc-hop", data),
  capNhat: (id: string, data: any) => api.patch(`/v1/cuoc-hop/${id}`, data),
  xoa: (id: string) => api.delete(`/v1/cuoc-hop/${id}`),
  danhGia: (id: string, override_facts?: Record<string, boolean>) =>
    api.post(`/v1/cuoc-hop/${id}/danh-gia`, override_facts),
  lichSuDanhGia: (id: string) => api.get(`/v1/cuoc-hop/${id}/lich-su-danh-gia`),
};

// Users
export const usersApi = {
  hoSo: () => api.get("/v1/users/ho-so"),
  capNhatHoSo: (data: any) => api.patch("/v1/users/ho-so", data),
};

// Thông báo
export const thongBaoApi = {
  danhSach: (chi_chua_doc?: boolean) =>
    api.get("/v1/thong-bao", { params: { chi_chua_doc } }),
  danhDauDaDoc: (id: string) => api.patch(`/v1/thong-bao/${id}/doc`),
  docTatCa: () => api.patch("/v1/thong-bao/doc-tat-ca"),
  xoa: (id: string) => api.delete(`/v1/thong-bao/${id}`),
};
