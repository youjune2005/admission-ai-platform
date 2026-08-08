import { useEffect, useRef, useState } from "react";
import { UploadCloud, FileText, RefreshCw, FolderSync } from "lucide-react";
import { apiClient } from "../api/client";
import Markdown from "../components/Markdown";
import type { IngestResult, UploadedDocument } from "../types";

export default function Documents() {
  const [docs, setDocs] = useState<UploadedDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<IngestResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocs = async () => {
    const res = await apiClient.get<UploadedDocument[]>("/api/documents");
    setDocs(res.data);
  };

  useEffect(() => {
    loadDocs();
  }, []);

  const handleFile = async (file: File) => {
    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await apiClient.post("/api/documents/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await loadDocs();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "업로드 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const syncDataFolder = async () => {
    setSyncing(true);
    setError(null);
    setSyncResult(null);
    try {
      const res = await apiClient.post<IngestResult>("/api/documents/ingest-data-folder");
      setSyncResult(res.data);
      await loadDocs();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "data/ 폴더 동기화 중 오류가 발생했습니다.");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">서류 검토</h1>
          <p className="mt-1 text-sm text-slate-500">
            지원 서류(PDF, 텍스트 등)를 업로드하면 AI가 핵심 내용과 확인 필요 항목을 요약하고,
            AI 상담 챗봇이 참고할 수 있도록 자동으로 인덱싱합니다.
          </p>
        </div>
        <button
          onClick={syncDataFolder}
          disabled={syncing}
          className="flex shrink-0 items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <FolderSync className="h-4 w-4" />}
          data/ 폴더 동기화
        </button>
      </div>

      {syncResult && (
        <div className="mt-3 rounded-lg bg-slate-50 px-4 py-2 text-xs text-slate-600 ring-1 ring-slate-200">
          새로 추가됨 {syncResult.ingested.length}건
          {syncResult.ingested.length > 0 && `: ${syncResult.ingested.join(", ")}`}
          {syncResult.skipped.length > 0 && ` · 이미 처리됨 ${syncResult.skipped.length}건`}
          {syncResult.failed.length > 0 && ` · 실패 ${syncResult.failed.length}건: ${syncResult.failed.join(", ")}`}
        </div>
      )}

      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          const file = e.dataTransfer.files?.[0];
          if (file) handleFile(file);
        }}
        className="mt-6 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-white py-12 text-center hover:border-indigo-400"
      >
        <UploadCloud className="mb-3 h-8 w-8 text-slate-400" />
        <p className="text-sm font-medium text-slate-700">클릭하거나 파일을 드래그해 업로드하세요</p>
        <p className="mt-1 text-xs text-slate-400">PDF, TXT 등 지원</p>
        <input ref={fileInputRef} type="file" className="hidden" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
      </div>

      {loading && <p className="mt-4 text-sm text-slate-400">업로드 및 분석 중입니다…</p>}
      {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

      <div className="mt-8 space-y-4">
        {docs.map((d) => (
          <div key={d.id} className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <div className="mb-2 flex items-center gap-2">
              <FileText className="h-4 w-4 text-indigo-600" />
              <p className="text-sm font-semibold text-slate-900">{d.filename}</p>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{d.doc_type}</span>
              {d.source === "data_folder" && (
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-600">data/ 폴더</span>
              )}
            </div>
            {d.summary ? (
              <Markdown content={d.summary} />
            ) : (
              <p className="text-sm text-slate-400">요약을 생성할 수 없는 파일 형식입니다.</p>
            )}
          </div>
        ))}
        {docs.length === 0 && <p className="text-sm text-slate-400">업로드된 서류가 없습니다.</p>}
      </div>
    </div>
  );
}
