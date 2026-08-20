"use client";

/**
 * 앱 전역 프로바이더: TanStack Query + 현재 사용자 컨텍스트.
 * 사용자 정보는 /auth/me로 확인하며, 미인증이면 로그인 페이지로 보낸다.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken } from "./api";
import type { User } from "./types";

const queryClientOptions = {
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10_000, // 업무 시스템: 목록은 10초 내 재사용, 변경 시 invalidate로 갱신
      refetchOnWindowFocus: false,
    },
  },
};

const UserContext = createContext<User | null>(null);

export function useCurrentUser(): User | null {
  return useContext(UserContext);
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const isLoginPage = pathname.startsWith("/login");

  const { data: user, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<User>("/auth/me"),
    enabled: !isLoginPage,
    retry: false,
  });

  useEffect(() => {
    if (!isLoginPage && !isLoading && (isError || (!getToken() && !user))) {
      router.replace("/login");
    }
  }, [isLoginPage, isLoading, isError, user, router]);

  if (isLoginPage) return <>{children}</>;
  if (isLoading || !user) {
    return (
      <div className="flex h-screen items-center justify-center text-slate-500">
        불러오는 중…
      </div>
    );
  }
  return <UserContext.Provider value={user}>{children}</UserContext.Provider>;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient(queryClientOptions));
  return (
    <QueryClientProvider client={queryClient}>
      <AuthGate>{children}</AuthGate>
    </QueryClientProvider>
  );
}
