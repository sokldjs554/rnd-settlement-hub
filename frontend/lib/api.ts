/**
 * API 클라이언트.
 *
 * - access token: 메모리+localStorage 보관, Authorization 헤더로 전송
 * - 401 응답 시 refresh(httpOnly cookie)로 1회 재발급 후 재시도, 실패하면 로그인으로
 * - 에러는 서버 표준 envelope({error:{code,message}})를 ApiError로 변환
 */

import type { ApiErrorBody } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "sh_access_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public detail?: unknown,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token === null) window.localStorage.removeItem(TOKEN_KEY);
  else window.localStorage.setItem(TOKEN_KEY, token);
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = (await res.json()) as ApiErrorBody;
    return new ApiError(res.status, body.error.code, body.error.message, body.error.detail);
  } catch {
    return new ApiError(res.status, "UNKNOWN", `요청 실패 (HTTP ${res.status})`);
  }
}

async function tryRefresh(): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return false;
  const body = (await res.json()) as { access_token: string };
  setToken(body.access_token);
  return true;
}

export async function api<T>(
  path: string,
  options: RequestInit & { retryOn401?: boolean } = {},
): Promise<T> {
  const { retryOn401 = true, ...init } = options;
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${BASE_URL}/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
  });

  if (res.status === 401 && retryOn401 && (await tryRefresh())) {
    return api<T>(path, { ...options, retryOn401: false });
  }
  if (res.status === 401) {
    setToken(null);
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** multipart 업로드 (증빙 파일) */
export function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return api<T>(path, { method: "POST", body: form });
}

/** 인증이 필요한 파일 다운로드 URL 열기 (증빙 뷰어용 blob) */
export async function fetchFileBlob(path: string): Promise<string> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${BASE_URL}/api/v1${path}`, { headers, credentials: "include" });
  if (!res.ok) throw await parseError(res);
  return URL.createObjectURL(await res.blob());
}
