import { Link } from "react-router-dom";
import { AlertTriangle, BookOpen, ExternalLink, FileText } from "lucide-react";
import type { RegulationReviewResult } from "../types";

type Props = {
  result: RegulationReviewResult;
  busy?: boolean;
  onBack: () => void;
  onContinue: () => void;
};

function relevanceTone(n: number) {
  const v = Math.max(0, Math.min(100, n || 0));
  if (v >= 90) {
    return {
      chip: "bg-[#062a8f] text-white",
      card: "border-[#062a8f] bg-[#062a8f]/10",
      title: "text-[#062a8f]",
    };
  }
  if (v >= 80) {
    return {
      chip: "bg-[#0f3fd1] text-white",
      card: "border-[#0f3fd1] bg-[#1a5cff]/10",
      title: "text-[#0f3fd1]",
    };
  }
  if (v >= 70) {
    return {
      chip: "bg-[#1a5cff] text-white",
      card: "border-[#1a5cff] bg-blue-50",
      title: "text-[#1a5cff]",
    };
  }
  if (v >= 55) {
    return {
      chip: "bg-[#5b8aff] text-white",
      card: "border-blue-200 bg-blue-50/70",
      title: "text-[#1a5cff]",
    };
  }
  return {
    chip: "bg-slate-200 text-slate-600",
    card: "border-slate-200 bg-white",
    title: "text-slate-700",
  };
}

