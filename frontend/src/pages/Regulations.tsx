import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  FolderSync,
  MoreHorizontal,
  RefreshCw,
  UploadCloud,
} from "lucide-react";
import { apiClient } from "../api/client";
import type { DocumentListResponse, IngestResult, UploadedDocument } from "../types";

const tabs = ["모집요강", "입학처 공지", "FAQ", "예산·행정 규정", "문서 양식"] as const;

function formatDate(value?: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value.slice(0, 10);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** 숫자만 받아 YYYY-MM-DD 형태로 포맷 */
function formatDateTyping(raw: string) {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

function statusClass(status: string) {
  if (status === "needs_update") return "bg-orange-50 text-orange-700";
  if (status === "processing") return "bg-sky-50 text-sky-700";
  return "bg-emerald-50 text-emerald-700";
}

export default function Regulations() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("예산·행정 규정");
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [uploadCategory, setUploadCategory] = useState<(typeof tabs)[number]>("예산·행정 규정");
  const [version, setVersion] = useState("V1.0");
  const [appliedDate, setAppliedDate] = useState("");
  const [description, setDescription] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLInputElement>(null);

  const loadDocs = async (opts?: { category?: string; page?: number; pageSize?: number }) => {
    const cat = opts?.category ?? activeTab;
    const p = opts?.page ?? page;
    const ps = opts?.pageSize ?? pageSize;
    const res = await apiClient.get<DocumentListResponse>("/api/documents", {
      params: { category: cat, page: p, page_size: ps },
    });
    setData(res.data);
  };

  useEffect(() => {
    loadDocs().catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, page, pageSize]);

  const counts = data?.counts ?? { total: 0, latest: 0, needs_update: 0, processing: 0 };
  const docs: UploadedDocument[] = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));

  const kpiCards = useMemo(
    () => [
      {
        label: "전체 자료",
        value: counts.total,
        icon: FileText,
        iconWrap: "bg-blue-50 text-blue-600",
      },
      {
        label: "최신 적용",
        value: counts.latest,
        icon: CheckCircle2,
        iconWrap: "bg-blue-50 text-blue-600",
      },
      {
        label: "업데이트 필요",
        value: counts.needs_update,
        icon: AlertTriangle,
        iconWrap: "bg-orange-50 text-orange-600",
      },
      {
        label: "처리 중",
        value: counts.processing,
        icon: Clock3,
        iconWrap: "bg-sky-50 text-sky-600",
      },
    ],
    [counts],
  );

  const syncDataFolder = async () => {
    setSyncing(true);
    setError(null);
    try {
      const res = await apiClient.post<IngestResult>("/api/documents/ingest-data-folder");
      setSyncResult(res.data);
      await loadDocs({ page: 1 });
      setPage(1);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "동기화 중 오류가 발생했습니다.");
    } finally {
      setSyncing(false);
    }
  };

  const pickFile = (file: File | null) => {
    if (!file) return;
    setSelectedFile(file);
    if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, ""));
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("업로드할 파일을 선택하세요.");
      return;
    }
    if (!title.trim()) {
      setError("자료명을 입력하세요.");
      return;
    }
    if (!version.trim()) {
      setError("버전을 입력하세요.");
      return;
    }

    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("title", title.trim());
    form.append("category", uploadCategory);
    form.append("version", version.trim());
    if (/^\d{4}-\d{2}-\d{2}$/.test(appliedDate)) form.append("applied_date", appliedDate);
    if (description.trim()) form.append("description", description.trim());

    try {
      await apiClient.post("/api/documents/upload", form);
      setSelectedFile(null);
      setTitle("");
      setVersion("V1.0");
      setAppliedDate("");
      setDescription("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      setActiveTab(uploadCategory);
      setPage(1);
      await loadDocs({ category: uploadCategory, page: 1 });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "업로드 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1400px] gap-4 px-6 py-6">
      <div className="min-w-0 flex-1">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h1 className="text-[24px] font-bold text-slate-900">규정·자료 관리</h1>
            <p className="mt-1 text-[13px] text-slate-500">
              모집요강·FAQ·행정 규정을 등록하고 AI가 참고할 수 있도록 인덱싱합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={syncDataFolder}
            disabled={syncing}
            className="ui-pressable inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-navy)] px-3 py-2 text-[13px] font-semibold text-white disabled:opacity-50"
          >
            {syncing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <FolderSync className="h-4 w-4" />}
            data/ 폴더 동기화
          </button>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
          {kpiCards.map((card) => {
            const Icon = card.icon;
            return (
              <div
                key={card.label}
                className="ui-surface flex items-center justify-between rounded-xl border border-[var(--ssu-border)] bg-white p-4"
              >
                <div>
                  <p className="text-[12px] text-slate-500">{card.label}</p>
                  <p className="mt-2 text-[28px] font-bold text-slate-900">{card.value}</p>
                </div>
                <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${card.iconWrap}`}>
                  <Icon className="h-5 w-5" />
                </div>
              </div>
            );
          })}
        </div>

        <div className="mb-3 flex gap-4 border-b border-slate-200 text-[13px]">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setActiveTab(tab);
                setPage(1);
              }}
              className={`ui-pressable pb-2 font-semibold ${
                activeTab === tab
                  ? "border-b-2 border-[var(--ssu-blue)] text-[var(--ssu-blue)]"
                  : "text-slate-500"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {syncResult && (
          <div className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
            새로 추가 {syncResult.ingested.length}건
            {syncResult.skipped.length > 0 && ` · 이미 처리됨 ${syncResult.skipped.length}건`}
            {syncResult.failed.length > 0 && ` · 실패 ${syncResult.failed.length}건`}
          </div>
        )}
        {error && <p className="mb-3 text-[13px] text-red-500">{error}</p>}

        <div className="ui-surface overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-slate-50 text-[12px] text-slate-500">
              <tr>
                <th className="px-4 py-3 font-medium">자료명</th>
                <th className="px-4 py-3 font-medium">버전</th>
                <th className="px-4 py-3 font-medium">최종 업데이트</th>
                <th className="px-4 py-3 font-medium">상태</th>
                <th className="px-4 py-3 text-right font-medium">관리</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.id} className="border-t border-slate-100">
                  <td className="px-4 py-3.5 font-semibold text-slate-800">{doc.filename}</td>
                  <td className="px-4 py-3.5 text-slate-600">{doc.version}</td>
                  <td className="px-4 py-3.5 text-slate-600">
                    {formatDate(doc.updated_at ?? doc.created_at)}
                  </td>
                  <td className="px-4 py-3.5">
                    <span
                      className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusClass(doc.status)}`}
                    >
                      {doc.status_label}
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <button
                      type="button"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                      aria-label="관리"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))}
              {docs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                    이 카테고리에 등록된 자료가 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-[12px] text-slate-500">
            <span>전체 {data?.total ?? 0}건</span>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="inline-flex h-7 w-7 items-center justify-center rounded border border-slate-200 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="min-w-[1.5rem] text-center font-semibold text-slate-700">{page}</span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  className="inline-flex h-7 w-7 items-center justify-center rounded border border-slate-200 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value));
                  setPage(1);
                }}
                className="rounded-lg border border-slate-200 px-2 py-1.5 text-[12px]"
              >
                <option value={10}>10개씩 보기</option>
                <option value={20}>20개씩 보기</option>
                <option value={50}>50개씩 보기</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <aside className="ui-surface w-[320px] shrink-0 self-start rounded-xl border border-[var(--ssu-border)] bg-white p-4">
        <p className="text-[14px] font-bold text-slate-900">자료 업로드</p>
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            pickFile(e.dataTransfer.files?.[0] ?? null);
          }}
          className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center hover:border-[var(--ssu-blue)]"
        >
          <UploadCloud className="mb-2 h-7 w-7 text-[var(--ssu-blue)]" />
          <p className="text-[12px] font-medium text-slate-700">파일을 드래그하여 놓거나 파일 선택</p>
          <p className="mt-1 text-[11px] text-slate-400">지원 형식: PDF, DOCX, XLSX</p>
          <p className="text-[11px] text-slate-400">최대 용량: 50MB</p>
          {selectedFile && (
            <p className="mt-2 max-w-full truncate text-[11px] font-medium text-[var(--ssu-blue)]">
              {selectedFile.name}
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx,.xls,.md,.txt"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="mt-4 space-y-3 text-[12px]">
          <div>
            <label className="mb-1 block font-medium text-slate-600">
              자료명 <span className="text-red-500">*</span>
            </label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
              placeholder="자료명을 입력하세요"
            />
          </div>
          <div>
            <label className="mb-1 block font-medium text-slate-600">
              카테고리 <span className="text-red-500">*</span>
            </label>
            <select
              value={uploadCategory}
              onChange={(e) => setUploadCategory(e.target.value as (typeof tabs)[number])}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
            >
              {tabs.map((tab) => (
                <option key={tab} value={tab}>
                  {tab}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block font-medium text-slate-600">
              버전 <span className="text-red-500">*</span>
            </label>
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
              placeholder="예: V1.0"
            />
          </div>
          <div>
            <label className="mb-1 block font-medium text-slate-600">적용일자</label>
            <div className="relative">
              <input
                type="text"
                inputMode="numeric"
                autoComplete="off"
                placeholder="YYYY-MM-DD"
                value={appliedDate}
                onChange={(e) => setAppliedDate(formatDateTyping(e.target.value))}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 pr-10 outline-none focus:border-[var(--ssu-blue)]"
              />
              <button
                type="button"
                onClick={() => {
                  const el = datePickerRef.current;
                  if (!el) return;
                  try {
                    el.showPicker();
                  } catch {
                    el.click();
                  }
                }}
                className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="날짜 선택"
              >
                <Calendar className="h-4 w-4" />
              </button>
              <input
                ref={datePickerRef}
                type="date"
                tabIndex={-1}
                value={/^\d{4}-\d{2}-\d{2}$/.test(appliedDate) ? appliedDate : ""}
                onChange={(e) => setAppliedDate(e.target.value)}
                className="pointer-events-none absolute h-0 w-0 opacity-0"
                aria-hidden
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block font-medium text-slate-600">설명</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
              rows={3}
              placeholder="설명을 입력하세요 (선택)"
            />
          </div>
          <button
            type="button"
            onClick={handleUpload}
            disabled={loading}
            className="ui-pressable w-full rounded-lg bg-[var(--ssu-blue)] py-2.5 text-[13px] font-semibold text-white disabled:opacity-50"
          >
            {loading ? "업로드 중…" : "업로드"}
          </button>
        </div>
      </aside>
    </div>
  );
}
