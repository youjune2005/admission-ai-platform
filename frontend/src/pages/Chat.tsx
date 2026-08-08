import { useEffect, useRef, useState } from "react";
import { Send, Plus, Bot, User } from "lucide-react";
import { apiClient } from "../api/client";
import Markdown from "../components/Markdown";
import type { ChatMessage, ChatSession, ChatSessionDetail } from "../types";

export default function Chat() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadSessions = async () => {
    const res = await apiClient.get<ChatSession[]>("/api/chat/sessions");
    setSessions(res.data);
  };

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (activeSessionId === null) {
      setMessages([]);
      return;
    }
    apiClient
      .get<ChatSessionDetail>(`/api/chat/sessions/${activeSessionId}`)
      .then((res) => setMessages(res.data.messages));
  }, [activeSessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: text, created_at: new Date().toISOString() },
    ]);

    try {
      const wasNewSession = activeSessionId === null;
      const res = await apiClient.post<ChatMessage & { session_id: number }>(
        "/api/chat/message",
        { session_id: activeSessionId, message: text }
      );

      if (wasNewSession) {
        setActiveSessionId(res.data.session_id);
        await loadSessions();
        const detail = await apiClient.get<ChatSessionDetail>(
          `/api/chat/sessions/${res.data.session_id}`
        );
        setMessages(detail.data.messages);
      } else {
        setMessages((prev) => [...prev, res.data]);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full">
      <div className="w-64 shrink-0 border-r border-slate-200 bg-white p-4">
        <button
          onClick={() => setActiveSessionId(null)}
          className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
        >
          <Plus className="h-4 w-4" /> 새 상담
        </button>
        <div className="space-y-1 overflow-y-auto">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setActiveSessionId(s.id)}
              className={`block w-full truncate rounded-lg px-3 py-2 text-left text-sm ${
                activeSessionId === s.id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {s.title}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-1 flex-col">
        <div className="border-b border-slate-200 bg-white px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">AI 입시 상담</h1>
          <p className="text-sm text-slate-500">전형, 서류, 일정 등 입시행정 관련 질문에 답변합니다.</p>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {messages.length === 0 && (
            <div className="mx-auto max-w-md pt-16 text-center text-sm text-slate-400">
              궁금한 내용을 입력해 대화를 시작해보세요. 예) "2026학년도 수시 서류 제출 마감일이 언제야?"
            </div>
          )}
          <div className="mx-auto max-w-2xl space-y-4">
            {messages.map((m) => (
              <div key={m.id} className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                {m.role === "assistant" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-indigo-600">
                    <Bot className="h-4 w-4" />
                  </div>
                )}
                <div
                  className={`max-w-lg rounded-2xl px-4 py-2.5 text-sm ${
                    m.role === "user"
                      ? "whitespace-pre-wrap bg-indigo-600 text-white"
                      : "bg-white text-slate-800 shadow-sm ring-1 ring-slate-200"
                  }`}
                >
                  {m.role === "assistant" ? <Markdown content={m.content} /> : m.content}
                </div>
                {m.role === "user" && (
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200 text-slate-600">
                    <User className="h-4 w-4" />
                  </div>
                )}
              </div>
            ))}
            {loading && <div className="text-sm text-slate-400">AI가 답변을 작성 중입니다…</div>}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-slate-200 bg-white px-6 py-4">
          <div className="mx-auto flex max-w-2xl items-center gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              placeholder="메시지를 입력하세요…"
              className="flex-1 rounded-full border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-indigo-500"
            />
            <button
              onClick={sendMessage}
              disabled={loading}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
