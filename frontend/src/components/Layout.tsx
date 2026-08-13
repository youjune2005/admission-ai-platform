import { NavLink, useNavigate } from "react-router-dom";
import {
  Home,
  MessageSquareText,
  FilePenLine,
  FolderOpen,
  BookOpen,
  Settings,
  ChevronDown,
  UserRound,
} from "lucide-react";
import NotificationBell from "./NotificationBell";
import PageTransition from "./PageTransition";
import { useIsPhone } from "../hooks/useIsPhone";

const navItems = [
  { to: "/", label: "홈", short: "홈", icon: Home, end: true },
  { to: "/inquiry", label: "입시 문의 답변", short: "문의", icon: MessageSquareText },
  { to: "/documents/create", label: "행정문서 작성", short: "문서", icon: FilePenLine },
  { to: "/archive", label: "문서 보관함", short: "보관함", icon: FolderOpen },
  { to: "/regulations", label: "규정·자료 관리", short: "규정", icon: BookOpen },
];

export default function Layout() {
  const navigate = useNavigate();
  const isPhone = useIsPhone();

  if (isPhone) {
    return (
      <div className="flex h-[100dvh] w-screen flex-col overflow-hidden bg-[var(--ssu-bg)]">
        <header
          className="flex min-h-12 shrink-0 items-center justify-between bg-[var(--ssu-navy)] px-3 text-white"
          style={{ paddingTop: "env(safe-area-inset-top)" }}
        >
          <p className="truncate text-[15px] font-bold tracking-tight">SSU 입시행정 AI</p>
          <div className="flex items-center gap-0.5">
            <NotificationBell tone="onDark" />
            <button
              type="button"
              onClick={() => navigate("/settings")}
              className="ui-pressable rounded-full p-2 text-white/80 hover:bg-white/10 hover:text-white"
              aria-label="설정"
            >
              <Settings className="h-5 w-5" strokeWidth={1.8} />
            </button>
            <span className="ml-0.5 flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-xs font-semibold">
              입
            </span>
          </div>
        </header>

        <div className="flex h-10 shrink-0 items-center justify-between border-b border-[var(--ssu-border)] bg-white px-3">
          <button
            type="button"
            className="ui-pressable inline-flex max-w-[70%] items-center gap-1 rounded-md px-1.5 py-1 text-[12px] font-medium text-slate-700"
          >
            <span className="truncate">2027학년도 · 수시모집 기준</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
          </button>
          <span className="text-[11px] font-medium text-slate-500">입학팀 담당자</span>
        </div>

        <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
          <PageTransition />
        </main>

        <nav
          className="grid shrink-0 grid-cols-5 border-t border-white/10 bg-[var(--ssu-navy)]"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
          aria-label="주요 메뉴"
        >
          {navItems.map(({ to, short, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `ui-nav-item flex flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-semibold ${
                  isActive ? "text-white" : "text-white/55"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`inline-flex h-8 w-8 items-center justify-center rounded-lg ${
                      isActive ? "bg-[var(--ssu-blue)]" : ""
                    }`}
                  >
                    <Icon className="h-4 w-4" strokeWidth={1.8} />
                  </span>
                  {short}
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--ssu-bg)]">
      <aside className="flex w-[232px] shrink-0 flex-col bg-[var(--ssu-navy)] text-white">
        <div className="px-5 py-5 text-[17px] font-bold tracking-tight">
          SSU 입시행정 AI
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `ui-nav-item flex items-center gap-3 rounded-lg px-3 py-2.5 text-[14px] font-medium ${
                  isActive
                    ? "bg-[var(--ssu-blue)] text-white shadow-sm"
                    : "text-white/75 hover:bg-white/10 hover:text-white"
                }`
              }
            >
              <Icon className="h-4 w-4" strokeWidth={1.8} />
              {label}
            </NavLink>
          ))}
        </nav>

        <button
          type="button"
          onClick={() => navigate("/settings")}
          className="ui-nav-item m-3 flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[14px] font-medium text-white/70 hover:bg-white/10 hover:text-white"
        >
          <Settings className="h-4 w-4" strokeWidth={1.8} />
          설정
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-[var(--ssu-border)] bg-white px-6">
          <button
            type="button"
            className="ui-pressable inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[13px] font-medium text-slate-700 hover:bg-slate-50"
          >
            2027학년도 · 수시모집 기준
            <ChevronDown className="h-4 w-4 text-slate-400" />
          </button>

          <div className="flex items-center gap-3">
            <NotificationBell />

            <button
              type="button"
              className="ui-pressable inline-flex items-center gap-2 rounded-full py-1 pl-1 pr-2 hover:bg-slate-50"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--ssu-navy)] text-xs font-semibold text-white">
                입
              </span>
              <span className="text-left text-[13px] leading-tight">
                <span className="block font-semibold text-slate-800">입학팀 담당자</span>
                <span className="block text-[11px] text-slate-500">입학팀</span>
              </span>
              <ChevronDown className="h-4 w-4 text-slate-400" />
              <UserRound className="sr-only" />
            </button>
          </div>
        </header>

        <main className="min-h-0 min-w-0 flex-1 overflow-x-hidden overflow-y-auto [&>div]:h-full">
          <PageTransition />
        </main>
      </div>
    </div>
  );
}
