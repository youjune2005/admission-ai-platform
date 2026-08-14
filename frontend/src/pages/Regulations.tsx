import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  Eye,
  FileText,
  FolderSync,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Replace,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import { API_BASE_URL, apiClient } from "../api/client";
import { formatKstDate, todayKstDate } from "../lib/datetime";
import type {
  DocumentListResponse,
  IngestResult,
  RegulationStatus,
  UploadedDocument,
} from "../types";

const tabs = ["모집요강", "입학처 공지", "회의록", "재무현황", "예산·행정 규정", "문서 양식"] as const;
const ACCEPT = ".pdf,.docx,.xlsx,.xls,.md,.txt,.hwp,.hwpx";
const SUPPORTED = new Set([
  ".pdf",
  ".docx",
  ".xlsx",
  ".xls",
  ".md",
  ".txt",
  ".hwp",
  ".hwpx",
]);
const MAX_BYTES = 50 * 1024 * 1024;

type UploadItem = {
  id: string;
  file: File;
  title: string;
  /** 사용자가 자료명을 직접 고치면 true — AI 추천으로 덮어쓰지 않습니다. */
  titleTouched: boolean;
  titleStatus: "idle" | "loading" | "ready" | "error";
};
type MenuState = { docId: number; top: number; left: number } | null;
type UploadPhase = "sending" | "indexing" | "done";
type UploadProgress = {
  index: number;
  total: number;
  name: string;
  phase: UploadPhase;
  ratio: number;
};

/** 전송(바이트)은 앞 70%, 서버 추출·인덱싱은 뒤 30%로 배분합니다. */
const SEND_WEIGHT = 0.7;

function overallPercent(p: UploadProgress) {
  let fileFraction: number;
  if (p.phase === "done") {
    fileFraction = 1;
  } else if (p.phase === "indexing") {
    // ratio는 OCR 대기 중 소프트 크롤(0→1)용입니다.
    fileFraction = SEND_WEIGHT + (1 - SEND_WEIGHT) * Math.min(1, Math.max(0, p.ratio));
  } else {
    fileFraction = p.ratio * SEND_WEIGHT;
  }
  return Math.min(100, Math.round(((p.index + fileFraction) / p.total) * 100));
}

function phaseLabel(phase: UploadPhase) {
  if (phase === "sending") return "파일 전송 중";
  if (phase === "indexing") return "텍스트 추출·OCR·인덱싱 중";
  return "완료";
}

type DocTask = { docId: number; label: string; percent: number };

/**
 * 서버가 단계별 진행률을 주지 않으므로 완만히 차오르는 링으로 진행 중임을 알립니다.
 * 자리를 항상 차지해 작업 중에도 표 레이아웃이 밀리지 않습니다.
 */
function TaskRing({
  task,
  queued,
  queuePos,
  onCancel,
}: {
  task: DocTask | null;
  queued?: boolean;
  queuePos?: number;
  onCancel?: () => void;
}) {
  const radius = 8;
  const circumference = 2 * Math.PI * radius;
  const clamped = task ? Math.min(100, Math.max(0, task.percent)) : 0;
  const queueTitle = `재인덱싱 대기${queuePos ? ` ${queuePos}번째` : ""}${
    onCancel ? " · 클릭하면 취소" : ""
  }`;
  const title = task ? `${task.label} ${Math.round(clamped)}%` : queued ? queueTitle : undefined;

  if (!task && queued && onCancel) {
    return (
      <button
        type="button"
        onClick={onCancel}
        title={queueTitle}
        aria-label={queueTitle}
        className="group inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-rose-50 hover:text-rose-600"
      >
        <span className="text-[9px] font-bold leading-none group-hover:hidden">대기</span>
        <X className="hidden h-3 w-3 group-hover:block" aria-hidden />
      </button>
    );
  }

  return (
    <span
      className="inline-flex h-5 w-5 shrink-0 items-center justify-center"
      title={title}
      aria-label={title}
    >
      {task ? (
        <svg className="h-5 w-5 -rotate-90" viewBox="0 0 20 20" aria-hidden>
          <circle cx="10" cy="10" r={radius} fill="none" stroke="#dbe3f0" strokeWidth="2.5" />
          <circle
            cx="10"
            cy="10"
            r={radius}
            fill="none"
            stroke={task.percent >= 100 ? "#10b981" : "var(--ssu-blue)"}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - clamped / 100)}
            style={{ transition: "stroke-dashoffset 600ms var(--motion-ease)" }}
          />
        </svg>
      ) : queued ? (
        <span className="text-[9px] font-bold leading-none text-slate-400">대기</span>
      ) : null}
    </span>
  );
}

/** 두 곳(사이드바·확인 모달)에서 같은 두께·같은 위치로 보이도록 한 군데서 그립니다. */
function UploadProgressBar({ progress, done }: { progress: UploadProgress; done: boolean }) {
  const percent = overallPercent(progress);
  return (
    <div
      className="progress-track h-2 w-full"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div
        className={`progress-fill ${done ? "progress-fill-done" : ""}`}
        style={{ width: `${Math.max(percent, 4)}%` }}
      />
    </div>
  );
}

function UploadProgressHint({ phase }: { phase: UploadPhase }) {
  // 단계가 바뀔 때 안내문이 사라져 막대가 위로 튀지 않도록 자리는 항상 차지합니다.
  return (
    <p
      aria-hidden={phase !== "indexing"}
      className={`mt-1.5 text-[10px] leading-snug text-amber-700/80 transition-opacity duration-300 ${
        phase === "indexing" ? "opacity-100" : "opacity-0"
      }`}
    >
      스캔 PDF는 한국어 OCR → (빈약하면) CLOVA OCR → (그래도 빈약하면) GPT-4o Vision
      순으로 처리합니다. Vision 단계에서는 분당 토큰 한도에 걸리면 자동 재시도해
      완료까지 시간이 더 걸릴 수 있습니다.
    </p>
  );
}