export default function RegulationReviewPanel({ result, busy, onBack, onContinue }: Props) {
  return (
    <section className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_300px]">
      <div className="rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[16px] font-bold text-slate-900">규정 검토 결과</p>
            <p className="mt-1 text-[13px] text-slate-500">
              규정과 명백히 충돌하면 「규정에 맞지 않음」, 그 외 확인이 필요하면 대부분
              「검토 필요」로 표시합니다.
            </p>
          </div>
          <div className="flex gap-2">
            <span className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-center">
              <p className="text-[15px] font-bold text-red-700">{result.summary.violations}건</p>
              <p className="text-[11px] text-red-700">규정에 맞지 않음</p>
            </span>
            <span className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-2 text-center">
              <p className="text-[15px] font-bold text-orange-700">{result.summary.needs_check}건</p>
              <p className="text-[11px] text-orange-700">검토 필요</p>
            </span>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {result.findings.map((finding, idx) => {
            const violation = finding.status === "violation";
            const reason = (finding.reason || "").trim();
            const note =
              finding.mismatch_note ||
              finding.explanation ||
              finding.problem;
            return (
              <article
                key={`${finding.location}-${idx}`}
                className={`rounded-xl border p-4 ${
                  violation ? "border-red-200 bg-red-50/40" : "border-orange-200 bg-orange-50/40"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                      violation ? "bg-red-600 text-white" : "bg-orange-500 text-white"
                    }`}
                  >
                    {violation ? "규정에 맞지 않음" : "검토가 필요함"}
                  </span>
                  <p className="text-[12px] font-semibold text-slate-700">{finding.location}</p>
                </div>

                {!violation && reason && (
                  <div className="mt-3 rounded-lg border border-orange-200 bg-white px-3 py-2.5">
                    <p className="text-[11px] font-semibold text-orange-700">검토가 필요한 이유</p>
                    <p className="mt-1 text-[13px] font-semibold leading-relaxed text-slate-900">
                      {reason}
                    </p>
                  </div>
                )}

                {(violation || !reason) && (
                  <p className="mt-2 text-[14px] font-semibold leading-relaxed text-slate-900">
                    {note}
                  </p>
                )}

                {finding.document_excerpt && (
                  <div className="mt-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
                      <FileText className="h-3.5 w-3.5" />
                      이 문서의 해당 부분
                    </p>
                    <p className="mt-1 text-[13px] leading-relaxed text-slate-800">
                      「{finding.document_excerpt}」
                    </p>
                  </div>
                )}

                {(finding.regulation_title || finding.regulation_excerpt) && (
                  <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5">
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--ssu-blue)]">
                      <BookOpen className="h-3.5 w-3.5" />
                      {finding.citation_n ? `[${finding.citation_n}] ` : ""}
                      {finding.regulation_title || "내부 규정"}
                    </p>
                    {finding.regulation_excerpt && (
                      <p className="mt-1 text-[13px] leading-relaxed text-slate-800">
                        「{finding.regulation_excerpt}」
                      </p>
                    )}
                    {violation && (
                      <p className="mt-2 text-[12px] font-semibold text-slate-700">
                        위 규정 문장 때문에 이 문서 기재가 규정에 맞지 않습니다.
                      </p>
                    )}
                  </div>
                )}
              </article>
            );
          })}
          {result.findings.length === 0 && (
            <p className="rounded-lg bg-emerald-50 px-4 py-6 text-center text-[13px] text-emerald-700">
              대조한 규정 원문과 모순되거나, 별도 검토가 필요한 사유는 없습니다.
            </p>
          )}
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={onBack}
            className="rounded-lg border border-[var(--ssu-blue)] bg-white px-4 py-2.5 text-[13px] font-semibold text-[var(--ssu-blue)] disabled:opacity-50"
          >
            이전으로 수정
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onContinue}
            className="rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
          >
            확인 후 계속
          </button>
        </div>
      </div>

      <aside className="space-y-4">
        <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4 shadow-sm">
          <p className="text-[13px] font-bold text-slate-900">근거 자료</p>
          <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
            예산·행정 규정 등 관련 카테고리에서 찾고, 제목 관련도를 한 번 더 확인한 근거입니다.
          </p>
          <div className="mt-3 space-y-2">
            {result.references.map((ref, idx) => {
              const tone = relevanceTone(ref.relevance);
              return (
                <div
                  key={`${ref.document_id}-${idx}`}
                  className={`rounded-lg border p-3 ${tone.card}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      {ref.category && (
                        <p className="text-[10px] font-semibold text-slate-500">{ref.category}</p>
                      )}
                      <p className={`text-[12px] font-bold leading-snug ${tone.title}`}>
                        {idx + 1}. {ref.filename}
                      </p>
                    </div>
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${tone.chip}`}
                    >
                      관련도 {ref.relevance}%
                    </span>
                  </div>
                  <p className="mt-2 text-[11px] leading-relaxed text-slate-700">
                    {ref.mismatch_excerpt || ref.snippet || "관련 규정 발췌가 없습니다."}
                  </p>
                  {ref.verdict === "violation" && (
                    <p className="mt-1.5 text-[10px] font-bold text-red-700">규정에 맞지 않는 근거</p>
                  )}
                  {ref.verdict === "check" && (
                    <p className="mt-1.5 text-[10px] font-bold text-orange-700">검토가 필요한 근거</p>
                  )}
                </div>
              );
            })}
            {result.references.length === 0 && (
              <p className="rounded-lg bg-slate-50 px-3 py-5 text-center text-[12px] text-slate-400">
                매칭된 근거 자료가 없습니다.
              </p>
            )}
          </div>
          <Link
            to="/regulations"
            className="mt-3 inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--ssu-blue)]"
          >
            규정·자료 관리 <ExternalLink className="h-3 w-3" />
          </Link>
        </section>

        {result.summary.violations + result.summary.needs_check > 0 && (
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-4">
            <p className="flex items-center gap-1.5 text-[12px] font-bold text-amber-900">
              <AlertTriangle className="h-3.5 w-3.5" />
              담당자 확인
            </p>
            <p className="mt-1.5 text-[12px] leading-relaxed text-amber-900">
              인용된 규정 문장과 문서 구절을 원문과 한 번 더 대조한 뒤 수정하거나 저장하세요.
            </p>
          </section>
        )}
      </aside>
    </section>
  );
}
