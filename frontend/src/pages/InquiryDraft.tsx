import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  AlignCenter,
  AlignLeft,
  AlignRight,
  Bold,
  Check,
  CheckCircle2,
  ClipboardCopy,
  ExternalLink,
  Italic,
  Link2,
  List,
  ListOrdered,
  MessageSquareQuote,
  Redo2,
  RefreshCw,
  Save,
  Sparkles,
  Underline,
  Undo2,
  X,
} from "lucide-react";
import { apiClient } from "../api/client";
import Markdown from "../components/Markdown";
import { formatKstDateTimeLong, parseApiDate } from "../lib/datetime";
import type { Inquiry } from "../types";

function sortActivitiesNewestFirst<T extends { id: number; created_at: string }>(items: T[]) {
  return [...items].sort((a, b) => {
    const ta = parseApiDate(a.created_at)?.getTime() ?? 0;
    const tb = parseApiDate(b.created_at)?.getTime() ?? 0;
    if (tb !== ta) return tb - ta;
    return b.id - a.id;
  });
}

function relevanceClass(pct: number) {
  if (pct >= 85) return "bg-blue-50 text-blue-700";
  if (pct >= 60) return "bg-slate-100 text-slate-700";
  return "bg-orange-50 text-orange-700";
}

export default function InquiryDraft() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [inquiry, setInquiry] = useState<Inquiry | null>(null);
  const [draft, setDraft] = useState("");
  const [aiBaseline, setAiBaseline] = useState("");
  const [rightTab, setRightTab] = useState<"refs" | "review">("refs");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackText, setFeedbackText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  const isDraftEdited = useMemo(
    () => draft.trim() !== aiBaseline.trim() && draft.trim().length > 0,
    [draft, aiBaseline],
  );

  const applyInquiry = (data: Inquiry) => {
    setInquiry(data);
    setDraft(data.draft_answer ?? "");
    setAiBaseline(data.ai_draft_answer ?? data.draft_answer ?? "");
  };

  const load = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<Inquiry>(`/api/inquiry/${id}`);
      applyInquiry(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "문의를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const wrapSelection = (before: string, after = before) => {
    const el = editorRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = draft.slice(start, end) || "텍스트";
    const next = draft.slice(0, start) + before + selected + after + draft.slice(end);
    setDraft(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + before.length, start + before.length + selected.length);
    });
  };

  const insertLinePrefix = (prefix: string) => {
    const el = editorRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const lineStart = draft.lastIndexOf("\n", start - 1) + 1;
    const next = draft.slice(0, lineStart) + prefix + draft.slice(lineStart);
    setDraft(next);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + prefix.length, start + prefix.length);
    });
  };

  const saveDraft = async () => {
    if (!inquiry) return;
    setSaving(true);
    setError(null);
    try {
      const res = await apiClient.patch<Inquiry>(`/api/inquiry/${inquiry.id}`, {
        draft_answer: draft,
      });
      setInquiry(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "저장 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const regenerate = async () => {
    if (!inquiry) return;
    setRegenerating(true);
    setError(null);
    try {
      const res = await apiClient.post<Inquiry>(`/api/inquiry/${inquiry.id}/regenerate`);
      applyInquiry(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "다시 생성 중 오류가 발생했습니다.");
    } finally {
      setRegenerating(false);
    }
  };

  const requestFeedback = async () => {
    if (!inquiry || !isDraftEdited) return;
    setFeedbackOpen(true);
    setFeedbackLoading(true);
    setFeedbackText(null);
    setError(null);
    try {
      const res = await apiClient.post<{ feedback: string }>(`/api/inquiry/${inquiry.id}/feedback`, {
        draft_answer: draft,
      });
      setFeedbackText(res.data.feedback);
      const refreshed = await apiClient.get<Inquiry>(`/api/inquiry/${inquiry.id}`);
      setInquiry(refreshed.data);
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? "피드백 생성 중 오류가 발생했습니다.";
      setFeedbackText(null);
      setError(typeof detail === "string" ? detail : "피드백 생성 중 오류가 발생했습니다.");
      setFeedbackOpen(false);
    } finally {
      setFeedbackLoading(false);
    }
  };

  const copyDraft = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("클립보드 복사에 실패했습니다.");
    }
  };

  const markReviewed = async () => {
    if (!inquiry) return;
    setSaving(true);
    try {
      const res = await apiClient.patch<Inquiry>(`/api/inquiry/${inquiry.id}`, {
        draft_answer: draft,
        status: "reviewed",
      });
      setInquiry(res.data);
      navigate("/inquiry");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "검토 완료 처리 중 오류가 발생했습니다.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-[13px] text-slate-500">
        불러오는 중…
      </div>
    );
  }

  if (!inquiry) {
    return (
      <div className="mx-auto max-w-[900px] px-6 py-10 text-center">
        <p className="text-[14px] text-slate-600">{error ?? "문의를 찾을 수 없습니다."}</p>
        <Link to="/inquiry" className="mt-4 inline-block text-[13px] font-semibold text-[var(--ssu-blue)]">
          목록으로
        </Link>
      </div>
    );
  }

  const toolbarBtn =
    "inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 hover:text-slate-800";

  return (
    <div className="mx-auto flex h-full max-w-[1400px] flex-col gap-4 overflow-y-auto px-6 py-6 phone:h-auto phone:px-4 phone:py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[12px] text-slate-500">
            <Link to="/inquiry" className="hover:text-[var(--ssu-blue)]">
              입시 문의 답변
            </Link>
            <span className="mx-1.5">/</span>
            답변 초안 확인
          </p>
          <h1 className="mt-1 text-[24px] font-bold text-slate-900 phone:text-[20px]">답변 초안 확인</h1>
        </div>
      </div>

      {error && <p className="text-[13px] text-red-500">{error}</p>}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-4">
          <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <p className="text-[15px] font-bold text-slate-900">원본 문의</p>
              <span className="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-1.5 text-[12px] font-semibold text-[var(--ssu-blue)]">
                <Sparkles className="h-3.5 w-3.5" />
                AI 생성됨
              </span>
            </div>
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] leading-relaxed text-slate-800 whitespace-pre-wrap">
              {inquiry.content}
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              {inquiry.academic_year}학년도 · {inquiry.admission_type} ·{" "}
              {inquiry.selection_type || "전형 미지정"} · {inquiry.asker_type}
            </p>
          </section>

          <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 phone:flex-col phone:items-start">
              <p className="text-[15px] font-bold text-slate-900">AI 답변 초안</p>
              <button
                type="button"
                onClick={requestFeedback}
                disabled={!isDraftEdited || feedbackLoading}
                title={
                  isDraftEdited
                    ? "수정한 부분에 대한 AI 피드백 받기"
                    : "초안을 수정하면 피드백을 요청할 수 있습니다"
                }
                className="ui-pressable inline-flex items-center gap-1.5 rounded-lg bg-[var(--ssu-blue)] px-3 py-1.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <MessageSquareQuote className="h-3.5 w-3.5" />
                {feedbackLoading ? "분석 중…" : "AI 피드백"}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-0.5 border-b border-slate-100 px-3 py-2">
              <button type="button" className={toolbarBtn} onClick={() => wrapSelection("**")} title="굵게">
                <Bold className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} onClick={() => wrapSelection("*")} title="기울임">
                <Italic className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} onClick={() => wrapSelection("__")} title="밑줄">
                <Underline className="h-4 w-4" />
              </button>
              <span className="mx-1 h-4 w-px bg-slate-200" />
              <button type="button" className={toolbarBtn} onClick={() => insertLinePrefix("- ")} title="목록">
                <List className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} onClick={() => insertLinePrefix("1. ")} title="번호 목록">
                <ListOrdered className="h-4 w-4" />
              </button>
              <span className="mx-1 h-4 w-px bg-slate-200" />
              <button type="button" className={toolbarBtn} title="왼쪽 정렬">
                <AlignLeft className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} title="가운데 정렬">
                <AlignCenter className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} title="오른쪽 정렬">
                <AlignRight className="h-4 w-4" />
              </button>
              <span className="mx-1 h-4 w-px bg-slate-200" />
              <button
                type="button"
                className={toolbarBtn}
                onClick={() => wrapSelection("[", "](https://)")}
                title="링크"
              >
                <Link2 className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} onClick={() => document.execCommand("undo")} title="실행 취소">
                <Undo2 className="h-4 w-4" />
              </button>
              <button type="button" className={toolbarBtn} onClick={() => document.execCommand("redo")} title="다시 실행">
                <Redo2 className="h-4 w-4" />
              </button>
            </div>
            <textarea
              ref={editorRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={16}
              className="w-full resize-y border-0 px-5 py-4 text-[13px] leading-relaxed text-slate-800 outline-none"
              placeholder="AI 답변 초안이 여기에 표시됩니다. 직접 수정할 수 있습니다."
            />
            <div className="flex items-center gap-2 border-t border-slate-100 px-5 py-3 text-[12px] text-emerald-700">
              <CheckCircle2 className="h-4 w-4" />
              상태:{" "}
              {inquiry.references.length > 0 ? "근거 확인 완료" : "근거 자료 없음 — 수동 검토 권장"}
            </div>
          </section>

          <div className="flex flex-wrap gap-2 phone:pb-2">
            <button
              type="button"
              onClick={regenerate}
              disabled={regenerating}
              className="ui-pressable inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${regenerating ? "animate-spin" : ""}`} />
              다시 생성
            </button>
            <button
              type="button"
              onClick={saveDraft}
              disabled={saving}
              className="ui-pressable inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <Save className="h-4 w-4" />
              {saving ? "저장 중…" : "임시 저장"}
            </button>
            <button
              type="button"
              onClick={copyDraft}
              className="ui-pressable inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-700 hover:bg-slate-50"
            >
              {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <ClipboardCopy className="h-4 w-4" />}
              {copied ? "복사됨" : "복사"}
            </button>
            <button
              type="button"
              onClick={markReviewed}
              disabled={saving}
              className="ui-pressable ml-auto inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-blue)] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50 phone:ml-0 phone:w-full phone:justify-center"
            >
              <Check className="h-4 w-4" />
              검토 완료
            </button>
          </div>
        </div>

        <div className="space-y-4">
          <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white">
            <div className="flex border-b border-slate-100 text-[13px]">
              <button
                type="button"
                onClick={() => setRightTab("refs")}
                className={`flex-1 px-4 py-3 font-semibold ${
                  rightTab === "refs"
                    ? "border-b-2 border-[var(--ssu-blue)] text-[var(--ssu-blue)]"
                    : "text-slate-500"
                }`}
              >
                근거 문서
              </button>
              <button
                type="button"
                onClick={() => setRightTab("review")}
                className={`flex-1 px-4 py-3 font-semibold ${
                  rightTab === "review"
                    ? "border-b-2 border-[var(--ssu-blue)] text-[var(--ssu-blue)]"
                    : "text-slate-500"
                }`}
              >
                검토 사항
              </button>
            </div>

            {rightTab === "refs" ? (
              <div className="space-y-3 p-4">
                <p className="text-[13px] font-bold text-slate-900">근거 자료</p>
                {inquiry.references.map((ref, idx) => (
                  <div
                    key={`${ref.document_id}-${idx}`}
                    className="rounded-xl border border-slate-200 bg-white p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[12px] font-semibold text-slate-800">
                        {idx + 1}. {ref.filename}
                      </p>
                      <span
                        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${relevanceClass(ref.relevance)}`}
                      >
                        관련도 {ref.relevance}%
                      </span>
                    </div>
                    {ref.snippet && (
                      <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{ref.snippet}</p>
                    )}
                    <Link
                      to="/regulations"
                      className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--ssu-blue)]"
                    >
                      원문 보기 <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                ))}
                {inquiry.references.length === 0 && (
                  <p className="rounded-lg bg-slate-50 px-3 py-6 text-center text-[12px] text-slate-400">
                    매칭된 근거 자료가 없습니다.
                  </p>
                )}

                {inquiry.check_notes.length > 0 && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
                    <p className="text-[12px] font-bold text-amber-900">담당자 확인 사항</p>
                    <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] leading-relaxed text-amber-900">
                      {inquiry.check_notes.map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="p-4">
                <ul className="list-disc space-y-2 pl-4 text-[12px] leading-relaxed text-slate-700">
                  {(inquiry.check_notes.length
                    ? inquiry.check_notes
                    : ["초안 내용을 원문 규정과 대조해 주세요."]
                  ).map((note) => (
                    <li key={note}>{note}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white p-4">
            <p className="text-[13px] font-bold text-slate-900">활동 로그</p>
            <ul className="mt-3 space-y-3">
              {[...sortActivitiesNewestFirst(inquiry.activities)].map((act) => (
                <li key={act.id} className="flex gap-3">
                  <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[var(--ssu-blue)]" />
                  <div>
                    <p className="text-[12px] font-medium text-slate-800">{act.message}</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">
                      {formatKstDateTimeLong(act.created_at)}
                    </p>
                  </div>
                </li>
              ))}
              {inquiry.activities.length === 0 && (
                <li className="text-[12px] text-slate-400">활동 기록이 없습니다.</li>
              )}
            </ul>
          </section>
        </div>
      </div>

      {feedbackOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="feedback-title"
            className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl bg-white shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <p id="feedback-title" className="text-[15px] font-bold text-slate-900">
                  AI 피드백
                </p>
                <p className="mt-0.5 text-[12px] text-slate-500">수정하신 부분에 대한 검토 의견입니다.</p>
              </div>
              <button
                type="button"
                onClick={() => setFeedbackOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-[13px] leading-relaxed text-slate-800">
              {feedbackLoading ? (
                <p className="py-8 text-center text-slate-500">수정 내용을 분석하는 중…</p>
              ) : feedbackText ? (
                <Markdown content={feedbackText} />
              ) : (
                <p className="py-8 text-center text-slate-400">피드백을 불러오지 못했습니다.</p>
              )}
            </div>
            <div className="border-t border-slate-100 px-5 py-3 text-right">
              <button
                type="button"
                onClick={() => setFeedbackOpen(false)}
                className="rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white"
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
