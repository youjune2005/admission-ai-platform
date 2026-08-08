import { useEffect, useState } from "react";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import { apiClient } from "../api/client";
import Markdown from "../components/Markdown";
import type { WorkflowTask } from "../types";

const STATUS_LABEL: Record<string, string> = {
  todo: "할 일",
  in_progress: "진행 중",
  done: "완료",
};

export default function Workflow() {
  const [tasks, setTasks] = useState<WorkflowTask[]>([]);
  const [newTitle, setNewTitle] = useState("");

  const [topic, setTopic] = useState("");
  const [audience, setAudience] = useState("지원자");
  const [keyPointsText, setKeyPointsText] = useState("");
  const [draft, setDraft] = useState("");
  const [draftLoading, setDraftLoading] = useState(false);

  const loadTasks = async () => {
    const res = await apiClient.get<WorkflowTask[]>("/api/workflow/tasks");
    setTasks(res.data);
  };

  useEffect(() => {
    loadTasks();
  }, []);

  const addTask = async () => {
    if (!newTitle.trim()) return;
    await apiClient.post("/api/workflow/tasks", { title: newTitle.trim() });
    setNewTitle("");
    loadTasks();
  };

  const updateStatus = async (id: number, status: string) => {
    await apiClient.patch(`/api/workflow/tasks/${id}`, { status });
    loadTasks();
  };

  const deleteTask = async (id: number) => {
    await apiClient.delete(`/api/workflow/tasks/${id}`);
    loadTasks();
  };

  const generateDraft = async () => {
    if (!topic.trim()) return;
    setDraftLoading(true);
    try {
      const res = await apiClient.post("/api/workflow/notice-draft", {
        topic,
        audience,
        key_points: keyPointsText
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setDraft(res.data.draft);
    } finally {
      setDraftLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <h1 className="text-2xl font-semibold text-slate-900">업무 자동화</h1>
      <p className="mt-1 text-sm text-slate-500">업무 태스크를 관리하고, AI로 공지문 초안을 생성합니다.</p>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-4 text-base font-semibold text-slate-900">업무 목록</h2>
          <div className="mb-4 flex gap-2">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addTask()}
              placeholder="새 업무 입력…"
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <button
              onClick={addTask}
              className="flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              <Plus className="h-4 w-4" /> 추가
            </button>
          </div>
          <ul className="space-y-2">
            {tasks.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2"
              >
                <span className={`text-sm ${t.status === "done" ? "text-slate-400 line-through" : "text-slate-700"}`}>
                  {t.title}
                </span>
                <div className="flex items-center gap-2">
                  <select
                    value={t.status}
                    onChange={(e) => updateStatus(t.id, e.target.value)}
                    className="rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600"
                  >
                    {Object.entries(STATUS_LABEL).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <button onClick={() => deleteTask(t.id)} className="text-slate-400 hover:text-red-500">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </li>
            ))}
            {tasks.length === 0 && <p className="text-sm text-slate-400">등록된 업무가 없습니다.</p>}
          </ul>
        </div>

        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="mb-4 text-base font-semibold text-slate-900">AI 공지문 초안 생성</h2>
          <div className="space-y-3">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="주제 (예: 수시모집 서류 제출 안내)"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <input
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder="대상 (예: 지원자, 학부모)"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <textarea
              value={keyPointsText}
              onChange={(e) => setKeyPointsText(e.target.value)}
              placeholder="핵심 내용을 한 줄에 하나씩 입력하세요"
              rows={4}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500"
            />
            <button
              onClick={generateDraft}
              disabled={draftLoading}
              className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Sparkles className="h-4 w-4" />
              {draftLoading ? "생성 중…" : "초안 생성"}
            </button>
          </div>
          {draft && (
            <div className="mt-4 rounded-lg bg-slate-50 p-4 ring-1 ring-slate-200">
              <Markdown content={draft} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