function formatDateTyping(raw: string) {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

function statusClass(status: string) {
  if (status === "upload_error") return "bg-red-50 text-red-700";
  if (status === "needs_update") return "bg-orange-50 text-orange-700";
  if (status === "processing") return "bg-sky-50 text-sky-700";
  return "bg-emerald-50 text-emerald-700";
}

function titleFromFilename(name: string) {
  return name.replace(/\.[^.]+$/, "");
}

function isSupportedFile(file: File) {
  const ext = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  return SUPPORTED.has(ext);
}

function fileUrl(docId: number, download = false) {
  const q = download ? "?download=true" : "";
  return `${API_BASE_URL}/api/documents/${docId}/file${q}`;
}

function extOf(filename: string) {
  return `.${filename.split(".").pop()?.toLowerCase() ?? ""}`;
}

export default function Regulations() {
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]>("예산·행정 규정");
  const [data, setData] = useState<DocumentListResponse | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [syncing, setSyncing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [syncResult, setSyncResult] = useState<IngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [uploadCategory, setUploadCategory] = useState<(typeof tabs)[number]>("예산·행정 규정");
  const [version, setVersion] = useState("V1.0");
  const [appliedDate, setAppliedDate] = useState(todayKstDate);
  const [description, setDescription] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [categoryConfirmOpen, setCategoryConfirmOpen] = useState(false);
  const [progress, setProgress] = useState<UploadProgress | null>(null);

  const [menu, setMenu] = useState<MenuState>(null);
  const [metaDoc, setMetaDoc] = useState<UploadedDocument | null>(null);
  const [metaTitle, setMetaTitle] = useState("");
  const [metaCategory, setMetaCategory] = useState<(typeof tabs)[number]>("예산·행정 규정");
  const [metaVersion, setMetaVersion] = useState("V1.0");
  const [metaDate, setMetaDate] = useState("");
  const [metaDescription, setMetaDescription] = useState("");
  const [replaceDoc, setReplaceDoc] = useState<UploadedDocument | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [docTask, setDocTask] = useState<DocTask | null>(null);
  /** 재인덱싱 대기열(먼저 누른 순서). 맨 앞이 곧 처리되거나 처리 중일 수 있음 */
  const [reindexQueue, setReindexQueue] = useState<number[]>([]);

  const [previewDoc, setPreviewDoc] = useState<UploadedDocument | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const replaceInputRef = useRef<HTMLInputElement>(null);
  const datePickerRef = useRef<HTMLInputElement>(null);
  const metaDatePickerRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const progressTimer = useRef<number | null>(null);
  const docTaskTimer = useRef<number | null>(null);
  const reindexQueueRef = useRef<{ id: number; name: string }[]>([]);
  const reindexRunningRef = useRef(false);

  useEffect(
    () => () => {
      if (progressTimer.current) window.clearTimeout(progressTimer.current);
      if (docTaskTimer.current) window.clearTimeout(docTaskTimer.current);
    },
    [],
  );

  // 재인덱싱·파일 교체처럼 서버 작업이 도는 동안 링을 완만히 채웁니다.
  useEffect(() => {
    if (!docTask || docTask.percent >= 100) return;
    const timer = window.setInterval(() => {
      setDocTask((prev) =>
        prev && prev.percent < 94
          ? { ...prev, percent: Math.min(94, prev.percent + 1.6) }
          : prev,
      );
    }, 700);
    return () => window.clearInterval(timer);
  }, [docTask?.docId, docTask?.label, docTask?.percent === 100]);

  // OCR·인덱싱 대기 중에는 바가 멈춘 것처럼 보이지 않도록 살짝 앞으로 밀어 줍니다.
  useEffect(() => {
    if (!progress || progress.phase !== "indexing") return;
    const timer = window.setInterval(() => {
      setProgress((prev) => {
        if (!prev || prev.phase !== "indexing") return prev;
        const next = Math.min(0.98, prev.ratio + 0.012);
        if (next === prev.ratio) return prev;
        return { ...prev, ratio: next };
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [progress?.phase, progress?.index, progress?.name]);

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
    setError(null);
    loadDocs().catch((err: unknown) => {
      setData(null);
      setError(err instanceof Error ? err.message : "자료 목록을 불러오지 못했습니다.");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, page, pageSize]);

  useEffect(() => {
    if (!menu) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target)) return;
      setMenu(null);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(null);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  useEffect(() => {
    if (!previewDoc) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreviewDoc(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [previewDoc]);

  const counts = data?.counts ?? {
    total: 0,
    latest: 0,
    needs_update: 0,
    upload_error: 0,
    processing: 0,
  };
  const docs: UploadedDocument[] = data?.items ?? [];
  const totalPages = Math.max(1, Math.ceil((data?.total ?? 0) / pageSize));
  const selectedDoc = menu ? docs.find((d) => d.id === menu.docId) ?? null : null;
  const uploadFinished = !uploading && progress?.phase === "done";

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
        icon: Clock3,
        iconWrap: "bg-orange-50 text-orange-600",
      },
      {
        label: "업로드 오류",
        value: counts.upload_error ?? 0,
        icon: AlertTriangle,
        iconWrap: "bg-red-50 text-red-600",
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

  const pickFiles = (list: FileList | File[] | null) => {
    if (!list || list.length === 0) return;
    const next: UploadItem[] = [];
    const rejected: string[] = [];
    for (const file of Array.from(list)) {
      if (!isSupportedFile(file)) {
        rejected.push(`${file.name} (형식)`);
        continue;
      }
      if (file.size > MAX_BYTES) {
        rejected.push(`${file.name} (용량)`);
        continue;
      }
      next.push({
        id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 7)}`,
        file,
        title: titleFromFilename(file.name),
        titleTouched: false,
        titleStatus: "loading",
      });
    }
    if (next.length) {
      setUploadItems((prev) => [...prev, ...next]);
      setError(null);
      for (const item of next) {
        void suggestTitleForItem(item.id, item.file);
      }
    }
    if (rejected.length) {
      setError(
        `일부 파일을 건너뛰었습니다: ${rejected.slice(0, 3).join(", ")}${
          rejected.length > 3 ? " 외" : ""
        }`,
      );
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  /** 파일 앞부분만 서버에 보내 문서 제목을 추천받습니다. 사용자가 고친 제목은 덮지 않습니다. */
  const suggestTitleForItem = async (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiClient.post<{ title: string }>("/api/documents/suggest-title", form, {
        timeout: 20_000,
      });
      const suggested = (res.data.title || "").trim();
      if (!suggested) {
        setUploadItems((prev) =>
          prev.map((item) =>
            item.id === id ? { ...item, titleStatus: "error" as const } : item,
          ),
        );
        return;
      }
      setUploadItems((prev) =>
        prev.map((item) => {
          if (item.id !== id) return item;
          if (item.titleTouched) return { ...item, titleStatus: "ready" };
          return { ...item, title: suggested, titleStatus: "ready" };
        }),
      );
    } catch {
      setUploadItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, titleStatus: "error" as const } : item,
        ),
      );
    }
  };

  const updateItemTitle = (id: string, title: string) => {
    setUploadItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, title, titleTouched: true, titleStatus: "ready" } : item,
      ),
    );
  };

  const removeUploadItem = (id: string) => {
    setUploadItems((prev) => prev.filter((item) => item.id !== id));
  };

  const resetUploadForm = () => {
    setUploadItems([]);
    setVersion("V1.0");
    setAppliedDate(todayKstDate());
    setDescription("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  /** 백그라운드 작업이 끝날 때까지(status가 processing에서 벗어날 때까지) 폴링합니다. */
  const waitForDocReady = async (docId: number, timeoutMs = 20 * 60 * 1000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 2500));
      try {
        const res = await apiClient.get<UploadedDocument>(`/api/documents/${docId}`);
        if (res.data.status !== "processing") return res.data;
      } catch {
        // 일시적인 네트워크 오류는 무시하고 다음 주기에 다시 확인합니다.
      }
    }
    return null;
  };

  const uploadOne = async (item: UploadItem, index: number, total: number) => {
    const form = new FormData();
    form.append("file", item.file);
    form.append("title", item.title.trim() || titleFromFilename(item.file.name));
    form.append("category", uploadCategory);
    form.append("version", version.trim() || "V1.0");
    form.append(
      "applied_date",
      /^\d{4}-\d{2}-\d{2}$/.test(appliedDate) ? appliedDate : todayKstDate(),
    );
    if (description.trim()) form.append("description", description.trim());

    const base = { index, total, name: item.title.trim() || item.file.name };
    setProgress({ ...base, phase: "sending", ratio: 0 });
    // 전송이 매우 빨리 끝나면 onUploadProgress가 indexing으로 안 바뀌는 경우가 있어
    // 요청 직후 인덱싱 단계로 전환할 타이머를 둡니다.
    const toIndexing = window.setTimeout(() => {
      setProgress((prev) =>
        prev && prev.index === index && prev.phase === "sending"
          ? { ...prev, phase: "indexing", ratio: 0 }
          : prev,
      );
    }, 1200);
    try {
      // 서버는 파일 저장까지만 처리하고 바로 응답합니다. 추출·인덱싱은 status로 확인합니다.
      const res = await apiClient.post<UploadedDocument>("/api/documents/upload", form, {
        timeout: 10 * 60 * 1000,
        onUploadProgress: (event) => {
          const totalBytes = event.total ?? item.file.size;
          const ratio = totalBytes ? Math.min(1, event.loaded / totalBytes) : 0;
          setProgress({
            ...base,
            phase: ratio >= 1 ? "indexing" : "sending",
            ratio: ratio >= 1 ? 0 : ratio,
          });
        },
      });
      setProgress({ ...base, phase: "indexing", ratio: 0 });
      const finished = await waitForDocReady(res.data.id);
      setProgress({ ...base, phase: "done", ratio: 1 });
      return { doc: finished ?? res.data, replaced: res.data.replaced, timedOut: !finished };
    } finally {
      window.clearTimeout(toIndexing);
    }
  };

  const runUpload = async () => {
    if (uploadItems.length === 0) {
      setError("업로드할 파일을 선택하세요.");
      return;
    }
    if (uploadItems.some((item) => !item.title.trim())) {
      setError("모든 자료명을 입력하세요.");
      return;
    }
    if (!version.trim()) {
      setError("버전을 입력하세요.");
      return;
    }

    setUploading(true);
    setError(null);
    setNotice(null);
    const failed: string[] = [];
    const warned: string[] = [];
    const overwritten: string[] = [];
    let ok = 0;
    try {
      for (const [index, item] of uploadItems.entries()) {
        try {
          const { doc, replaced, timedOut } = await uploadOne(item, index, uploadItems.length);
          const name = titleFromFilename(doc.filename);
          if (timedOut) {
            failed.push(`${name}: 처리가 지연되고 있습니다. 잠시 후 상태를 확인해 주세요.`);
            continue;
          }
          if (doc.status === "upload_error") {
            failed.push(`${name}: 텍스트 추출·인덱싱에 실패했습니다.`);
            continue;
          }
          ok += 1;
          if (replaced) overwritten.push(`${name} → ${doc.version}`);
          if (doc.status === "needs_update") {
            warned.push(`${name}: OCR 품질이 낮아 AI 정리 결과로 인덱싱했습니다. 내용을 확인해 주세요.`);
          }
        } catch (err: any) {
          failed.push(
            `${item.file.name}: ${err?.response?.data?.detail ?? err?.message ?? "실패"}`,
          );
        }
      }
      if (ok > 0) {
        const overwriteNote = overwritten.length
          ? ` · 동일 자료명 덮어쓰기 ${overwritten.slice(0, 2).join(", ")}${
              overwritten.length > 2 ? " 외" : ""
            }`
          : "";
        setNotice(
          `${ok}건 업로드 완료${failed.length ? ` · 실패 ${failed.length}건` : ""}${overwriteNote}`,
        );
        resetUploadForm();
        setActiveTab(uploadCategory);
        setPage(1);
        await loadDocs({ category: uploadCategory, page: 1 });
      }
      const problems = [...failed, ...warned];
      if (problems.length) {
        setError(problems.slice(0, 3).join(" / "));
      }
    } finally {
      setUploading(false);
      // 완료 바는 진행 중이던 자리에서 그대로 보여주고,
      // 확인 모달을 쓴 경우에도 완료를 띄운 뒤에 함께 닫습니다.
      if (progressTimer.current) window.clearTimeout(progressTimer.current);
      progressTimer.current = window.setTimeout(() => {
        setProgress(null);
        setCategoryConfirmOpen(false);
      }, 1100);
    }
  };

  /** 확인 모달을 닫으면서 남아 있는 완료 표시도 같이 정리합니다. */
  const closeUploadConfirm = () => {
    if (progressTimer.current) window.clearTimeout(progressTimer.current);
    setCategoryConfirmOpen(false);
    setProgress(null);
  };

  const handleUploadClick = () => {
    if (uploadItems.length > 1) {
      setCategoryConfirmOpen(true);
      return;
    }
    void runUpload();
  };

  const openMenu = (doc: UploadedDocument, button: HTMLButtonElement) => {
    const rect = button.getBoundingClientRect();
    const width = 188;
    const left = Math.min(window.innerWidth - width - 8, Math.max(8, rect.right - width));
    const top = Math.min(window.innerHeight - 260, rect.bottom + 4);
    setMenu({ docId: doc.id, top, left });
  };

  const openPreview = async (doc: UploadedDocument) => {
    setMenu(null);
    setPreviewDoc(doc);
    setPreviewText(null);
    setPreviewError(null);
    if (![".txt", ".md"].includes(extOf(doc.filename))) return;
    setPreviewLoading(true);
    try {
      const res = await apiClient.get<string>(`/api/documents/${doc.id}/file`, {
        responseType: "text",
        transformResponse: [(value) => value],
      });
      setPreviewText(typeof res.data === "string" ? res.data : String(res.data));
    } catch (err: any) {
      setPreviewError(err?.response?.data?.detail ?? "미리보기를 불러오지 못했습니다.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const openMetaEditor = (doc: UploadedDocument) => {
    setMetaDoc(doc);
    setMetaTitle(titleFromFilename(doc.filename));
    setMetaCategory(
      (tabs.includes(doc.category as (typeof tabs)[number])
        ? doc.category
        : "예산·행정 규정") as (typeof tabs)[number],
    );
    setMetaVersion(doc.version || "V1.0");
    setMetaDate(
      doc.applied_date ? formatKstDate(doc.applied_date, todayKstDate(), "-") : todayKstDate(),
    );
    setMetaDescription(doc.description || "");
    setMenu(null);
  };

  const saveMeta = async () => {
    if (!metaDoc) return;
    if (!metaTitle.trim()) {
      setError("자료명을 입력하세요.");
      return;
    }
    setActionBusy(true);
    setError(null);
    try {
      await apiClient.patch(`/api/documents/${metaDoc.id}`, {
        title: metaTitle.trim(),
        category: metaCategory,
        version: metaVersion.trim() || "V1.0",
        description: metaDescription,
        applied_date: /^\d{4}-\d{2}-\d{2}$/.test(metaDate) ? metaDate : todayKstDate(),
      });
      setMetaDoc(null);
      setNotice("자료 정보가 수정되었습니다.");
      if (metaCategory !== activeTab) {
        setActiveTab(metaCategory);
        setPage(1);
        await loadDocs({ category: metaCategory, page: 1 });
      } else {
        await loadDocs();
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "수정에 실패했습니다.");
    } finally {
      setActionBusy(false);
    }
  };

  const deleteDoc = async (doc: UploadedDocument) => {
    if (!window.confirm(`「${doc.filename}」을(를) 삭제할까요?`)) return;
    setMenu(null);
    setActionBusy(true);
    setError(null);
    try {
      await apiClient.delete(`/api/documents/${doc.id}`);
      setNotice("자료를 삭제했습니다.");
      await loadDocs();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "삭제에 실패했습니다.");
    } finally {
      setActionBusy(false);
    }
  };

  const reindexDoc = (doc: UploadedDocument) => {
    setMenu(null);
    setError(null);

    const alreadyQueued = reindexQueueRef.current.some((item) => item.id === doc.id);
    if (alreadyQueued || doc.status === "processing") {
      setNotice("이미 재인덱싱 대기열이거나 처리 중입니다.");
      return;
    }

    reindexQueueRef.current = [
      ...reindexQueueRef.current,
      { id: doc.id, name: doc.filename },
    ];
    setReindexQueue(reindexQueueRef.current.map((item) => item.id));
    const total = reindexQueueRef.current.length;
    setNotice(
      total === 1
        ? "재인덱싱을 시작했습니다."
        : `재인덱싱 대기열에 추가했습니다. (대기 ${total}건 · 누른 순서대로 처리)`,
    );
    void pumpReindexQueue();
  };

  /** 아직 시작하지 않은 대기 항목만 큐에서 뺍니다. 처리 중인 항목은 취소 불가. */
  const cancelQueuedReindex = (docId: number) => {
    setMenu(null);
    const queue = reindexQueueRef.current;
    const index = queue.findIndex((item) => item.id === docId);
    if (index < 0) return;
    if (index === 0 && reindexRunningRef.current) {
      setNotice("이미 처리 중인 항목은 취소할 수 없습니다.");
      return;
    }
    const removed = queue[index];
    reindexQueueRef.current = queue.filter((_, i) => i !== index);
    setReindexQueue(reindexQueueRef.current.map((item) => item.id));
    setNotice(`「${titleFromFilename(removed.name)}」 재인덱싱 대기를 취소했습니다.`);
  };

  const pumpReindexQueue = async () => {
    if (reindexRunningRef.current) return;
    reindexRunningRef.current = true;
    let okCount = 0;
    let failCount = 0;

    try {
      while (reindexQueueRef.current.length > 0) {
        const next = reindexQueueRef.current[0];
        const remaining = reindexQueueRef.current.length;
        const done = okCount + failCount;
        setReindexQueue(reindexQueueRef.current.map((item) => item.id));
        setDocTask({ docId: next.id, label: "재인덱싱 중", percent: 8 });
        setNotice(
          remaining + done > 1
            ? `재인덱싱 진행 중 ${done + 1}번째 (남은 대기 ${Math.max(0, remaining - 1)}건)`
            : `「${titleFromFilename(next.name)}」 재인덱싱 중…`,
        );

        try {
          await apiClient.post(`/api/documents/${next.id}/reindex`);
          await loadDocs();
          const finished = await waitForDocReady(next.id);
          if (!finished) {
            failCount += 1;
            setError(
              `${titleFromFilename(next.name)}: 재인덱싱이 지연되고 있습니다. 잠시 후 상태를 확인해 주세요.`,
            );
          } else if (finished.status === "upload_error") {
            failCount += 1;
            setError(`${finished.filename}: 재인덱싱에 실패했습니다. 원본 파일을 확인해 주세요.`);
          } else if (finished.status === "needs_update") {
            okCount += 1;
            setError(
              `${finished.filename}: OCR 품질이 낮아 AI 정리 결과로 인덱싱했습니다. 내용을 확인해 주세요.`,
            );
          } else {
            okCount += 1;
          }
          setDocTask({ docId: next.id, label: "완료", percent: 100 });
          await loadDocs();
          await new Promise((resolve) => window.setTimeout(resolve, 450));
        } catch (err: any) {
          failCount += 1;
          setDocTask(null);
          setError(
            `${titleFromFilename(next.name)}: ${
              err?.response?.data?.detail ?? err?.message ?? "재인덱싱에 실패했습니다."
            }`,
          );
          await loadDocs();
        }

        reindexQueueRef.current = reindexQueueRef.current.slice(1);
        setReindexQueue(reindexQueueRef.current.map((item) => item.id));
      }

      if (okCount + failCount > 1) {
        setNotice(
          `재인덱싱 큐 완료 · 성공 ${okCount}건${failCount ? ` · 실패 ${failCount}건` : ""}`,
        );
      } else if (okCount === 1 && failCount === 0) {
        setNotice("재인덱싱이 완료되었습니다.");
      }
    } finally {
      reindexRunningRef.current = false;
      setReindexQueue(reindexQueueRef.current.map((item) => item.id));
      if (docTaskTimer.current) window.clearTimeout(docTaskTimer.current);
      docTaskTimer.current = window.setTimeout(() => setDocTask(null), 1200);
      if (reindexQueueRef.current.length > 0) {
        void pumpReindexQueue();
      }
    }
  };

  const setDocStatus = async (doc: UploadedDocument, status: RegulationStatus) => {
    setMenu(null);
    setError(null);
    try {
      await apiClient.patch(`/api/documents/${doc.id}`, { status });
      setNotice(
        status === "needs_update"
          ? "「업데이트 필요」로 표시했습니다."
          : "「최신 적용」으로 표시했습니다.",
      );
      await loadDocs();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "상태 변경에 실패했습니다.");
    }
  };

  const replaceFile = async (file: File | null) => {
    if (!replaceDoc || !file) return;
    if (!isSupportedFile(file)) {
      setError("지원하지 않는 형식입니다.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("파일 용량은 50MB 이하여야 합니다.");
      return;
    }
    setError(null);
    setNotice(null);
    setDocTask({ docId: replaceDoc.id, label: "파일 교체 중", percent: 8 });
    const targetId = replaceDoc.id;
    setReplaceDoc(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("title", titleFromFilename(file.name));
      await apiClient.post(`/api/documents/${targetId}/replace`, form, {
        timeout: 10 * 60 * 1000,
      });
      await loadDocs();
      const finished = await waitForDocReady(targetId);
      if (!finished) {
        setDocTask(null);
        setError("파일 교체 처리가 지연되고 있습니다. 잠시 후 상태를 확인해 주세요.");
        await loadDocs();
        return;
      }
      setDocTask({ docId: targetId, label: "완료", percent: 100 });
      if (finished.status === "upload_error") {
        setError(`${finished.filename}: 파일 교체 후 인덱싱에 실패했습니다.`);
      } else if (finished.status === "needs_update") {
        setError(
          `${finished.filename}: OCR 품질이 낮아 AI 정리 결과로 인덱싱했습니다. 내용을 확인해 주세요.`,
        );
      } else {
        setNotice("파일이 업데이트되었습니다.");
      }
      await loadDocs();
    } catch (err: any) {
      setDocTask(null);
      setError(err?.response?.data?.detail ?? "파일 업데이트에 실패했습니다.");
      await loadDocs();
    } finally {
      if (replaceInputRef.current) replaceInputRef.current.value = "";
      if (docTaskTimer.current) window.clearTimeout(docTaskTimer.current);
      docTaskTimer.current = window.setTimeout(() => setDocTask(null), 1200);
    }
  };

  return (
    <div className="mx-auto flex h-full max-w-[1400px] gap-4 px-6 py-6 phone:h-auto phone:flex-col phone:px-4 phone:py-4">
      <div className="min-w-0 flex-1">
        <div className="mb-5 flex items-start justify-between gap-3 phone:flex-col">
          <div>
            <h1 className="text-[24px] font-bold text-slate-900 phone:text-[20px]">규정·자료 관리</h1>
            <p className="mt-1 text-[13px] text-slate-500">
              모집요강·회의록·재무현황·행정 규정을 등록하고 AI가 참고할 수 있도록 인덱싱합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={syncDataFolder}
            disabled={syncing}
            className="ui-pressable inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-navy)] px-3 py-2 text-[13px] font-semibold text-white disabled:opacity-50 phone:w-full phone:justify-center"
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

        <div className="mb-3 flex gap-4 overflow-x-auto border-b border-slate-200 text-[13px]">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => {
                setActiveTab(tab);
                setPage(1);
              }}
              className={`ui-pressable shrink-0 pb-2 font-semibold ${
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
        {notice && <p className="mb-3 text-[13px] text-emerald-600">{notice}</p>}
        {error && <p className="mb-3 text-[13px] text-red-500">{error}</p>}

        <div className="ui-surface overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-[13px] phone:min-w-[480px]">
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
                      {formatKstDate(doc.updated_at ?? doc.created_at)}
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${statusClass(doc.status)}`}
                      >
                        {doc.status_label}
                      </span>
                    </td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center justify-end gap-1.5">
                        {(() => {
                          const queuePos = reindexQueue.indexOf(doc.id);
                          const isActive = docTask?.docId === doc.id;
                          const isQueued = queuePos >= 0 && !isActive;
                          return (
                            <TaskRing
                              task={isActive ? docTask : null}
                              queued={isQueued}
                              queuePos={isQueued ? queuePos : undefined}
                              onCancel={
                                isQueued ? () => cancelQueuedReindex(doc.id) : undefined
                              }
                            />
                          );
                        })()}
                        <button
                          type="button"
                          onClick={(e) => openMenu(doc, e.currentTarget)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                          aria-label="관리"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </div>
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
          </div>

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

      <aside className="ui-surface w-[320px] shrink-0 self-start rounded-xl border border-[var(--ssu-border)] bg-white p-4 phone:w-full">
        <p className="text-[14px] font-bold text-slate-900">자료 업로드</p>
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pickFiles(e.dataTransfer.files);
          }}
          className={`mt-3 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-8 text-center ${
            dragOver
              ? "border-[var(--ssu-blue)] bg-blue-50"
              : "border-slate-300 bg-slate-50 hover:border-[var(--ssu-blue)]"
          }`}
        >
          <UploadCloud className="mb-2 h-7 w-7 text-[var(--ssu-blue)]" />
          <p className="text-[12px] font-medium text-slate-700">
            파일을 드래그하여 놓거나 파일 선택
          </p>
          <p className="mt-1 text-[11px] text-slate-400">여러 개 선택·드래그 가능</p>
          <p className="text-[11px] text-slate-400">지원 형식: PDF, DOCX, XLSX, HWP, HWPX</p>
          <p className="text-[11px] text-slate-400">HWP는 업로드 시 PDF로 변환해 인덱싱합니다</p>
          <p className="text-[11px] text-slate-400">최대 용량: 50MB</p>
          {uploadItems.length > 0 && (
            <p className="mt-2 text-[11px] font-medium text-[var(--ssu-blue)]">
              {uploadItems.length}개 선택됨
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => pickFiles(e.target.files)}
          />
        </div>

        <div className="mt-4 space-y-3 text-[12px]">
          <div>
            <label className="mb-1 block font-medium text-slate-600">
              자료명 <span className="text-red-500">*</span>
            </label>
            {uploadItems.length === 0 ? (
              <input
                disabled
                value=""
                className="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-slate-400 outline-none"
                placeholder="파일을 선택하면 자동으로 채워집니다"
              />
            ) : uploadItems.length === 1 ? (
              <div>
                <input
                  value={uploadItems[0].title}
                  onChange={(e) => updateItemTitle(uploadItems[0].id, e.target.value)}
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
                  placeholder="자료명을 입력하세요"
                />
                <p className="mt-1 text-[10px] text-slate-400">
                  {uploadItems[0].titleStatus === "loading"
                    ? "문서 제목을 파악하는 중…"
                    : uploadItems[0].titleTouched
                      ? "직접 수정한 자료명입니다."
                      : "본문에서 찾은 제목을 넣었습니다. 필요하면 수정하세요."}
                </p>
              </div>
            ) : (
              <div className="max-h-44 space-y-2 overflow-y-auto rounded-lg border border-slate-200 p-2">
                {uploadItems.map((item) => (
                  <div key={item.id} className="rounded-md bg-slate-50 p-2">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <p className="truncate text-[10px] text-slate-400">
                        {item.file.name}
                        {item.titleStatus === "loading" ? " · 제목 파악 중" : ""}
                      </p>
                      <button
                        type="button"
                        onClick={() => removeUploadItem(item.id)}
                        className="rounded p-0.5 text-slate-400 hover:bg-white hover:text-red-500"
                        aria-label="선택 해제"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                    <input
                      value={item.title}
                      onChange={(e) => updateItemTitle(item.id, e.target.value)}
                      className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 outline-none focus:border-[var(--ssu-blue)]"
                      placeholder="자료명"
                    />
                  </div>
                ))}
              </div>
            )}
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
            {uploadItems.length > 1 && (
              <p className="mt-1 text-[10px] text-slate-400">선택한 모든 파일에 동일하게 적용됩니다.</p>
            )}
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
            {uploadItems.length > 1 && (
              <p className="mt-1 text-[10px] text-slate-400">선택한 모든 파일에 동일하게 적용됩니다.</p>
            )}
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
          {progress && !categoryConfirmOpen && (
            <div className="soft-fade-in rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2.5">
              <div className="flex items-end justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-semibold text-slate-700">
                    {progress.total > 1 && (
                      <span className="mr-1 text-slate-400">
                        {Math.min(progress.index + 1, progress.total)}/{progress.total}
                      </span>
                    )}
                    {progress.name}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {phaseLabel(progress.phase)}
                  </p>
                </div>
                <span className="shrink-0 text-[13px] font-bold tabular-nums text-slate-700">
                  {overallPercent(progress)}%
                </span>
              </div>
              <div className="mt-2">
                <UploadProgressBar progress={progress} done={uploadFinished} />
              </div>
              <UploadProgressHint phase={progress.phase} />
            </div>
          )}
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={uploading || uploadItems.length === 0}
            className="ui-pressable w-full rounded-lg bg-[var(--ssu-blue)] py-2.5 text-[13px] font-semibold text-white disabled:opacity-50"
          >
            {uploading
              ? "업로드 중…"
              : uploadItems.length > 1
                ? `${uploadItems.length}개 업로드`
                : "업로드"}
          </button>
        </div>
      </aside>

      {menu && selectedDoc &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed z-[1100] w-[188px] overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-xl"
            style={{ top: menu.top, left: menu.left }}
          >
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
              onClick={() => void openPreview(selectedDoc)}
            >
              <Eye className="h-3.5 w-3.5" /> 미리보기
            </button>
            <a
              href={fileUrl(selectedDoc.id, true)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
              onClick={() => setMenu(null)}
            >
              <Download className="h-3.5 w-3.5" /> 다운로드
            </a>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
              onClick={() => openMetaEditor(selectedDoc)}
            >
              <Pencil className="h-3.5 w-3.5" /> 정보 수정
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
              onClick={() => {
                setReplaceDoc(selectedDoc);
                setMenu(null);
                window.setTimeout(() => replaceInputRef.current?.click(), 0);
              }}
            >
              <Replace className="h-3.5 w-3.5" /> 파일 업데이트
            </button>
            {reindexQueue.includes(selectedDoc.id) && docTask?.docId !== selectedDoc.id ? (
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
                onClick={() => cancelQueuedReindex(selectedDoc.id)}
              >
                <X className="h-3.5 w-3.5" /> 재인덱싱 대기 취소
              </button>
            ) : (
              <button
                type="button"
                disabled={
                  selectedDoc.status === "processing" || reindexQueue.includes(selectedDoc.id)
                }
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                onClick={() => reindexDoc(selectedDoc)}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {reindexQueue.includes(selectedDoc.id)
                  ? "재인덱싱 중"
                  : selectedDoc.status === "processing"
                    ? "재인덱싱 중"
                    : "재인덱싱"}
              </button>
            )}
            {selectedDoc.status === "needs_update" ? (
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50"
                onClick={() => void setDocStatus(selectedDoc, "latest")}
              >
                <CheckCircle2 className="h-3.5 w-3.5" /> 최신 적용으로 표시
              </button>
            ) : (
              <button
                type="button"
                disabled={selectedDoc.status === "processing"}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                onClick={() => void setDocStatus(selectedDoc, "needs_update")}
              >
                <AlertTriangle className="h-3.5 w-3.5" /> 업데이트 필요로 표시
              </button>
            )}
            <div className="my-1 border-t border-slate-100" />
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] text-red-600 hover:bg-red-50"
              onClick={() => void deleteDoc(selectedDoc)}
            >
              <Trash2 className="h-3.5 w-3.5" /> 삭제
            </button>
          </div>,
          document.body,
        )}

      <input
        ref={replaceInputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          void replaceFile(file);
        }}
      />

      {previewDoc &&
        createPortal(
          <div
            className="fixed inset-0 z-[1200] flex items-center justify-center bg-slate-900/50 p-6 phone:p-3"
            onClick={() => setPreviewDoc(null)}
          >
            <div
              className="flex h-[85vh] w-full max-w-[900px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="truncate text-[14px] font-bold text-slate-900">
                    {previewDoc.filename}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {previewDoc.category} · {previewDoc.version} ·{" "}
                    {formatKstDate(previewDoc.updated_at ?? previewDoc.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <a
                    href={fileUrl(previewDoc.id, true)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    aria-label="다운로드"
                  >
                    <Download className="h-4 w-4" />
                  </a>
                  <button
                    type="button"
                    onClick={() => setPreviewDoc(null)}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    aria-label="닫기"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="min-h-0 flex-1 bg-slate-50">
                {previewError ? (
                  <div className="flex h-full items-center justify-center px-6 text-center text-[13px] text-red-500">
                    {previewError}
                  </div>
                ) : extOf(previewDoc.filename) === ".pdf" ? (
                  <iframe
                    src={fileUrl(previewDoc.id)}
                    title={previewDoc.filename}
                    className="h-full w-full border-0"
                  />
                ) : [".txt", ".md"].includes(extOf(previewDoc.filename)) ? (
                  <div className="h-full overflow-auto px-5 py-4">
                    {previewLoading ? (
                      <p className="text-[13px] text-slate-500">불러오는 중…</p>
                    ) : (
                      <pre className="whitespace-pre-wrap break-words font-sans text-[13px] leading-relaxed text-slate-700">
                        {previewText || "내용이 비어 있습니다."}
                      </pre>
                    )}
                  </div>
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
                    <FileText className="h-9 w-9 text-slate-300" />
                    <p className="text-[13px] font-semibold text-slate-600">
                      이 형식은 화면에서 바로 볼 수 없습니다.
                    </p>
                    {previewDoc.summary && (
                      <p className="max-h-40 max-w-[520px] overflow-auto text-[12px] leading-relaxed text-slate-500">
                        {previewDoc.summary}
                      </p>
                    )}
                    <a
                      href={fileUrl(previewDoc.id, true)}
                      className="mt-1 inline-flex items-center gap-1.5 rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white"
                    >
                      <Download className="h-4 w-4" />
                      다운로드하여 열기
                    </a>
                  </div>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}

      {categoryConfirmOpen &&
        createPortal(
          <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-slate-900/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
              <p className="text-[15px] font-bold text-slate-900">
                {uploadFinished ? "업로드 완료" : "카테고리 확인"}
              </p>
              {/* 확인 → 완료로 바뀔 때 창 높이가 변해 막대가 튀지 않도록 자리를 맞춥니다. */}
              <div className="mt-2 min-h-[84px]">
                {uploadFinished ? (
                  <>
                    <p className="text-[13px] leading-relaxed text-slate-600">
                      <span className="font-semibold text-[var(--ssu-blue)]">
                        「{uploadCategory}」
                      </span>
                      카테고리에 {progress?.total ?? 0}개 파일 처리를 마쳤습니다.
                    </p>
                    <p className="mt-2 text-[12px] text-slate-500">
                      결과와 실패 건은 목록 위 알림에서 확인할 수 있습니다.
                    </p>
                  </>
                ) : (
                  <>
                    <p className="text-[13px] leading-relaxed text-slate-600">
                      선택한{" "}
                      <span className="font-semibold text-slate-900">{uploadItems.length}개</span>{" "}
                      파일을 모두{" "}
                      <span className="font-semibold text-[var(--ssu-blue)]">
                        「{uploadCategory}」
                      </span>
                      카테고리로 업로드할까요?
                    </p>
                    <p className="mt-2 text-[12px] text-slate-500">
                      버전({version || "V1.0"})과 적용일자(
                      {/^\d{4}-\d{2}-\d{2}$/.test(appliedDate) ? appliedDate : todayKstDate()})는
                      모든 파일에 동일하게 적용됩니다.
                    </p>
                  </>
                )}
              </div>
              <div className="mt-5 flex justify-end gap-2">
                {uploadFinished ? (
                  <button
                    type="button"
                    onClick={closeUploadConfirm}
                    className="rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white"
                  >
                    닫기
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={uploading}
                      onClick={closeUploadConfirm}
                      className="rounded-lg border border-slate-200 px-4 py-2 text-[13px] font-semibold text-slate-600"
                    >
                      취소
                    </button>
                    <button
                      type="button"
                      disabled={uploading}
                      onClick={() => void runUpload()}
                      className="rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-50"
                    >
                      {uploading ? "업로드 중…" : "맞습니다, 업로드"}
                    </button>
                  </>
                )}
              </div>
              {progress && (
                <div className="soft-fade-in mt-4">
                  <div className="mb-1.5 flex items-baseline justify-between gap-2">
                    <p className="truncate text-[12px] text-slate-500">
                      <span className="mr-1 font-semibold text-slate-700">
                        {Math.min(progress.index + 1, progress.total)}/{progress.total}
                      </span>
                      {progress.name} · {phaseLabel(progress.phase)}
                    </p>
                    <span className="shrink-0 text-[12px] font-bold tabular-nums text-slate-700">
                      {overallPercent(progress)}%
                    </span>
                  </div>
                  <UploadProgressBar progress={progress} done={uploadFinished} />
                  <UploadProgressHint phase={progress.phase} />
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}

      {metaDoc &&
        createPortal(
          <div className="fixed inset-0 z-[1200] flex items-center justify-center bg-slate-900/40 p-4">
            <div className="w-full max-w-md rounded-2xl bg-white p-5 shadow-xl">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <p className="text-[15px] font-bold text-slate-900">자료 정보 수정</p>
                  <p className="mt-1 text-[12px] text-slate-500">{metaDoc.filename}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setMetaDoc(null)}
                  className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-3 text-[12px]">
                <div>
                  <label className="mb-1 block font-medium text-slate-600">자료명</label>
                  <input
                    value={metaTitle}
                    onChange={(e) => setMetaTitle(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
                  />
                </div>
                <div>
                  <label className="mb-1 block font-medium text-slate-600">카테고리</label>
                  <select
                    value={metaCategory}
                    onChange={(e) => setMetaCategory(e.target.value as (typeof tabs)[number])}
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
                  <label className="mb-1 block font-medium text-slate-600">버전</label>
                  <input
                    value={metaVersion}
                    onChange={(e) => setMetaVersion(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
                  />
                </div>
                <div>
                  <label className="mb-1 block font-medium text-slate-600">적용일자</label>
                  <div className="relative">
                    <input
                      type="text"
                      inputMode="numeric"
                      value={metaDate}
                      onChange={(e) => setMetaDate(formatDateTyping(e.target.value))}
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 pr-10 outline-none focus:border-[var(--ssu-blue)]"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const el = metaDatePickerRef.current;
                        if (!el) return;
                        try {
                          el.showPicker();
                        } catch {
                          el.click();
                        }
                      }}
                      className="absolute right-2 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100"
                    >
                      <Calendar className="h-4 w-4" />
                    </button>
                    <input
                      ref={metaDatePickerRef}
                      type="date"
                      tabIndex={-1}
                      value={/^\d{4}-\d{2}-\d{2}$/.test(metaDate) ? metaDate : ""}
                      onChange={(e) => setMetaDate(e.target.value)}
                      className="pointer-events-none absolute h-0 w-0 opacity-0"
                      aria-hidden
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block font-medium text-slate-600">설명</label>
                  <textarea
                    value={metaDescription}
                    onChange={(e) => setMetaDescription(e.target.value)}
                    rows={3}
                    className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 outline-none focus:border-[var(--ssu-blue)]"
                  />
                </div>
              </div>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => setMetaDoc(null)}
                  className="rounded-lg border border-slate-200 px-4 py-2 text-[13px] font-semibold text-slate-600"
                >
                  취소
                </button>
                <button
                  type="button"
                  disabled={actionBusy}
                  onClick={() => void saveMeta()}
                  className="rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-50"
                >
                  {actionBusy ? "저장 중…" : "저장"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
