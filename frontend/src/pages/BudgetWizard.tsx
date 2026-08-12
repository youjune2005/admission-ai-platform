import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  FileDown,
  FileText,
  LoaderCircle,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { API_BASE_URL, apiClient } from "../api/client";
import WizardStepper from "../components/WizardStepper";
import StepTransition from "../components/StepTransition";
import { BUDGET_FLOW_STEPS, flowStepFromWizard } from "../constants/documentFlow";

type WizardStep = 1 | 2 | 3 | 4 | 5;

type BudgetRow = {
  id: string;
  name: string;
  basis: string;
  unit_price: number;
  quantity: number;
  status?: string;
};

type ReviewResult = {
  items: Array<{
    name: string;
    basis: string;
    unit_price: number;
    quantity: number;
    amount: number;
    status: string;
  }>;
  total_budget: number;
  allocated_budget: number;
  remaining_budget: number;
  summary: { suitable: number; needs_check: number };
  applied_regulations: string[];
  evidence: Array<{ name: string; status: string }>;
};

const DEFAULT_ROWS: BudgetRow[] = [
  {
    id: "1",
    name: "다과비",
    basis: "50명 × 10,000원",
    unit_price: 10000,
    quantity: 50,
  },
  {
    id: "2",
    name: "홍보물(리플렛)",
    basis: "견적 기준",
    unit_price: 1000,
    quantity: 100,
  },
  {
    id: "3",
    name: "현수막",
    basis: "3m × 1m",
    unit_price: 100000,
    quantity: 1,
  },
  {
    id: "4",
    name: "장소 장비",
    basis: "대여 및 장비비",
    unit_price: 300000,
    quantity: 1,
  },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function won(n: number) {
  return `${Number(n || 0).toLocaleString("ko-KR")}원`;
}

function statusClass(status: string) {
  if (status === "적합") return "bg-emerald-50 text-emerald-700";
  if (status === "견적서 필요") return "bg-orange-50 text-orange-700";
  return "bg-amber-50 text-amber-700";
}

export default function BudgetWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<WizardStep>(1);
  const [title, setTitle] = useState("2027학년도 수시 입시설명회 예상 예산안");
  const [allocated, setAllocated] = useState(1500000);
  const [rows, setRows] = useState<BudgetRow[]>(DEFAULT_ROWS);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [planId, setPlanId] = useState<number | null>(null);
  const [archiveId, setArchiveId] = useState<number | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [savingArchive, setSavingArchive] = useState(false);

  const total = useMemo(
    () => rows.reduce((sum, r) => sum + r.unit_price * r.quantity, 0),
    [rows]
  );
  const remaining = allocated - total;

  const updateRow = (id: string, patch: Partial<BudgetRow>) => {
    setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const addRow = () => {
    setRows((prev) => [
      ...prev,
      {
        id: `${Date.now()}`,
        name: "",
        basis: "",
        unit_price: 0,
        quantity: 1,
      },
    ]);
  };

  const removeRow = (id: string) => {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  };

  const payloadItems = () =>
    rows.map((r) => ({
      name: r.name,
      basis: r.basis,
      unit_price: r.unit_price,
      quantity: r.quantity,
      amount: r.unit_price * r.quantity,
      status: r.status,
    }));

  const startReviewFlow = async () => {
    setError(null);
    if (!rows.some((r) => r.name.trim())) {
      setError("예산 항목을 1개 이상 입력해주세요.");
      return;
    }

    try {
      setStep(2);
      setLoadingLabel("행정 요건과 입력값을 검토하고 있습니다…");
      await sleep(1100);

      setStep(3);
      setLoadingLabel("규정·자료 관리 DB와 비교하여 규정 상태를 확인합니다…");
      const { data } = await apiClient.post<ReviewResult>("/api/budget/review", {
        title,
        allocated_budget: allocated,
        items: payloadItems(),
      });
      setReview(data);
      setRows(
        data.items.map((item, idx) => ({
          id: rows[idx]?.id ?? `${idx}`,
          name: item.name,
          basis: item.basis,
          unit_price: item.unit_price,
          quantity: item.quantity,
          status: item.status,
        }))
      );
      await sleep(900);
      setStep(4);
      setLoadingLabel("");
    } catch (e) {
      setStep(1);
      setLoadingLabel("");
      setError(e instanceof Error ? e.message : "규정 검토에 실패했습니다.");
    }
  };

  const rowsRef = useRef(rows);
  const allocatedRef = useRef(allocated);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);
  useEffect(() => {
    allocatedRef.current = allocated;
  }, [allocated]);

  const refreshReviewOnStep4 = async (nextRows?: BudgetRow[], nextAllocated?: number) => {
    const useRows = nextRows ?? rowsRef.current;
    const useAllocated = nextAllocated ?? allocatedRef.current;
    try {
      const { data } = await apiClient.post<ReviewResult>("/api/budget/review", {
        title,
        allocated_budget: useAllocated,
        items: useRows.map((r) => ({
          name: r.name,
          basis: r.basis,
          unit_price: r.unit_price,
          quantity: r.quantity,
          amount: r.unit_price * r.quantity,
        })),
      });
      setReview(data);
      setRows(
        data.items.map((item, idx) => ({
          id: useRows[idx]?.id ?? `${idx}`,
          name: item.name,
          basis: item.basis,
          unit_price: item.unit_price,
          quantity: item.quantity,
          status: item.status,
        }))
      );
    } catch {
      // keep current
    }
  };

  const finalize = async () => {
    setError(null);
    try {
      const { data } = await apiClient.post<{
        id: number;
        pdf_url: string | null;
        preview_url: string | null;
        archive_id?: number | null;
      }>("/api/budget/finalize", {
        title,
        allocated_budget: allocated,
        items: payloadItems(),
      });
      setPlanId(data.id);
      setArchiveId(data.archive_id ?? null);
      setPdfUrl(data.pdf_url);
      setPreviewUrl(data.preview_url);
      setStep(5);
    } catch (e) {
      setError(e instanceof Error ? e.message : "최종 문서 생성에 실패했습니다.");
    }
  };

  const saveToArchive = async () => {
    setSavingArchive(true);
    try {
      if (archiveId != null) {
        await apiClient.patch(`/api/archive/${archiveId}/status`, { status: "archived" });
      }
      navigate("/archive");
    } catch {
      navigate("/archive");
    } finally {
      setSavingArchive(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-6">
      {step === 5 ? (
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setStep(4)}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[22px] font-bold text-slate-900">예산안 문서 완성</h1>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                예산안 PDF
              </span>
            </div>
            <p className="mt-0.5 text-[12px] text-slate-500">{title}</p>
          </div>
        </div>
      ) : (
        <div className="mb-4 flex items-start gap-3">
          <button
            type="button"
            onClick={() => navigate("/documents/create")}
            className="mt-0.5 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="문서 선택으로 돌아가기"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-[22px] font-bold text-slate-900">
              {step === 4 ? "예산안 및 규정 검토" : "예상 예산안 작성"}
            </h1>
            <p className="mt-1 text-[13px] text-slate-500">
              예산 항목을 입력하면 규정 검토 후 예산안 PDF로 완성합니다.
            </p>
          </div>
        </div>
      )}

      <WizardStepper
        steps={BUDGET_FLOW_STEPS}
        current={flowStepFromWizard(step)}
        className="mb-1"
      />

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
          {error}
        </div>
      )}

      <StepTransition stepKey={step}>
      {step === 1 && (
        <>
          <section className="mt-6 rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block">
                <span className="text-[12px] font-medium text-slate-600">문서 제목</span>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="field-input mt-1"
                />
              </label>
              <label className="block">
                <span className="text-[12px] font-medium text-slate-600">배정 예산 (원)</span>
                <input
                  value={allocated.toLocaleString("ko-KR")}
                  onChange={(e) => {
                    const n = Number(e.target.value.replace(/[^\d]/g, "") || "0");
                    setAllocated(n);
                  }}
                  className="field-input mt-1"
                />
              </label>
            </div>

            <div className="mt-5 flex items-center justify-between">
              <p className="text-[14px] font-bold text-slate-900">예산 항목 입력</p>
              <button
                type="button"
                onClick={addRow}
                className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--ssu-blue)]"
              >
                <Plus className="h-3.5 w-3.5" /> 항목 추가
              </button>
            </div>

            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[12px]">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-500">
                    <th className="px-2 py-2 font-medium">예산 항목</th>
                    <th className="px-2 py-2 font-medium">산출 근거</th>
                    <th className="px-2 py-2 font-medium">단가</th>
                    <th className="px-2 py-2 font-medium">수량</th>
                    <th className="px-2 py-2 font-medium">금액</th>
                    <th className="w-8 px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="border-b border-slate-50">
                      <td className="px-2 py-2">
                        <input
                          value={row.name}
                          onChange={(e) => updateRow(row.id, { name: e.target.value })}
                          className="field-input"
                          placeholder="예: 다과비"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          value={row.basis}
                          onChange={(e) => updateRow(row.id, { basis: e.target.value })}
                          className="field-input"
                          placeholder="예: 50명 × 10,000원"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          value={row.unit_price.toLocaleString("ko-KR")}
                          onChange={(e) =>
                            updateRow(row.id, {
                              unit_price: Number(e.target.value.replace(/[^\d]/g, "") || "0"),
                            })
                          }
                          className="field-input text-right"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          value={row.quantity}
                          onChange={(e) =>
                            updateRow(row.id, {
                              quantity: Number(e.target.value.replace(/[^\d]/g, "") || "0"),
                            })
                          }
                          className="field-input text-right"
                        />
                      </td>
                      <td className="px-2 py-2 text-right font-semibold text-slate-800">
                        {won(row.unit_price * row.quantity)}
                      </td>
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          onClick={() => removeRow(row.id)}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 flex flex-col items-end gap-1 text-[13px]">
              <p>
                총 예산액 <span className="ml-3 font-bold text-slate-900">{won(total)}</span>
              </p>
              <p>
                배정 예산 <span className="ml-3 font-semibold text-slate-700">{won(allocated)}</span>
              </p>
              <p>
                잔여 예산{" "}
                <span
                  className={`ml-3 font-bold ${
                    remaining >= 0 ? "text-[var(--ssu-blue)]" : "text-red-600"
                  }`}
                >
                  {won(remaining)}
                </span>
              </p>
            </div>
          </section>

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => navigate("/documents/create")}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700"
            >
              이전
            </button>
            <button
              type="button"
              onClick={startReviewFlow}
              className="rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white"
            >
              다음 (행정·규정 검토)
            </button>
          </div>
        </>
      )}

      {(step === 2 || step === 3) && (
        <section className="mt-10 flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-[var(--ssu-border)] bg-white px-6 py-16 text-center shadow-sm">
          <LoaderCircle className="h-10 w-10 animate-spin text-[var(--ssu-blue)]" />
          <p className="mt-5 text-[16px] font-bold text-slate-900">
            {step === 2 ? "행정 검토 중" : "규정 검토 중"}
          </p>
          <p className="mt-2 max-w-md text-[13px] text-slate-500">{loadingLabel}</p>
          <div className="mt-6 flex gap-2">
            {["행정 검토", "규정 검토"].map((label, idx) => {
              const n = (idx + 2) as WizardStep;
              return (
                <span
                  key={label}
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold ${
                    n === step
                      ? "bg-blue-50 text-[var(--ssu-blue)]"
                      : n < step
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-100 text-slate-400"
                  }`}
                >
                  {label}
                </span>
              );
            })}
          </div>
        </section>
      )}

      {step === 4 && (
        <>
          <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_300px]">
            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
              <p className="text-[14px] font-bold text-slate-900">예산안 검토 및 편집</p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-[12px]">
                  <thead>
                    <tr className="border-b border-slate-100 bg-slate-50 text-slate-600">
                      <th className="px-2 py-2.5 font-semibold">예산 항목</th>
                      <th className="px-2 py-2.5 font-semibold">산출 근거</th>
                      <th className="px-2 py-2.5 font-semibold">단가</th>
                      <th className="px-2 py-2.5 font-semibold">수량</th>
                      <th className="px-2 py-2.5 font-semibold">금액</th>
                      <th className="px-2 py-2.5 font-semibold">규정 상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.id} className="border-b border-slate-50">
                        <td className="px-2 py-2 font-medium text-slate-800">{row.name}</td>
                        <td className="px-2 py-2 text-slate-600">{row.basis}</td>
                        <td className="px-2 py-2">
                          <input
                            value={row.unit_price.toLocaleString("ko-KR")}
                            onChange={(e) => {
                              const unit_price = Number(e.target.value.replace(/[^\d]/g, "") || "0");
                              const next = rows.map((r) =>
                                r.id === row.id ? { ...r, unit_price } : r
                              );
                              setRows(next);
                            }}
                            onBlur={() => void refreshReviewOnStep4()}
                            className="field-input text-right"
                          />
                        </td>
                        <td className="px-2 py-2">
                          <input
                            value={row.quantity}
                            onChange={(e) => {
                              const quantity = Number(e.target.value.replace(/[^\d]/g, "") || "0");
                              const next = rows.map((r) =>
                                r.id === row.id ? { ...r, quantity } : r
                              );
                              setRows(next);
                            }}
                            onBlur={() => void refreshReviewOnStep4()}
                            className="field-input text-right"
                          />
                        </td>
                        <td className="px-2 py-2 text-right font-semibold">
                          {won(row.unit_price * row.quantity)}
                        </td>
                        <td className="px-2 py-2">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold ${statusClass(
                              row.status || "담당자 확인"
                            )}`}
                          >
                            {row.status || "담당자 확인"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-4 flex flex-col items-end gap-1 text-[13px]">
                <p>
                  총 예산액 <span className="ml-3 font-bold">{won(total)}</span>
                </p>
                <p>
                  배정 예산 <span className="ml-3 font-semibold text-slate-700">{won(allocated)}</span>
                </p>
                <p>
                  잔여 예산{" "}
                  <span
                    className={`ml-3 font-bold ${
                      remaining >= 0 ? "text-[var(--ssu-blue)]" : "text-red-600"
                    }`}
                  >
                    {won(remaining)}
                  </span>
                </p>
              </div>
            </section>

            <aside className="space-y-4">
              <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4 shadow-sm">
                <p className="text-[13px] font-bold text-slate-900">규정 검토 결과</p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-center">
                    <p className="text-[16px] font-bold text-emerald-700">
                      {review?.summary.suitable ?? 0}건
                    </p>
                    <p className="text-[11px] text-emerald-700">적합</p>
                  </div>
                  <div className="rounded-lg border border-orange-200 bg-orange-50 px-3 py-3 text-center">
                    <p className="text-[16px] font-bold text-orange-700">
                      {review?.summary.needs_check ?? 0}건
                    </p>
                    <p className="text-[11px] text-orange-700">확인 필요</p>
                  </div>
                </div>

                <p className="mt-4 text-[12px] font-semibold text-slate-700">적용 규정</p>
                <ul className="mt-2 space-y-1.5 text-[12px] text-slate-600">
                  {(review?.applied_regulations || []).map((reg) => (
                    <li key={reg} className="flex items-start gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-400" />
                      {reg}
                    </li>
                  ))}
                </ul>

                {(review?.summary.needs_check ?? 0) > 0 && (
                  <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] text-amber-800">
                    <p className="flex items-center gap-1.5 font-semibold">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      담당자 확인 사항
                    </p>
                    <p className="mt-1 leading-relaxed">
                      확인 필요한 항목이 있습니다. 담당자 검토 후 진행해 주세요.
                    </p>
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4 shadow-sm">
                <p className="text-[13px] font-bold text-slate-900">필수 증빙 자료</p>
                <ul className="mt-3 space-y-2">
                  {(review?.evidence || []).map((ev) => (
                    <li
                      key={ev.name}
                      className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium text-slate-700">{ev.name}</span>
                      <span
                        className={`font-semibold ${
                          ev.status === "첨부 완료" ? "text-emerald-600" : "text-orange-600"
                        }`}
                      >
                        {ev.status}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            </aside>
          </div>

          <div className="mt-5 flex items-center justify-between gap-2">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rounded-lg border border-[var(--ssu-blue)] bg-white px-4 py-2.5 text-[13px] font-semibold text-[var(--ssu-blue)]"
            >
              이전
            </button>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void refreshReviewOnStep4()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--ssu-blue)] bg-white px-4 py-2.5 text-[13px] font-semibold text-[var(--ssu-blue)]"
              >
                <Save className="h-4 w-4" />
                초안 저장
              </button>
              <button
                type="button"
                onClick={finalize}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white"
              >
                <FileText className="h-4 w-4" />
                최종 문서 생성
              </button>
            </div>
          </div>
        </>
      )}

      {step === 5 && (
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_280px]">
          <section className="rounded-xl border border-[var(--ssu-border)] bg-[#f5f6f8] p-5">
            <div className="mx-auto max-w-[720px] overflow-hidden rounded-sm bg-white shadow-sm ring-1 ring-slate-200">
              {previewUrl ? (
                <img
                  src={`${API_BASE_URL}${previewUrl}`}
                  alt="예산안 PDF 미리보기"
                  className="mx-auto block h-auto w-full object-contain"
                />
              ) : (
                <p className="py-20 text-center text-[13px] text-slate-400">미리보기 준비 중…</p>
              )}
            </div>
            <div className="mt-5 flex justify-center gap-2">
              {pdfUrl && (
                <a
                  href={`${API_BASE_URL}${pdfUrl}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--ssu-navy)] px-5 py-3 text-[13px] font-semibold text-white"
                >
                  <FileDown className="h-4 w-4" />
                  PDF 다운로드
                </a>
              )}
              <button
                type="button"
                onClick={() => void saveToArchive()}
                disabled={savingArchive}
                className="rounded-lg bg-[var(--ssu-blue)] px-5 py-3 text-[13px] font-semibold text-white disabled:opacity-60"
              >
                {savingArchive ? "저장 중…" : "문서 보관함에 저장"}
              </button>
            </div>
          </section>

          <aside className="space-y-4">
            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4">
              <p className="text-[13px] font-bold text-slate-900">문서 정보</p>
              <dl className="mt-3 space-y-2 text-[12px]">
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">서식</dt>
                  <dd className="font-medium">예산안</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">총 예산</dt>
                  <dd className="font-medium">{won(total)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">잔여 예산</dt>
                  <dd className="font-medium text-[var(--ssu-blue)]">{won(remaining)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">문서 ID</dt>
                  <dd className="font-medium">{planId ?? "-"}</dd>
                </div>
              </dl>
            </section>
          </aside>
        </div>
      )}
      </StepTransition>

      <style>{`
        .field-input {
          width: 100%;
          border-radius: 0.5rem;
          border: 1px solid #e2e8f0;
          background: #fff;
          padding: 0.5rem 0.7rem;
          font-size: 12px;
          outline: none;
        }
        .field-input:focus {
          border-color: var(--ssu-blue);
          box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
        }
      `}</style>
    </div>
  );
}
