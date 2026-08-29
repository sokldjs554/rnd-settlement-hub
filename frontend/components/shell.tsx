"use client";

/** 앱 셸: 좌측 내비게이션 + 상단 헤더(알림). 로그인 페이지에서는 렌더링하지 않는다. */

import { api, setToken } from "@/lib/api";
import { useCurrentUser } from "@/lib/providers";
import type { Notification } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CreditCard, FileBarChart2, FolderKanban, LayoutDashboard, LogOut, ReceiptText } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { cn } from "./ui";

const NAV = [
  { href: "/", label: "대시보드", icon: LayoutDashboard, minRole: "MANAGER" },
  { href: "/expenses", label: "집행 건", icon: ReceiptText, minRole: "RESEARCHER" },
  { href: "/projects", label: "과제·예산", icon: FolderKanban, minRole: "RESEARCHER" },
  { href: "/reports", label: "정산보고서", icon: FileBarChart2, minRole: "MANAGER" },
  { href: "/reconciliation", label: "카드 대사", icon: CreditCard, minRole: "MANAGER" },
] as const;

const ROLE_LEVEL = { RESEARCHER: 1, MANAGER: 2, ADMIN: 3 } as const;

function NotificationBell() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { data: notifications = [] } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<Notification[]>("/notifications?unread=true"),
    refetchInterval: 30_000, // 인앱 알림: 30초 폴링 (내부 도구 규모에서 충분)
  });
  const markRead = useMutation({
    mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "PATCH" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications"] }),
  });

  // 알림이 가리키는 화면 — payload에 링크 대상 id가 들어 있다
  function targetPath(n: Notification): string | null {
    if (typeof n.payload.expense_id === "number") return `/expenses/${n.payload.expense_id}`;
    if (typeof n.payload.report_id === "number") return `/reports/${n.payload.report_id}`;
    return null;
  }

  const MESSAGES: Record<string, string> = {
    expense_needs_review: "새 검토 대기 건이 있습니다",
    expense_approved: "집행 건이 승인되었습니다",
    expense_rejected: "집행 건이 반려되었습니다",
    automation_failed: "자동 검증이 실패해 수기 검토가 필요합니다",
    report_generated: "정산보고서 초안이 준비되었습니다",
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-md p-2 text-slate-600 hover:bg-slate-100"
        aria-label="알림"
      >
        <Bell size={18} />
        {notifications.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {notifications.length}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-80 rounded-lg border border-slate-200 bg-white p-2 shadow-lg">
          {notifications.length === 0 && (
            <p className="px-2 py-3 text-sm text-slate-500">새 알림이 없습니다.</p>
          )}
          {notifications.map((n) => (
            <button
              key={n.id}
              className="block w-full rounded-md px-2 py-2 text-left text-sm hover:bg-slate-50"
              onClick={() => {
                markRead.mutate(n.id);
                const path = targetPath(n);
                if (path) {
                  setOpen(false);
                  router.push(path);
                }
              }}
            >
              <p className="text-slate-800">{MESSAGES[n.type] ?? n.type}</p>
              <p className="text-xs text-slate-400">{formatDateTime(n.created_at)}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const user = useCurrentUser();
  const pathname = usePathname();
  const router = useRouter();

  if (pathname.startsWith("/login")) return <>{children}</>;
  if (!user) return null;

  const logout = async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setToken(null);
    router.replace("/login");
  };

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="px-4 py-5">
          <p className="text-sm font-bold">RnD Settlement Hub</p>
          <p className="text-xs text-slate-500">R&D 정산 관제 시스템</p>
        </div>
        <nav className="flex-1 space-y-1 px-2">
          {NAV.filter((item) => ROLE_LEVEL[user.role] >= ROLE_LEVEL[item.minRole]).map(
            ({ href, label, icon: Icon }) => {
              const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
              return (
                <Link
                  key={href}
                  href={href}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                    active
                      ? "bg-slate-900 font-medium text-white"
                      : "text-slate-600 hover:bg-slate-100",
                  )}
                >
                  <Icon size={16} />
                  {label}
                </Link>
              );
            },
          )}
        </nav>
        <div className="border-t border-slate-200 p-3 text-sm">
          <p className="font-medium text-slate-800">{user.name}</p>
          <p className="mb-2 text-xs text-slate-500">{user.email}</p>
          <button
            onClick={logout}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800"
          >
            <LogOut size={12} /> 로그아웃
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-end border-b border-slate-200 bg-white px-4 py-2">
          <NotificationBell />
        </header>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
