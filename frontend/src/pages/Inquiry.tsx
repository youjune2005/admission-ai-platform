import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CheckCircle2, ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { apiClient } from "../api/client";
import { formatKstDate, formatKstDateTime } from "../lib/datetime";
import type { Inquiry, InquiryListResponse, InquiryReferenceDoc } from "../types";

const YEARS = ["2027", "2026"];
const ADMISSION_TYPES = ["수시모집", "정시모집"];
const SELECTION_TYPES = ["", "학생부종합", "학생부교과", "논술우수자", "실기/실적"];

function statusBadge(status: string) {
  if (status === "generating") {
    return "bg-orange-50 text-orange-700";
  }
  if (status === "completed" || status === "reviewed") {
    return "bg-emerald-50 text-emerald-700";
  }
  return "bg-slate-100 text-slate-600";
}

export default function InquiryPage() {
  const navigate = useNavigate();
  const [year, setYear] = useState("2027");
  const [admissionType, setAdmissionType] = useState("수시모집");
  const [selectionType, setSelectionType] = useState("");
  const [askerType, setAskerType] = useState<"학생" | "학부모">("학생");
  const [content, setContent] = useState("");
  const [refs, setRefs] = useState<InquiryReferenceDoc[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [history, setHistory] = useState<Inquiry[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 5;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [refsError, setRefsError] = useState<string | null>(null);

  const loadHistory = async (p = page) => {
    try {
      const res = await apiClient.get<InquiryListResponse>("/api/inquiry", {
        params: { page: p, page_size: pageSize },
      });
      setHistory(res.data.items);
      setTotal(res.data.total);
      setHistoryError(null);
    } catch (err: any) {
      setHistory([]);
      setTotal(0);
      setHistoryError(
        err?.response?.data?.detail ?? "최근 문의 내역을 불러오지 못했습니다."
      );
    }
  };

  const loadRefs = async () => {
    try {
      const res = await apiClient.get<InquiryReferenceDoc[]>("/api/inquiry/references");
      setRefs(res.data);
      setSelectedIds(res.data.map((d) => d.id));
      setRefsError(null);
    } catch (err: any) {
      setRefs([]);
      setSelectedIds([]);
      setRefsError(err?.response?.data?.detail ?? "규정·자료를 불러오지 못했습니다.");
    }
  };

  useEffect(() => {
    void loadRefs();
  }, []);

  useEffect(() => {
    void loadHistory(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const charCount = content.length;

  const toggleDoc = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const displayRefs = useMemo(() => refs.slice(0, 8), [refs]);

  const handleGenerate = async () => {
    const text = content.trim();
    if (!text || loading) return;
    if (!selectionType) {
      setError("전형을 선택하세요.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post<Inquiry>("/api/inquiry/generate", {
        content: text,
        academic_year: year,
        admission_type: admissionType,
        selection_type: selectionType,
        asker_type: askerType,
        document_ids: selectedIds,
      });
      navigate(`/inquiry/${res.data.id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "답변 생성 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1400px] flex-col gap-4 overflow-y-auto px-6 py-6 phone:h-auto phone:px-4 phone:py-4">
      <div>
        <h1 className="text-[24px] font-bold text-slate-900 phone:text-[20px]">입시 문의 답변</h1>
        <p className="mt-1 text-[13px] text-slate-500">
          모집요강·회의록·재무현황 근거를 바탕으로 정확한 답변 초안을 생성합니다.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_400px]">
        {/* 문의 입력 */}
        <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white p-5">
          <p className="text-[15px] font-bold text-slate-900">문의 내용 입력</p>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-3 phone:grid-cols-1!">
            <select
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-2.5 text-[13px] outline-none focus:border-[var(--ssu-blue)]"
            >
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}학년도
                </option>
              ))}
            </select>
            <select
              value={admissionType}
              onChange={(e) => setAdmissionType(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-2.5 text-[13px] outline-none focus:border-[var(--ssu-blue)]"
            >
              {ADMISSION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <select
              value={selectionType}
              onChange={(e) => setSelectionType(e.target.value)}
              className="rounded-lg border border-slate-200 px-3 py-2.5 text-[13px] outline-none focus:border-[var(--ssu-blue)]"
            >
              <option value="">전형을 선택하세요</option>
              {SELECTION_TYPES.filter(Boolean).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4">
            <p className="mb-2 text-[12px] font-medium text-slate-600">문의자 구분</p>
            <div className="inline-flex overflow-hidden rounded-lg border border-slate-200">
              {(["학생", "학부모"] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setAskerType(type)}
                  className={`px-5 py-2 text-[13px] font-semibold ${
                    askerType === type
                      ? "bg-[var(--ssu-blue)] text-white"
                      : "bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-4">
            <p className="mb-2 text-[12px] font-medium text-slate-600">문의 내용</p>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value.slice(0, 1000))}
              rows={5}
              placeholder="문의 내용을 입력하세요…"
              className="w-full resize-none rounded-xl border border-slate-200 px-3 py-3 text-[13px] leading-relaxed outline-none focus:border-[var(--ssu-blue)]"
            />
            <div className="mt-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">
                  <CheckCircle2 className="h-3 w-3" />
                  마스킹 적용됨
                </span>
                <span>이름·연락처 등 개인정보는 자동으로 마스킹됩니다.</span>
              </div>
              <span className="text-[11px] text-slate-400">
                {charCount} / 1,000
              </span>
            </div>
          </div>

          {error && <p className="mt-3 text-[13px] text-red-500">{error}</p>}

          <button
            type="button"
            onClick={handleGenerate}
            disabled={loading || !content.trim()}
            className="ui-pressable mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--ssu-blue)] py-3 text-[14px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {loading ? "답변 생성 중…" : "AI 답변 생성"}
          </button>
        </section>

        {/* 답변 생성 전 확인 */}
        <aside className="ui-surface self-start rounded-xl border border-[var(--ssu-border)] bg-white p-5">
          <p className="text-[15px] font-bold text-slate-900">답변 생성 전 확인</p>
          <p className="mt-3 text-[12px] font-semibold text-slate-600">참고 자료</p>
          <ul className="mt-2 max-h-[420px] space-y-2 overflow-y-auto">
            {displayRefs.map((doc) => (
              <li
                key={doc.id}
                className="flex items-start gap-2.5 rounded-lg bg-slate-50 px-3 py-2.5"
              >
                <input
                  type="checkbox"
                  checked={selectedIds.includes(doc.id)}
                  onChange={() => toggleDoc(doc.id)}
                  className="mt-0.5 accent-[var(--ssu-blue)]"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[12px] font-medium text-slate-800">{doc.filename}</p>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    {formatKstDate(doc.updated_at ?? doc.created_at, "", ".")}
                    {doc.category ? ` · ${doc.category}` : ""}
                  </p>
                </div>
              </li>
            ))}
            {displayRefs.length === 0 && (
              <li className="rounded-lg bg-slate-50 px-3 py-4 text-center text-[12px] text-slate-400">
                {refsError ? (
                  <span className="flex flex-col items-center gap-2">
                    <span className="text-red-600">{refsError}</span>
                    <button
                      type="button"
                      onClick={() => void loadRefs()}
                      className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-slate-100"
                    >
                      다시 시도
                    </button>
                  </span>
                ) : (
                  "등록된 규정·자료가 없습니다."
                )}
              </li>
            )}
          </ul>
          <div className="mt-4 rounded-lg bg-blue-50 px-3 py-3 text-[12px] leading-relaxed text-blue-800">
            체크된 자료만 근거로 사용하며, 오래된 자료는 자동으로 제외됩니다.
          </div>
        </aside>
      </div>

      {/* 최근 문의 내역 */}
      <section className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white">
        <div className="border-b border-slate-100 px-5 py-4">
          <p className="text-[15px] font-bold text-slate-900">최근 문의 내역</p>
        </div>
        <div className="hidden phone:block">
          {history.length === 0 ? (
            <div className="px-4 py-10 text-center text-[13px] text-slate-400">
              {historyError ? (
                <span className="inline-flex flex-col items-center gap-3">
                  <span className="text-red-600">{historyError}</span>
                  <button
                    type="button"
                    onClick={() => void loadHistory(page)}
                    className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700"
                  >
                    다시 시도
                  </button>
                </span>
              ) : (
                "최근 문의 내역이 없습니다. 위에서 문의를 입력해 보세요."
              )}
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {history.map((item) => (
                <li key={item.id} className="px-4 py-3.5">
                  <p className="text-[13px] font-semibold leading-snug text-slate-800">
                    {item.content}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                    <span>{item.selection_type || "-"}</span>
                    <span>·</span>
                    <span>{item.asker_type}</span>
                    <span>·</span>
                    <span>{formatKstDateTime(item.created_at)}</span>
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusBadge(item.status)}`}
                    >
                      {item.status_label}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate(`/inquiry/${item.id}`)}
                    className="mt-2 rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-semibold text-slate-700"
                  >
                    조회
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="overflow-x-auto phone:hidden">
          <table className="w-full min-w-[900px] text-left text-[13px]">
            <thead className="bg-slate-50 text-[12px] text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">번호</th>
                <th className="px-4 py-3 font-medium">문의 내용</th>
                <th className="px-4 py-3 font-medium">전형</th>
                <th className="px-4 py-3 font-medium">문의자 구분</th>
                <th className="px-4 py-3 font-medium">문의 일시</th>
                <th className="px-4 py-3 font-medium">답변 상태</th>
                <th className="px-4 py-3 text-right font-medium">작업</th>
              </tr>
            </thead>
            <tbody>
              {history.map((item, idx) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="px-4 py-3.5 text-slate-500">
                    {total - ((page - 1) * pageSize + idx)}
                  </td>
                  <td className="max-w-[320px] truncate px-4 py-3.5 font-medium text-slate-800">
                    {item.content}
                  </td>
                  <td className="px-4 py-3.5 text-slate-600">{item.selection_type || "-"}</td>
                  <td className="px-4 py-3.5 text-slate-600">{item.asker_type}</td>
                  <td className="px-4 py-3.5 text-slate-600">{formatKstDateTime(item.created_at)}</td>
                  <td className="px-4 py-3.5">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusBadge(item.status)}`}
                    >
                      {item.status_label}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <button
                      type="button"
                      onClick={() => navigate(`/inquiry/${item.id}`)}
                      className="rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      조회
                    </button>
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                    {historyError ? (
                      <span className="inline-flex flex-col items-center gap-3">
                        <span className="text-red-600">{historyError}</span>
                        <button
                          type="button"
                          onClick={() => void loadHistory(page)}
                          className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-semibold text-slate-700 hover:bg-slate-100"
                        >
                          다시 시도
                        </button>
                      </span>
                    ) : (
                      "최근 문의 내역이 없습니다. 위에서 문의를 입력해 보세요."
                    )}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-center gap-2 border-t border-slate-100 px-4 py-3">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[1.5rem] text-center text-[13px] font-semibold text-slate-700">
            {page}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 disabled:opacity-40"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </section>
    </div>
  );
}
