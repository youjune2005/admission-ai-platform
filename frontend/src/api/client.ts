import axios from "axios";

/**
 * API 베이스 URL
 * - 기본(로컬): http://localhost:8000
 * - 공유/터널: VITE_API_BASE_URL= 빈 값 → 같은 출처(/api)로 요청 (Vite 프록시)
 *   → 브라우저에는 OpenAI 키가 절대 내려가지 않음
 */
const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
export const API_BASE_URL =
  raw === undefined ? "http://localhost:8000" : raw;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

function detailMessage(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean)
      .join(" ");
  }
  return null;
}

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const status = error?.response?.status as number | undefined;
    const detail = detailMessage(error?.response?.data);
    if (detail) {
      error.message = detail;
    } else if (status === 429) {
      error.message = "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.";
    } else if (status && status >= 500) {
      error.message = "서버에서 문서 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
    } else if (!error.response) {
      error.message = "서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.";
    }
    return Promise.reject(error);
  }
);
