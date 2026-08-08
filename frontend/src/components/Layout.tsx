import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  MessageSquare,
  BarChart3,
  ListChecks,
  FileText,
  GraduationCap,
} from "lucide-react";

const navItems = [
  { to: "/", label: "대시보드", icon: LayoutDashboard, end: true },
  { to: "/chat", label: "AI 상담", icon: MessageSquare },
  { to: "/analytics", label: "데이터 분석", icon: BarChart3 },
  { to: "/workflow", label: "업무 자동화", icon: ListChecks },
  { to: "/documents", label: "서류 검토", icon: FileText },
];

export default function Layout() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50">
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-5">
          <GraduationCap className="h-7 w-7 text-indigo-600" />
          <div>
            <p className="text-sm font-semibold leading-tight text-slate-900">
              입시행정 통합
            </p>
            <p className="text-xs leading-tight text-slate-500">지원 시스템</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {navItems.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              <Icon className="h-4.5 w-4.5" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 px-4 py-3 text-xs text-slate-400">
          admission-ai-platform v0.1
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
