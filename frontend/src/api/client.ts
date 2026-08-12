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
