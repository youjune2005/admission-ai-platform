import { useRef, useState } from "react";
import { UploadCloud, FileSpreadsheet, Sparkles } from "lucide-react";
import { apiClient } from "../api/client";
import Markdown from "../components/Markdown";
import type { AnalyticsResult } from "../types";

export default function Analytics() {
  const [result, setResult] = useState<AnalyticsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setLoading(true);
    setError(null);
    setResult(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await apiClient.post<AnalyticsResult>("/api/analytics/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResult(res.data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "분석 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <h1 className="text-2xl font-semibold text-slate-900">데이터 분석</h1>
      <p className="mt-1 text-sm text-slate-500">
        입시 관련 CSV/Excel 데이터를 업로드하면 통계 요약과 AI 인사이트를 제공합니다.
      </p>

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
        <p className="mt-1 text-xs text-slate-400">CSV, XLSX, XLS 지원</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
      </div>

      {loading && <p className="mt-4 text-sm text-slate-400">분석 중입니다…</p>}
      {error && <p className="mt-4 text-sm text-red-500">{error}</p>}

      {result && (
        <div className="mt-8 space-y-6">
          <div className="flex items-center gap-2 rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <FileSpreadsheet className="h-5 w-5 text-indigo-600" />
            <div>
              <p className="text-sm font-semibold text-slate-900">{result.filename}</p>
              <p className="text-xs text-slate-500">
                {result.row_count.toLocaleString()}행 · {result.column_count}개 컬럼
              </p>
            </div>
          </div>

          {result.ai_insight && (
            <div className="rounded-xl bg-indigo-50 p-5 ring-1 ring-indigo-100">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-indigo-700">
                <Sparkles className="h-4 w-4" /> AI 인사이트
              </div>
              <Markdown content={result.ai_insight} />
            </div>
          )}

          <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">컬럼별 통계</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500">
                    <th className="py-2 pr-4">컬럼</th>
                    <th className="py-2 pr-4">타입</th>
                    <th className="py-2 pr-4">결측</th>
                    <th className="py-2 pr-4">고유값</th>
                    <th className="py-2 pr-4">요약</th>
                  </tr>
                </thead>
                <tbody>
                  {result.columns.map((c) => (
                    <tr key={c.column} className="border-b border-slate-100">
                      <td className="py-2 pr-4 font-medium text-slate-800">{c.column}</td>
                      <td className="py-2 pr-4 text-slate-500">{c.dtype}</td>
                      <td className="py-2 pr-4 text-slate-500">{c.null_count}</td>
                      <td className="py-2 pr-4 text-slate-500">{c.unique_count}</td>
                      <td className="py-2 pr-4 text-slate-500">
                        {c.numeric_summary
                          ? `평균 ${c.numeric_summary.mean?.toFixed(2)} / 최소 ${c.numeric_summary.min} / 최대 ${c.numeric_summary.max}`
                          : c.top_values
                          ? Object.entries(c.top_values)
                              .map(([k, v]) => `${k}(${v})`)
                              .join(", ")
                          : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
            <h2 className="mb-3 text-sm font-semibold text-slate-900">데이터 미리보기 (상위 10행)</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs text-slate-500">
                    {result.preview[0] &&
                      Object.keys(result.preview[0]).map((k) => (
                        <th key={k} className="py-2 pr-4 whitespace-nowrap">
                          {k}
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {result.preview.map((row, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="py-2 pr-4 whitespace-nowrap text-slate-600">
                          {String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
