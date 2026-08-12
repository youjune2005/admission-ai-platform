import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Calendar,
  Copy,
  Download,
  ExternalLink,
  Plus,
  Search,
  X,
} from "lucide-react";
import { API_BASE_URL, apiClient } from "../api/client";
import type { ArchiveListResponse, ArchiveStatus, GeneratedDocument } from "../types";

const statusTabs: { key: "all" | ArchiveStatus; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "draft", label: "작성 중" },
  { key: "review", label: "직원 확인 필요" },
  { key: "approved", label: "승인 완료" },
  { key: "archived", label: "보관 완료" },
];

function statusClass(status: ArchiveStatus) {
  switch (status) {
    case "approved":
      return "bg-emerald-50 text-emerald-700";
    case "review":
      return "bg-orange-50 text-orange-700";
    case "draft":
      return "bg-sky-50 text-sky-700";
    case "archived":
      return "bg-slate-100 text-slate-500";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

function formatDt(value: string | null | undefined) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}.${m}.${day} ${hh}:${mm}`;
}

function formatDateOnly(value: string | null | undefined) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("ko-KR");
}

export default function Archive() {
  const [data, setData] = useState<ArchiveListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [tab, setTab] = useState<"all" | ArchiveStatus>("all");
  const [academicYear, setAcademicYear] = useState("all");
  const [admissionCategory, setAdmissionCategory] = useState("all");
  const [docType, setDocType] = useState("all");
  const [filterStatus, setFilterStatus] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(query.trim()), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  const activeStatus = filterStatus !== "all" ? filterStatus : tab;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        page_size: 10,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (activeStatus !== "all") params.status = activeStatus;
      if (academicYear !== "all") params.academic_year = academicYear;
      if (admissionCategory !== "all") params.admission_category = admissionCategory;
      if (docType !== "all") params.doc_type = docType;
      if (dateFrom) params.date_from = `${dateFrom}T00:00:00`;
      if (dateTo) params.date_to = `${dateTo}T23:59:59`;

      const res = await apiClient.get<ArchiveListResponse>("/api/archive", { params });
      setData(res.data);
      setSelectedId((prev) => {
        if (prev != null && res.data.items.some((d) => d.id === prev)) return prev;
        return res.data.items[0]?.id ?? null;
      });
    } catch {
      setData({
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        counts: { all: 0, draft: 0, review: 0, approved: 0, archived: 0 },
        facets: { academic_years: [], admission_categories: [], doc_types: [] },
      });
    } finally {
      setLoading(false);
    }
  }, [
    page,
    debouncedQ,
    activeStatus,
    academicYear,
    admissionCategory,
    docType,
    dateFrom,
    dateTo,
  ]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQ, tab, filterStatus, academicYear, admissionCategory, docType, dateFrom, dateTo]);

  const selected = useMemo(
    () => data?.items.find((d) => d.id === selectedId) ?? null,
    [data, selectedId]
  );

  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.page_size ?? 10)));

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (!data) return;
    if (selectedIds.size === data.items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.items.map((d) => d.id)));
    }
  };

  const duplicateDoc = async (doc: GeneratedDocument) => {
    setBusy(true);
    try {
      const res = await apiClient.post<GeneratedDocument>(`/api/archive/${doc.id}/duplicate`);
      setSelectedId(res.data.id);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const markArchived = async (doc: GeneratedDocument) => {
    setBusy(true);
    try {
      await apiClient.patch(`/api/archive/${doc.id}/status`, { status: "archived" });
      await load();
    } finally {
      setBusy(false);
    }
  };

  const openPdf = (doc: GeneratedDocument) => {
    if (!doc.pdf_url) return;
    window.open(`${API_BASE_URL}${doc.pdf_url}`, "_blank", "noopener,noreferrer");
  };

  const facets = data?.facets;
  const years = facets?.academic_years?.length ? facets.academic_years : ["2027", "2026"];
  const categories = facets?.admission_categories?.length
    ? facets.admission_categories
    : ["수시", "정시"];
  const types = facets?.doc_types?.length
    ? facets.doc_types
    : ["계획서", "예산안", "안내문", "FAQ", "보고서"];

  return (
    <div className="mx-auto flex h-full max-w-[1480px] gap-4 px-6 py-6">
      <div className="min-w-0 flex-1">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-[24px] font-bold text-slate-900">문서 보관함</h1>
            <p className="mt-1 text-[13px] text-slate-500">
              행정문서 작성으로 생성된 문서를 보관하고 관리합니다.
            </p>
          </div>
          <Link
            to="/documents/create"
            className="ui-pressable inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-blue)] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)]"
          >
            <Plus className="h-4 w-4" /> 새 문서 작성
          </Link>
        </div>

        <div className="mb-3 flex items-center gap-2 rounded-xl border border-[var(--ssu-border)] bg-white px-3 py-2.5 ui-surface">
          <Search className="h-4 w-4 shrink-0 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="문서 제목, 내용, 작성자 검색"
            className="w-full border-0 bg-transparent text-[13px] outline-none"
          />
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]">
          <select
            value="all"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700"
            disabled
          >
            <option>전체 문서</option>
          </select>
          <select
            value={academicYear}
            onChange={(e) => setAcademicYear(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700"
          >
            <option value="all">학년도 전체</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y.endsWith("학년도") ? y : `${y}학년도`}
              </option>
            ))}
          </select>
          <select
            value={admissionCategory}
            onChange={(e) => setAdmissionCategory(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700"
          >
            <option value="all">모집 구분</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700"
          >
            <option value="all">문서 유형</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <select
            value={filterStatus}
            onChange={(e) => {
              setFilterStatus(e.target.value);
              if (e.target.value !== "all") setTab(e.target.value as ArchiveStatus);
              else setTab("all");
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 font-semibold text-slate-700"
          >
            <option value="all">처리 상태</option>
            {statusTabs
              .filter((s) => s.key !== "all")
              .map((s) => (
                <option key={s.key} value={s.key}>
                  {s.label}
                </option>
              ))}
          </select>
          <label className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-2 font-semibold text-slate-700">
            <Calendar className="h-3.5 w-3.5 text-slate-500" />
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="border-0 bg-transparent text-[12px] font-semibold outline-none"
            />
            <span className="text-slate-300">~</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="border-0 bg-transparent text-[12px] font-semibold outline-none"
            />
          </label>
        </div>

        <div className="mb-3 flex gap-5 border-b border-slate-200 text-[14px]">
          {statusTabs.map((item) => {
            const count = data?.counts?.[item.key === "all" ? "all" : item.key] ?? 0;
            return (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  setTab(item.key);
                  setFilterStatus("all");
                }}
                className={`pb-2.5 font-bold ${
                  tab === item.key && filterStatus === "all"
                    ? "border-b-2 border-[var(--ssu-blue)] text-[var(--ssu-blue)]"
                    : "text-slate-600"
                }`}
              >
                {item.label}
                <span className="ml-1.5 font-bold text-slate-500">{count}</span>
              </button>
            );
          })}
        </div>

        <div className="overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white ui-surface">
          <table className="w-full text-left text-[14px]">
            <thead className="bg-slate-50 text-[13px] text-slate-700">
              <tr>
                <th className="w-12 px-4 py-4">
                  <input
                    type="checkbox"
                    checked={!!data?.items.length && selectedIds.size === data.items.length}
                    onChange={toggleAll}
                    className="rounded border-slate-300"
                  />
                </th>
                <th className="px-4 py-4 font-bold">문서 제목</th>
                <th className="px-4 py-4 font-bold">모집 구분</th>
                <th className="px-4 py-4 font-bold">문서 유형</th>
                <th className="px-4 py-4 font-bold">작성자</th>
                <th className="px-4 py-4 font-bold">최종 수정일</th>
                <th className="px-4 py-4 font-bold">처리 상태</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center font-semibold text-slate-500">
                    불러오는 중…
                  </td>
                </tr>
              )}
              {!loading &&
                data?.items.map((doc) => {
                  const active = selectedId === doc.id;
                  return (
                    <tr
                      key={doc.id}
                      onClick={() => setSelectedId(doc.id)}
                      className={`cursor-pointer border-t border-slate-100 transition-colors duration-200 ${
                        active ? "bg-blue-50" : "hover:bg-slate-50"
                      }`}
                    >
                      <td className="px-4 py-4" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(doc.id)}
                          onChange={() => toggleSelect(doc.id)}
                          className="rounded border-slate-300"
                        />
                      </td>
                      <td className="px-4 py-4 font-bold text-slate-900">{doc.title}</td>
                      <td className="px-4 py-4 font-semibold text-slate-800">
                        {doc.admission_category}
                      </td>
                      <td className="px-4 py-4 font-semibold text-slate-800">{doc.doc_type}</td>
                      <td className="px-4 py-4 font-semibold text-slate-800">{doc.author}</td>
                      <td className="px-4 py-4 font-semibold text-slate-800">
                        {formatDt(doc.updated_at)}
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className={`inline-flex rounded-full px-2.5 py-1 text-[12px] font-bold ${statusClass(
                            doc.status
                          )}`}
                        >
                          {doc.status_label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              {!loading && (data?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-14 text-center font-semibold text-slate-500">
                    행정문서 작성으로 생성된 문서가 없습니다.
                    <div className="mt-3">
                      <Link
                        to="/documents/create"
                        className="text-[13px] font-bold text-[var(--ssu-blue)] hover:underline"
                      >
                        새 문서 작성하기
                      </Link>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-3 flex items-center justify-between text-[12px] text-slate-500">
          <div className="flex items-center gap-1">
            {Array.from({ length: Math.min(totalPages, 6) }, (_, i) => i + 1).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setPage(p)}
                className={`min-w-7 rounded px-2 py-1 font-semibold ${
                  page === p
                    ? "bg-[var(--ssu-blue)] text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {p}
              </button>
            ))}
            {totalPages > 6 && (
              <>
                <span className="px-1">…</span>
                <button
                  type="button"
                  onClick={() => setPage(totalPages)}
                  className={`min-w-7 rounded px-2 py-1 font-semibold ${
                    page === totalPages
                      ? "bg-[var(--ssu-blue)] text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {totalPages}
                </button>
              </>
            )}
          </div>
          <p>총 {data?.total ?? 0}건</p>
        </div>
      </div>

      {selected && (
        <aside className="dropdown-enter flex w-[340px] shrink-0 flex-col rounded-xl border border-[var(--ssu-border)] bg-white">
          <div className="border-b border-slate-100 p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[15px] font-bold leading-snug text-slate-900">{selected.title}</p>
                <span
                  className={`mt-2 inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusClass(
                    selected.status
                  )}`}
                >
                  {selected.status_label}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setSelectedId(null)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            <dl className="space-y-2.5 text-[13px]">
              {(
                [
                  ["문서 유형", selected.doc_type],
                  ["모집 구분", selected.admission_category],
                  ["작성자", selected.author],
                  ["작성일", formatDateOnly(selected.created_at)],
                  ["최종 수정일", formatDateOnly(selected.updated_at)],
                  ["최종 수정자", selected.last_modifier],
                  ["승인일", formatDateOnly(selected.approved_at)],
                  ["승인자", selected.approver ?? "-"],
                  ["보관일", formatDateOnly(selected.archived_at)],
                  ["보관 위치", selected.archive_location ?? "-"],
                  ["버전", selected.version],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3">
                  <dt className="shrink-0 font-semibold text-slate-600">{label}</dt>
                  <dd className="text-right font-bold text-slate-900">{value}</dd>
                </div>
              ))}
            </dl>

            <div className="mt-5">
              <p className="mb-2 text-[12px] font-semibold text-slate-700">미리보기</p>
              <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
                {selected.preview_url ? (
                  <img
                    src={`${API_BASE_URL}${selected.preview_url}`}
                    alt={`${selected.title} 미리보기`}
                    className="mx-auto max-h-[280px] w-full object-contain object-top"
                  />
                ) : (
                  <div className="flex h-40 items-center justify-center text-[12px] text-slate-400">
                    미리보기가 없습니다.
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="space-y-2 border-t border-slate-100 p-4">
            <button
              type="button"
              disabled={!selected.pdf_url || busy}
              onClick={() => openPdf(selected)}
              className="ui-pressable flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--ssu-blue)] px-3 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
            >
              <ExternalLink className="h-4 w-4" />
              열기
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void duplicateDoc(selected)}
              className="ui-pressable flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <Copy className="h-4 w-4" />
              복제
            </button>
            <a
              href={selected.pdf_url ? `${API_BASE_URL}${selected.pdf_url}` : undefined}
              download
              className={`flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[13px] font-semibold ${
                selected.pdf_url
                  ? "text-slate-700 hover:bg-slate-50"
                  : "pointer-events-none text-slate-300"
              }`}
            >
              <Download className="h-4 w-4" />
              PDF 다운로드
            </a>
            {selected.status !== "archived" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void markArchived(selected)}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-[13px] font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                보관 완료로 변경
              </button>
            )}
          </div>
        </aside>
      )}
    </div>
  );
}
