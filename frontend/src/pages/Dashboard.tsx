import { useEffect, useState } from "react";
import { MessageSquare, BarChart3, ListChecks, FileText, Sparkles } from "lucide-react";
import { apiClient } from "../api/client";
import type { WorkflowTask, UploadedDocument, ChatSession } from "../types";

interface HealthInfo {
  status: string;
  app: string;
  llm_provider: string;
}

export default function Dashboard() {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [docs, setDocs] = useState<UploadedDocument[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    apiClient.get("/api/health").then((res) => setHealth(res.data)).catch(() => {});
    apiClient.get("/api/workflow/tasks").then((res) => setTasks(res.data)).catch(() => {});
    apiClient.get("/api/documents").then((res) => setDocs(res.data)).catch(() => {});
    apiClient.get("/api/chat/sessions").then((res) => setSessions(res.data)).catch(() => {});
  }, []);

  const openTasks = tasks.filter((t) => t.status !== "done").length;

  const cards = [
    { label: "진행 중인 업무", value: openTasks, icon: ListChecks, color: "text-amber-600 bg-amber-50" },
    { label: "AI 상담 세션", value: sessions.length, icon: MessageSquare, color: "text-indigo-600 bg-indigo-50" },
    { label: "검토된 서류", value: docs.length, icon: FileText, color: "text-emerald-600 bg-emerald-50" },
    { label: "분석 도구", value: "CSV/Excel", icon: BarChart3, color: "text-sky-600 bg-sky-50" },
  ];

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">대시보드</h1>
          <p className="mt-1 text-sm text-slate-500">
            생성형 AI 기반 입시행정 통합 지원 시스템에 오신 것을 환영합니다.
          </p>
        </div>
        {health && (
          <div className="flex items-center gap-2 rounded-full bg-white px-4 py-2 text-xs font-medium text-slate-600 shadow-sm ring-1 ring-slate-200">
            <Sparkles className="h-3.5 w-3.5 text-indigo-500" />
            LLM Provider: <span className="font-semibold text-slate-900">{health.llm_provider}</span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <div className={`mb-3 inline-flex rounded-lg p-2 ${color}`}>
              <Icon className="h-5 w-5" />
            </div>
            <p className="text-2xl font-semibold text-slate-900">{value}</p>
            <p className="mt-1 text-sm text-slate-500">{label}</p>
          </div>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-4 text-base font-semibold text-slate-900">최근 업무</h2>
          {tasks.length === 0 ? (
            <p className="text-sm text-slate-400">등록된 업무가 없습니다. 업무 자동화 메뉴에서 추가해보세요.</p>
          ) : (
            <ul className="space-y-2">
              {tasks.slice(0, 5).map((t) => (
                <li key={t.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm">
                  <span className="text-slate-700">{t.title}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{t.status}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-4 text-base font-semibold text-slate-900">최근 검토 서류</h2>
          {docs.length === 0 ? (
            <p className="text-sm text-slate-400">업로드된 서류가 없습니다. 서류 검토 메뉴에서 업로드해보세요.</p>
          ) : (
            <ul className="space-y-2">
              {docs.slice(0, 5).map((d) => (
                <li key={d.id} className="rounded-lg border border-slate-100 px-3 py-2 text-sm text-slate-700">
                  {d.filename}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
