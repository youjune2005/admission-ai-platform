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

const navItems = [
  { to: "/", label: "홈", icon: Home, end: true },
  { to: "/inquiry", label: "입시 문의 답변", icon: MessageSquareText },
  { to: "/documents/create", label: "행정문서 작성", icon: FilePenLine },
  { to: "/archive", label: "문서 보관함", icon: FolderOpen },
  { to: "/regulations", label: "규정·자료 관리", icon: BookOpen },
];

export default function Layout() {
  const navigate = useNavigate();

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
