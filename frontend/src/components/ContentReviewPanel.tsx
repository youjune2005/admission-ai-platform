import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import type { ContentReviewIssue, ContentReviewOption, ContentReviewPatch, ContentReviewResult } from "../types";

type Props = {
  result: ContentReviewResult;
  busy?: boolean;
  onApply: (patches: ContentReviewPatch[]) => void;
  onSkip: () => void;
};

const SKIP = "__skip__";

function issueOptions(issue: ContentReviewIssue): ContentReviewOption[] {
  if (issue.options?.length) return issue.options;
  if (issue.patch) {
    return [
      {
        id: "suggested",
        label: issue.after || "제안대로 수정",
        before: issue.before || "",
        after: issue.after || "",
        patches: [issue.patch],
      },
    ];
  }
  return [];
}

export default function ContentReviewPanel({ result, busy, onApply, onSkip }: Props) {
  const choices = useMemo(() => {
    const initial: Record<string, string> = {};
    for (const issue of result.issues) {
      const opts = issueOptions(issue);
      initial[issue.id] = opts[0]?.id ?? SKIP;
    }
    return initial;
  }, [result.issues]);
  const [selected, setSelected] = useState<Record<string, string>>(choices);
  useEffect(() => {
    setSelected(choices);
  }, [choices]);

  const patches = useMemo(() => {
    const next: ContentReviewPatch[] = [];
    for (const issue of result.issues) {
      const optionId = selected[issue.id];
      if (!optionId || optionId === SKIP) continue;
      const option = issueOptions(issue).find((item) => item.id === optionId);
      if (option?.patches?.length) next.push(...option.patches);
    }
    return next;
  }, [result.issues, selected]);

  return (
    <section className="mt-6 rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[16px] font-bold text-slate-900">내용 점검 결과</p>
          <p className="mt-1 text-[13px] text-slate-500">
            같은 불일치는 한 건만 보여 드립니다. 수량·산출 근거·단가 중 맞는 쪽을 선택하세요.
          </p>
        </div>
        <div className="flex gap-2">
          <span className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-center">
            <p className="text-[15px] font-bold text-red-700">{result.summary.errors}건</p>
            <p className="text-[11px] text-red-700">불일치</p>
          </span>
          <span className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-center">
            <p className="text-[15px] font-bold text-amber-700">{result.summary.warnings}건</p>
            <p className="text-[11px] text-amber-700">확인</p>
          </span>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {result.issues.map((issue) => {
          const opts = issueOptions(issue);
          const current = selected[issue.id] ?? SKIP;
          return (
            <article
              key={issue.id}
              className="rounded-xl border border-slate-200 bg-slate-50/60 p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                    issue.severity === "error"
                      ? "bg-red-50 text-red-700"
                      : "bg-amber-50 text-amber-800"
                  }`}
                >
                  {issue.severity === "error" ? "불일치" : "확인 필요"}
                </span>
                <p className="text-[12px] font-semibold text-slate-700">{issue.location}</p>
              </div>
              <p className="mt-2 text-[13px] font-medium leading-relaxed text-slate-900">
                {issue.problem}
              </p>
              {issue.guideline && (
                <p className="mt-2 text-[12px] leading-relaxed text-slate-600">{issue.guideline}</p>
              )}

              {opts.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {opts.map((option) => {
                    const on = current === option.id;
                    return (
                      <label
                        key={option.id}
                        className={`block cursor-pointer rounded-lg border px-3 py-2.5 ${
                          on
                            ? "border-[var(--ssu-blue)] bg-blue-50"
                            : "border-slate-200 bg-white hover:border-slate-300"
                        }`}
                      >
                        <span className="flex items-start gap-2">
                          <input
                            type="radio"
                            name={`issue-${issue.id}`}
                            className="mt-0.5"
                            checked={on}
                            onChange={() =>
                              setSelected((prev) => ({ ...prev, [issue.id]: option.id }))
                            }
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block text-[13px] font-semibold text-slate-900">
                              {option.label}
                            </span>
                            {(option.before || option.after) && (
                              <span className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[12px] text-slate-600">
                                <span className="rounded bg-white px-2 py-1 text-slate-500">
                                  {option.before || "-"}
                                </span>
                                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                                <span className="rounded bg-white px-2 py-1 font-medium text-slate-800">
                                  {option.after || "-"}
                                </span>
                              </span>
                            )}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                  <label
                    className={`block cursor-pointer rounded-lg border px-3 py-2.5 ${
                      current === SKIP
                        ? "border-slate-400 bg-white"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <span className="flex items-center gap-2 text-[13px] text-slate-600">
                      <input
                        type="radio"
                        name={`issue-${issue.id}`}
                        checked={current === SKIP}
                        onChange={() =>
                          setSelected((prev) => ({ ...prev, [issue.id]: SKIP }))
                        }
                      />
                      이 항목은 수정하지 않음
                    </span>
                  </label>
                </div>
              ) : (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] text-amber-900">
                  자동으로 한쪽만 맞출 수 없습니다. 이전 단계에서 값을 수정하거나, 확인 후 계속하세요.
                </div>
              )}
            </article>
          );
        })}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onSkip}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          수정 없이 계속
        </button>
        <button
          type="button"
          disabled={busy || patches.length === 0}
          onClick={() => onApply(patches)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
        >
          <Check className="h-4 w-4" />
          선택한 수정 적용 후 계속
        </button>
      </div>
    </section>
  );
}
