import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Calendar,
  Check,
  Clock3,
  FileDown,
  GripVertical,
  LoaderCircle,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { API_BASE_URL, apiClient } from "../api/client";
import WizardStepper from "../components/WizardStepper";
import StepTransition from "../components/StepTransition";
import ContentReviewPanel from "../components/ContentReviewPanel";
import RegulationReviewPanel from "../components/RegulationReviewPanel";
import {
  BRIEFING_FLOW_STEPS,
  flowStepFromWizard,
} from "../constants/documentFlow";
import { asNumber, asRecord, asString } from "../lib/archiveWizard";
import { applyReviewPatches } from "../lib/reviewPatches";
import type {
  ContentReviewPatch,
  ContentReviewResult,
  GeneratedDocument,
  RegulationReviewResult,
} from "../types";

type ProgramRow = {
  id: string;
  time: string;
  content: string;
  owner: string;
};

type BudgetLineRow = {
  id: string;
  name: string;
  basis: string;
  unit_price: number;
  quantity: number;
};

type StaffPerson = {
  id: number;
  name: string;
};

type WizardStep = 1 | 2 | 3 | 4 | 5 | 6;

const STEP_LABELS = [
  "문서 선택",
  "기본정보 입력",
  "예산 입력",
  "계획 생성",
  "내용 구성",
  "규정 검토",
  "완성 및 저장",
] as const;

const DEFAULT_BUDGET_OPTIONS = ["다과", "홍보물", "현수막", "장소 장비", "교통비"] as const;

const BUDGET_LINE_DEFAULTS: Record<
  string,
  { unit_price: number; quantityFromAttendees: (n: number) => number; basis: (n: number, unit: number, qty: number) => string }
> = {
  다과: {
    unit_price: 8000,
    quantityFromAttendees: (n) => n,
    basis: (_n, unit, qty) => `${qty}명 × ${unit.toLocaleString("ko-KR")}원`,
  },
  홍보물: {
    unit_price: 1500,
    quantityFromAttendees: (n) => n,
    basis: (_n, unit, qty) => `리플렛 ${qty}부 × ${unit.toLocaleString("ko-KR")}원`,
  },
  현수막: {
    unit_price: 120000,
    quantityFromAttendees: () => 1,
    basis: () => "현수막 1식",
  },
  "장소 장비": {
    unit_price: 300000,
    quantityFromAttendees: () => 1,
    basis: () => "음향·빔 등 1식",
  },
  교통비: {
    unit_price: 50000,
    quantityFromAttendees: (n) => Math.max(1, Math.floor(n / 50)),
    basis: (_n, unit, qty) => `차량 ${qty}대 × ${unit.toLocaleString("ko-KR")}원`,
  },
};

const DEFAULT_PROGRAMS: ProgramRow[] = [
  { id: "1", time: "14:00~14:10", content: "개회 및 환영 인사", owner: "" },
  { id: "2", time: "14:10~14:50", content: "2027학년도 수시전형 안내", owner: "" },
  { id: "3", time: "14:50~15:20", content: "학과 소개 및 캠퍼스 투어 안내", owner: "" },
  { id: "4", time: "15:20~16:00", content: "질의응답", owner: "" },
  { id: "5", time: "16:00~16:30", content: "개별 상담", owner: "" },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatBudgetInput(raw: string) {
  const digits = raw.replace(/[^\d]/g, "");
  if (!digits) return "";
  return Number(digits).toLocaleString("ko-KR");
}

function won(n: number) {
  return `${Number(n || 0).toLocaleString("ko-KR")}원`;
}

function buildBudgetLinesFromSelection(
  selected: string[],
  attendeesRaw: string,
  prev: BudgetLineRow[]
): BudgetLineRow[] {
  const attendees = Number(attendeesRaw.replace(/[^\d]/g, "") || "100") || 100;
  const prevMap = new Map(prev.map((r) => [r.name, r]));
  return selected.map((name, idx) => {
    const existing = prevMap.get(name);
    if (existing) return existing;
    const def = BUDGET_LINE_DEFAULTS[name];
    const unit_price = def?.unit_price ?? 100000;
    const quantity = def?.quantityFromAttendees(attendees) ?? 1;
    const basis = def?.basis(attendees, unit_price, quantity) ?? `${name} 1식`;
    return {
      id: `${Date.now()}-${idx}`,
      name,
      basis,
      unit_price,
      quantity,
    };
  });
}

export default function DocumentWizard() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const template = params.get("template") || "입시설명회 운영계획서";
  const archiveIdParam = params.get("archiveId");

  const [step, setStep] = useState<WizardStep>(1);
  const [eventName, setEventName] = useState("2027학년도 수시 입시설명회");
  const [target, setTarget] = useState("서울 지역 고등학생 및 학부모");
  const [attendees, setAttendees] = useState("100");
  const [schedule, setSchedule] = useState("2025-07-19 (토) 14:00 ~ 16:30");
  const [location, setLocation] = useState("한경직기념관 대예배실");
  const [department, setDepartment] = useState("입학팀");
  const [budgetLimit, setBudgetLimit] = useState("2,000,000");
  const [budgetOptions, setBudgetOptions] = useState<string[]>([...DEFAULT_BUDGET_OPTIONS]);
  const [budgetItems, setBudgetItems] = useState<string[]>([...DEFAULT_BUDGET_OPTIONS]);
  const [newBudgetItem, setNewBudgetItem] = useState("");
  const [budgetLines, setBudgetLines] = useState<BudgetLineRow[]>([]);
  const [programs, setPrograms] = useState<ProgramRow[]>(DEFAULT_PROGRAMS);
  const [staffList, setStaffList] = useState<StaffPerson[]>([]);
  const [activeOwnerId, setActiveOwnerId] = useState<string | null>(null);

  const [loadingLabel, setLoadingLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [planId, setPlanId] = useState<number | null>(null);
  const [archiveId, setArchiveId] = useState<number | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [savingArchive, setSavingArchive] = useState(false);
  const [hydrating, setHydrating] = useState(!!archiveIdParam);
  const [pausedPhase, setPausedPhase] = useState<null | "content" | "regulation">(null);
  const [contentReview, setContentReview] = useState<ContentReviewResult | null>(null);
  const [regulationReview, setRegulationReview] = useState<RegulationReviewResult | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);

  const title = useMemo(() => `${eventName} 운영계획서`, [eventName]);
  const budgetTotal = useMemo(
    () => budgetLines.reduce((sum, r) => sum + r.unit_price * r.quantity, 0),
    [budgetLines]
  );
  const budgetLimitNumber = useMemo(
    () => Number(budgetLimit.replace(/[^\d]/g, "") || "0"),
    [budgetLimit]
  );
  const budgetRemaining = budgetLimitNumber - budgetTotal;

  const loadStaff = async () => {
    const res = await apiClient.get<StaffPerson[]>("/api/staff");
    setStaffList(res.data);
  };

  useEffect(() => {
    loadStaff().catch(() => setStaffList([]));
  }, []);

  useEffect(() => {
    if (!archiveIdParam) return;
    const id = Number(archiveIdParam);
    if (!Number.isFinite(id) || id <= 0) {
      setHydrating(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await apiClient.get<GeneratedDocument>(`/api/archive/${id}`);
        if (cancelled) return;
        const p = asRecord(data.payload) ?? {};
        setArchiveId(data.id);
        setEventName(asString(p.event_name, "2027학년도 수시 입시설명회"));
        setTarget(asString(p.target, "서울 지역 고등학생 및 학부모"));
        setAttendees(asString(p.attendees, "100"));
        setSchedule(asString(p.schedule));
        setLocation(asString(p.location));
        setDepartment(asString(p.department, "입학팀"));
        const limitRaw = p.budget_limit;
        setBudgetLimit(
          formatBudgetInput(
            typeof limitRaw === "number" ? String(limitRaw) : asString(limitRaw, "2000000")
          )
        );
        const itemNames = Array.isArray(p.budget_items)
          ? p.budget_items.map((n) => asString(n)).filter(Boolean)
          : [];
        const lineRows: BudgetLineRow[] = Array.isArray(p.budget_lines)
          ? p.budget_lines.flatMap((row, idx) => {
              const rec = asRecord(row);
              if (!rec) return [];
              return [
                {
                  id: `resume-${idx}`,
                  name: asString(rec.name),
                  basis: asString(rec.basis),
                  unit_price: asNumber(rec.unit_price),
                  quantity: asNumber(rec.quantity, 1),
                },
              ];
            })
          : [];
        const names = itemNames.length ? itemNames : lineRows.map((r) => r.name).filter(Boolean);
        if (names.length) {
          setBudgetOptions((prev) => Array.from(new Set([...prev, ...names])));
          setBudgetItems(names);
        }
        if (lineRows.length) setBudgetLines(lineRows);
        const programRows: ProgramRow[] = Array.isArray(p.programs)
          ? p.programs.flatMap((row, idx) => {
              const rec = asRecord(row);
              if (!rec) return [];
              return [
                {
                  id: `resume-p-${idx}`,
                  time: asString(rec.time),
                  content: asString(rec.content),
                  owner: asString(rec.owner),
                },
              ];
            })
          : [];
        if (programRows.length) setPrograms(programRows);
        setPdfUrl(null);
        setPreviewUrl(null);
        setStep(1);
      } catch {
        setError("작성 중이던 문서를 불러오지 못했습니다.");
      } finally {
        if (!cancelled) setHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [archiveIdParam]);

  const saveStaffName = async (raw: string) => {
    const name = raw.trim();
    if (!name) return null;
    const res = await apiClient.post<StaffPerson>("/api/staff", { name });
    setStaffList((prev) => {
      if (prev.some((p) => p.id === res.data.id || p.name === res.data.name)) {
        return prev.map((p) => (p.id === res.data.id ? res.data : p));
      }
      return [...prev, res.data].sort((a, b) => a.name.localeCompare(b.name, "ko"));
    });
    return res.data;
  };

  const deleteStaff = async (id: number) => {
    await apiClient.delete(`/api/staff/${id}`);
    setStaffList((prev) => prev.filter((p) => p.id !== id));
  };

  const applyStaffToProgram = (name: string) => {
    const targetId =
      activeOwnerId ??
      programs.find((p) => !p.owner.trim())?.id ??
      programs[0]?.id ??
      null;
    if (!targetId) return;
    updateProgram(targetId, { owner: name });
    setActiveOwnerId(targetId);
    void saveStaffName(name).catch(() => undefined);
  };

  const updateProgram = (id: string, patch: Partial<ProgramRow>) => {
    setPrograms((prev) => prev.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const addProgram = () => {
    const id = `${Date.now()}`;
    setPrograms((prev) => [
      ...prev,
      {
        id,
        time: "16:30~17:00",
        content: "",
        owner: "",
      },
    ]);
    setActiveOwnerId(id);
  };

  const removeProgram = (id: string) => {
    setPrograms((prev) => (prev.length <= 1 ? prev : prev.filter((row) => row.id !== id)));
  };

  const toggleBudgetItem = (item: string) => {
    setBudgetItems((prev) =>
      prev.includes(item) ? prev.filter((v) => v !== item) : [...prev, item]
    );
  };

  const isDefaultBudgetOption = (item: string) =>
    (DEFAULT_BUDGET_OPTIONS as readonly string[]).includes(item);

  const addBudgetOption = () => {
    const name = newBudgetItem.trim().replace(/\s+/g, " ");
    if (!name) return;
    const exists = budgetOptions.some((o) => o === name);
    if (exists) {
      if (!budgetItems.includes(name)) {
        setBudgetItems((prev) => [...prev, name]);
      }
      setNewBudgetItem("");
      return;
    }
    setBudgetOptions((prev) => [...prev, name]);
    setBudgetItems((prev) => [...prev, name]);
    setNewBudgetItem("");
  };

  const removeBudgetOption = (item: string) => {
    if (isDefaultBudgetOption(item)) return;
    setBudgetOptions((prev) => prev.filter((v) => v !== item));
    setBudgetItems((prev) => prev.filter((v) => v !== item));
  };

  const updateBudgetLine = (id: string, patch: Partial<BudgetLineRow>) => {
    setBudgetLines((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  };

  const goToBudgetStep = () => {
    setError(null);
    if (!eventName.trim()) {
      setError("행사명을 입력해주세요.");
      return;
    }
    if (budgetItems.length === 0) {
      setError("예산 항목 포함 조건을 1개 이상 선택해주세요.");
      return;
    }
    setBudgetLines((prev) => buildBudgetLinesFromSelection(budgetItems, attendees, prev));
    setStep(2);
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

  const buildPayload = () => ({
    event_name: eventName.trim(),
    target: target.trim(),
    attendees: attendees.trim() || "100",
    schedule: schedule.trim(),
    location: location.trim(),
    department: department.trim() || "입학팀",
    budget_limit: budgetLimit.replace(/,/g, "") || "2000000",
    budget_items: budgetItems,
    budget_lines: budgetLines.map(({ name, basis, unit_price, quantity }) => ({
      name,
      basis,
      unit_price,
      quantity,
    })),
    programs: programs.map(({ time, content, owner }) => ({ time, content, owner })),
    archive_id: archiveId,
  });

  const applyBriefingPayload = (p: Record<string, unknown>) => {
    setEventName(asString(p.event_name, eventName));
    setTarget(asString(p.target, target));
    setAttendees(asString(p.attendees, attendees));
    setSchedule(asString(p.schedule, schedule));
    setLocation(asString(p.location, location));
    setDepartment(asString(p.department, department));
    const limitRaw = p.budget_limit;
    if (limitRaw != null) {
      setBudgetLimit(
        formatBudgetInput(typeof limitRaw === "number" ? String(limitRaw) : asString(limitRaw, budgetLimit))
      );
    }
    const lineRows: BudgetLineRow[] = Array.isArray(p.budget_lines)
      ? p.budget_lines.flatMap((row, idx) => {
          const rec = asRecord(row);
          if (!rec) return [];
          return [
            {
              id: budgetLines[idx]?.id ?? `patched-${idx}`,
              name: asString(rec.name),
              basis: asString(rec.basis),
              unit_price: asNumber(rec.unit_price),
              quantity: asNumber(rec.quantity, 1),
            },
          ];
        })
      : [];
    if (lineRows.length) {
      setBudgetLines(lineRows);
      setBudgetItems(lineRows.map((r) => r.name).filter(Boolean));
    }
    const programRows: ProgramRow[] = Array.isArray(p.programs)
      ? p.programs.flatMap((row, idx) => {
          const rec = asRecord(row);
          if (!rec) return [];
          return [
            {
              id: programs[idx]?.id ?? `patched-p-${idx}`,
              time: asString(rec.time),
              content: asString(rec.content),
              owner: asString(rec.owner),
            },
          ];
        })
      : [];
    if (programRows.length) setPrograms(programRows);
  };

  const generatePlan = async (payload: ReturnType<typeof buildPayload>) => {
    const { data } = await apiClient.post<{
      id: number;
      pdf_url: string | null;
      preview_url: string | null;
      title: string;
      archive_id?: number | null;
    }>("/api/plans/briefing", payload);
    setPlanId(data.id);
    setArchiveId(data.archive_id ?? null);
    setPdfUrl(data.pdf_url);
    setPreviewUrl(data.preview_url);
    await loadStaff();
  };

  const runRegulationReview = async (payload: ReturnType<typeof buildPayload>) => {
    setPausedPhase(null);
    setStep(5);
    setLoadingLabel("관련 규정을 검토하고 있습니다…");
    const { archive_id: _aid, ...reviewPayload } = payload;
    const { data } = await apiClient.post<RegulationReviewResult>("/api/plans/review/regulations", {
      kind: "briefing",
      payload: reviewPayload,
    });
    setRegulationReview(data);
    if (!data.ok && data.findings.length > 0) {
      setPausedPhase("regulation");
      setLoadingLabel("");
      return;
    }
    setStep(6);
    setLoadingLabel("");
  };

  const runContentReview = async (payload: ReturnType<typeof buildPayload>) => {
    setPausedPhase(null);
    setStep(4);
    setLoadingLabel("입력하신 정보로 문서 내용을 구성하고 있습니다…");
    const { archive_id: _aid, ...reviewPayload } = payload;
    const { data } = await apiClient.post<ContentReviewResult>("/api/plans/review/consistency", {
      kind: "briefing",
      payload: reviewPayload,
    });
    setContentReview(data);
    if (!data.ok && data.issues.length > 0) {
      setPausedPhase("content");
      setLoadingLabel("");
      return;
    }
    await runRegulationReview(payload);
  };

  const startGeneration = async () => {
    setError(null);
    setPdfUrl(null);
    setPreviewUrl(null);
    setPausedPhase(null);
    setContentReview(null);
    setRegulationReview(null);

    if (budgetLines.length === 0) {
      setError("예산 항목이 없습니다. 이전 단계에서 항목을 선택해주세요.");
      return;
    }

    const payload = buildPayload();
    try {
      setStep(3);
      setLoadingLabel("행사 계획안을 생성하고 있습니다…");
      const apiPromise = generatePlan(payload);
      await sleep(1200);
      await apiPromise;
      await runContentReview(payload);
    } catch (e) {
      setStep(2);
      setPausedPhase(null);
      setLoadingLabel("");
      setError(e instanceof Error ? e.message : "문서 생성에 실패했습니다.");
    }
  };

  const continueContentReview = async (patches: ContentReviewPatch[]) => {
    setReviewBusy(true);
    setError(null);
    try {
      let payload = buildPayload();
      if (patches.length) {
        const { archive_id, ...body } = payload;
        const patched = applyReviewPatches(body, patches);
        applyBriefingPayload(patched);
        payload = { ...patched, archive_id };
        setPausedPhase(null);
        setStep(3);
        setLoadingLabel("수정된 내용으로 문서를 다시 구성하고 있습니다…");
        await generatePlan(payload);
      }
      setContentReview(null);
      await runRegulationReview(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : "수정 반영에 실패했습니다.");
    } finally {
      setReviewBusy(false);
    }
  };

  const skipContentReview = async () => {
    setReviewBusy(true);
    try {
      setContentReview(null);
      await runRegulationReview(buildPayload());
    } catch (e) {
      setError(e instanceof Error ? e.message : "규정 검토에 실패했습니다.");
    } finally {
      setReviewBusy(false);
    }
  };

  if (hydrating) {
    return (
      <div className="mx-auto max-w-[1180px] px-6 py-16 text-center text-[14px] text-slate-500">
        작성 중이던 문서를 불러오는 중…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1180px] px-6 py-6 phone:px-4 phone:py-4">
      {step === 6 ? (
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setStep(2)}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="예산 입력으로 돌아가기"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[22px] font-bold text-slate-900">운영계획서 완성</h1>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                {regulationReview && !regulationReview.ok ? "규정 검토 확인 완료" : "규정 검토 완료"}
              </span>
            </div>
            <p className="mt-0.5 text-[12px] text-slate-500">{title}</p>
          </div>
        </div>
      ) : (
        <div className="mb-4 flex items-start gap-3">
          <button
            type="button"
            onClick={() => {
              if (step === 2) setStep(1);
              else navigate("/documents/create");
            }}
            className="mt-0.5 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="이전으로 돌아가기"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-[22px] font-bold text-slate-900">{template} 작성</h1>
            <p className="mt-1 text-[13px] text-slate-500">
              {step === 2
                ? "선택한 예산 항목의 단가와 수량을 입력한 뒤 계획서를 생성합니다."
                : "기본 정보를 입력하면 계획서 초안과 PDF를 자동으로 생성합니다."}
            </p>
          </div>
        </div>
      )}

      <WizardStepper
        steps={BRIEFING_FLOW_STEPS}
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
          <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
              <p className="text-[14px] font-bold text-slate-900">행사 기본 정보</p>
              <div className="mt-4 space-y-3">
                <Field label="행사명">
                  <input
                    value={eventName}
                    onChange={(e) => setEventName(e.target.value)}
                    className="field-input"
                  />
                </Field>
                <Field label="대상">
                  <input
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    className="field-input"
                  />
                </Field>
                <Field label="참석 예정 인원">
                  <input
                    value={attendees}
                    onChange={(e) => setAttendees(e.target.value.replace(/[^\d]/g, ""))}
                    className="field-input"
                    inputMode="numeric"
                  />
                </Field>
                <Field label="일시">
                  <div className="relative">
                    <input
                      value={schedule}
                      onChange={(e) => setSchedule(e.target.value)}
                      className="field-input pr-9"
                    />
                    <Calendar className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  </div>
                </Field>
                <Field label="장소">
                  <input
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className="field-input"
                  />
                </Field>
                <Field label="주관 부서">
                  <input
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    className="field-input"
                  />
                </Field>
              </div>
            </section>

            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-[14px] font-bold text-slate-900">운영 프로그램</p>
                <button
                  type="button"
                  onClick={addProgram}
                  className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--ssu-blue)] hover:underline"
                >
                  <Plus className="h-3.5 w-3.5" /> 프로그램 추가
                </button>
              </div>

              <div className="mt-3">
                <table className="w-full min-w-[520px] text-left text-[12px]">
                  <thead>
                    <tr className="border-b border-slate-100 text-slate-500">
                      <th className="px-1 py-2 font-medium">순서</th>
                      <th className="px-1 py-2 font-medium">시간</th>
                      <th className="px-1 py-2 font-medium">프로그램 내용</th>
                      <th className="min-w-[140px] px-1 py-2 font-medium">담당자</th>
                      <th className="w-8 px-1 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {programs.map((row, idx) => (
                      <tr key={row.id} className="border-b border-slate-50">
                        <td className="px-1 py-2">
                          <span className="inline-flex items-center gap-1 text-slate-500">
                            <GripVertical className="h-3.5 w-3.5" />
                            {idx + 1}
                          </span>
                        </td>
                        <td className="px-1 py-2">
                          <div className="relative">
                            <input
                              value={row.time}
                              onChange={(e) => updateProgram(row.id, { time: e.target.value })}
                              className="field-input pr-8 text-[12px]"
                            />
                            <Clock3 className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
                          </div>
                        </td>
                        <td className="px-1 py-2">
                          <input
                            value={row.content}
                            onChange={(e) => updateProgram(row.id, { content: e.target.value })}
                            className="field-input text-[12px]"
                          />
                        </td>
                        <td className="px-1 py-2 align-top">
                          <OwnerInput
                            value={row.owner}
                            staffList={staffList}
                            active={activeOwnerId === row.id}
                            onActivate={() => setActiveOwnerId(row.id)}
                            onChange={(value) => updateProgram(row.id, { owner: value })}
                            onCommit={(name) => {
                              void saveStaffName(name).catch(() => undefined);
                            }}
                            onDeleteStaff={(id) => {
                              void deleteStaff(id).catch(async () => {
                                await loadStaff().catch(() => undefined);
                              });
                            }}
                          />
                        </td>
                        <td className="px-1 py-2">
                          <button
                            type="button"
                            onClick={() => removeProgram(row.id)}
                            className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                            aria-label="삭제"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-3 rounded-lg bg-slate-50 px-3 py-2">
                <p className="text-[11px] font-medium text-slate-500">
                  저장된 담당자
                  {activeOwnerId ? (
                    <span className="ml-1 text-[var(--ssu-blue)]">
                      (선택한 입력란에 적용됩니다)
                    </span>
                  ) : (
                    <span className="ml-1 text-slate-400">(담당자 칸을 먼저 클릭하세요)</span>
                  )}
                </p>
                {staffList.length === 0 ? (
                  <p className="mt-1 text-[11px] text-slate-400">
                    이름을 입력하면 여기에 저장되어 다시 선택할 수 있습니다.
                  </p>
                ) : (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {staffList.map((person) => (
                      <span
                        key={person.id}
                        className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-700"
                      >
                        <button
                          type="button"
                          className="hover:text-[var(--ssu-blue)]"
                          onClick={() => applyStaffToProgram(person.name)}
                        >
                          {person.name}
                        </button>
                        <button
                          type="button"
                          aria-label={`${person.name} 삭제`}
                          className="rounded-full p-0.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            void deleteStaff(person.id).catch(async () => {
                              await loadStaff().catch(() => undefined);
                            });
                          }}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </div>

          <section className="mt-4 rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
            <p className="text-[14px] font-bold text-slate-900">예산 조건</p>
            <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[280px_1fr]">
              <div>
                <label className="text-[12px] font-medium text-slate-600">총 예산 한도</label>
                <div className="relative mt-1">
                  <input
                    value={budgetLimit}
                    onChange={(e) => setBudgetLimit(formatBudgetInput(e.target.value))}
                    className="field-input pr-10 font-semibold"
                  />
                  <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-slate-500">
                    원
                  </span>
                </div>
                <p className="mt-1.5 text-[11px] text-slate-400">
                  행사 운영에 사용할 수 있는 최대 예산 금액을 입력하세요.
                </p>
              </div>
              <div>
                <p className="text-[12px] font-medium text-slate-600">예산 항목 포함 조건</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {budgetOptions.map((item) => {
                    const checked = budgetItems.includes(item);
                    const custom = !isDefaultBudgetOption(item);
                    return (
                      <label
                        key={item}
                        className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-[12px] ${
                          checked
                            ? "border-blue-200 bg-blue-50 text-blue-700"
                            : "border-slate-200 bg-white text-slate-600"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleBudgetItem(item)}
                          className="accent-[var(--ssu-blue)]"
                        />
                        {item}
                        {custom && (
                          <button
                            type="button"
                            aria-label={`${item} 항목 삭제`}
                            className="rounded p-0.5 text-slate-400 hover:bg-red-50 hover:text-red-500"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              removeBudgetOption(item);
                            }}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        )}
                      </label>
                    );
                  })}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <input
                    value={newBudgetItem}
                    onChange={(e) => setNewBudgetItem(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addBudgetOption();
                      }
                    }}
                    className="field-input max-w-[220px] text-[12px]"
                    placeholder="항목명 입력 (예: 기념품)"
                  />
                  <button
                    type="button"
                    onClick={addBudgetOption}
                    disabled={!newBudgetItem.trim()}
                    className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[12px] font-semibold text-[var(--ssu-blue)] hover:bg-blue-50 disabled:opacity-40"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    항목 추가
                  </button>
                </div>
                <p className="mt-1.5 text-[11px] text-slate-400">
                  기본 항목 외에 필요한 예산 항목을 추가한 뒤 체크하세요.
                </p>
              </div>
            </div>
          </section>

          <div className="mt-5 flex justify-end gap-2 phone:flex-col-reverse">
            <button
              type="button"
              onClick={() => navigate("/documents/create")}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700"
            >
              이전
            </button>
            <button
              type="button"
              onClick={goToBudgetStep}
              disabled={!eventName.trim()}
              className="rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
            >
              다음 (예산 입력)
            </button>
          </div>
        </>
      )}

      {step === 2 && (
        <>
          <section className="mt-6 rounded-xl border border-[var(--ssu-border)] bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <p className="text-[12px] font-medium text-slate-600">총 예산 한도</p>
                <p className="mt-1 text-[18px] font-bold text-slate-900">{won(budgetLimitNumber)}</p>
                <p className="mt-1 text-[11px] text-slate-400">
                  기본정보에서 입력한 한도입니다. 항목별 단가·수량만 수정하세요.
                </p>
              </div>
              <div className="rounded-lg bg-slate-50 px-4 py-3">
                <div className="flex justify-between text-[12px] text-slate-600">
                  <span>합계</span>
                  <span className="font-semibold text-slate-900">{won(budgetTotal)}</span>
                </div>
                <div className="mt-1 flex justify-between text-[12px] text-slate-600">
                  <span>잔여</span>
                  <span
                    className={`font-semibold ${
                      budgetRemaining < 0 ? "text-red-600" : "text-emerald-700"
                    }`}
                  >
                    {won(budgetRemaining)}
                  </span>
                </div>
              </div>
            </div>

            <p className="mt-5 text-[14px] font-bold text-slate-900">예산 항목 입력</p>
            <p className="mt-1 text-[12px] text-slate-500">
              앞에서 선택한 항목의 이름은 변경할 수 없습니다. 산출근거·단가·수량만 입력하세요.
            </p>

            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-[12px]">
                <thead>
                  <tr className="border-b border-slate-100 text-slate-500">
                    <th className="px-2 py-2 font-medium">예산 항목</th>
                    <th className="px-2 py-2 font-medium">산출 근거</th>
                    <th className="px-2 py-2 font-medium">단가</th>
                    <th className="px-2 py-2 font-medium">수량</th>
                    <th className="px-2 py-2 font-medium">금액</th>
                  </tr>
                </thead>
                <tbody>
                  {budgetLines.map((row) => (
                    <tr key={row.id} className="border-b border-slate-50">
                      <td className="px-2 py-2">
                        <div className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 font-medium text-slate-800">
                          {row.name}
                        </div>
                      </td>
                      <td className="px-2 py-2">
                        <input
                          value={row.basis}
                          onChange={(e) => updateBudgetLine(row.id, { basis: e.target.value })}
                          className="field-input"
                          placeholder="예: 50명 × 10,000원"
                        />
                      </td>
                      <td className="px-2 py-2">
                        <input
                          value={row.unit_price.toLocaleString("ko-KR")}
                          onChange={(e) =>
                            updateBudgetLine(row.id, {
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
                            updateBudgetLine(row.id, {
                              quantity: Number(e.target.value.replace(/[^\d]/g, "") || "0"),
                            })
                          }
                          className="field-input text-right"
                        />
                      </td>
                      <td className="px-2 py-2 text-right font-semibold text-slate-800">
                        {won(row.unit_price * row.quantity)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="mt-5 flex justify-end gap-2 phone:flex-col-reverse">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-[13px] font-medium text-slate-700"
            >
              이전
            </button>
            <button
              type="button"
              onClick={() => void startGeneration()}
              className="rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)]"
            >
              계획서 생성
            </button>
          </div>
        </>
      )}

      {step === 4 && pausedPhase === "content" && contentReview && (
        <ContentReviewPanel
          result={contentReview}
          busy={reviewBusy}
          onApply={(patches) => void continueContentReview(patches)}
          onSkip={() => void skipContentReview()}
        />
      )}

      {step === 5 && pausedPhase === "regulation" && regulationReview && (
        <RegulationReviewPanel
          result={regulationReview}
          busy={reviewBusy}
          onBack={() => {
            setPausedPhase(null);
            setStep(2);
          }}
          onContinue={() => {
            setPausedPhase(null);
            setStep(6);
            setLoadingLabel("");
          }}
        />
      )}

      {(step === 3 ||
        (step === 4 && pausedPhase !== "content") ||
        (step === 5 && pausedPhase !== "regulation")) && (
        <section className="mt-10 flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-[var(--ssu-border)] bg-white px-6 py-16 text-center shadow-sm">
          <LoaderCircle className="h-10 w-10 animate-spin text-[var(--ssu-blue)]" />
          <p className="mt-5 text-[16px] font-bold text-slate-900">
            {step === 3 && "계획 생성 중"}
            {step === 4 && "내용 구성 중"}
            {step === 5 && "규정 검토 중"}
          </p>
          <p className="mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
            {loadingLabel}
          </p>
          <div className="mt-6 flex gap-2">
            {STEP_LABELS.slice(3, 6).map((label, idx) => {
              const n = (idx + 3) as WizardStep;
              const active = n === step;
              const done = n < step;
              return (
                <span
                  key={label}
                  className={`rounded-full px-3 py-1 text-[11px] font-semibold ${
                    active
                      ? "bg-blue-50 text-[var(--ssu-blue)]"
                      : done
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

      {step === 6 && (
        <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_280px]">
          <section className="rounded-xl border border-[var(--ssu-border)] bg-[#f5f6f8] p-5">
            <div className="mx-auto max-w-[720px] rounded-sm bg-white px-10 py-10 shadow-sm ring-1 ring-slate-200">
              {previewUrl ? (
                <img
                  src={`${API_BASE_URL}${previewUrl}`}
                  alt="운영계획서 PDF 미리보기"
                  className="mx-auto h-auto w-full object-contain"
                />
              ) : (
                <p className="py-20 text-center text-[13px] text-slate-400">
                  미리보기를 불러오는 중입니다…
                </p>
              )}
            </div>
            <div className="mt-5 flex justify-center">
              <button
                type="button"
                onClick={() => void saveToArchive()}
                disabled={savingArchive}
                className="rounded-lg bg-[var(--ssu-blue)] px-6 py-3 text-[13px] font-semibold text-white disabled:opacity-60"
              >
                {savingArchive ? "저장 중…" : "문서 보관함에 저장"}
              </button>
            </div>
          </section>

          <aside className="space-y-4">
            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4">
              <p className="text-[13px] font-bold text-slate-900">완료 체크리스트</p>
              <ul className="mt-3 space-y-2 text-[12px] text-slate-700">
                {["기본정보 입력", "예산 입력", "계획 생성", "내용 구성", "규정 검토"].map(
                  (item) => (
                    <li key={item} className="flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-white">
                        <Check className="h-3 w-3" />
                      </span>
                      {item}
                    </li>
                  )
                )}
              </ul>
            </section>

            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4">
              <p className="text-[13px] font-bold text-slate-900">문서 정보</p>
              <dl className="mt-3 space-y-2 text-[12px]">
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">문서 유형</dt>
                  <dd className="font-medium text-slate-800">운영계획서</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">작성자</dt>
                  <dd className="font-medium text-slate-800">입학팀 담당자</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">계획서 ID</dt>
                  <dd className="font-medium text-slate-800">{planId ?? "-"}</dd>
                </div>
              </dl>
            </section>

            <section className="rounded-xl border border-[var(--ssu-border)] bg-white p-4">
              <p className="text-[13px] font-bold text-slate-900">다운로드</p>
              <div className="mt-3 grid grid-cols-3 gap-2">
                {["HWP", "Word", "PDF"].map((fmt) => (
                  <a
                    key={fmt}
                    href={fmt === "PDF" && pdfUrl ? `${API_BASE_URL}${pdfUrl}` : undefined}
                    target={fmt === "PDF" ? "_blank" : undefined}
                    rel="noreferrer"
                    className={`rounded-lg border px-2 py-3 text-center text-[12px] font-semibold ${
                      fmt === "PDF" && pdfUrl
                        ? "border-blue-200 bg-blue-50 text-[var(--ssu-blue)]"
                        : "cursor-not-allowed border-slate-200 text-slate-400"
                    }`}
                    onClick={(e) => {
                      if (!(fmt === "PDF" && pdfUrl)) e.preventDefault();
                    }}
                  >
                    <FileDown className="mx-auto mb-1 h-4 w-4" />
                    {fmt}
                  </a>
                ))}
              </div>
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
          padding: 0.55rem 0.75rem;
          font-size: 13px;
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium text-slate-600">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function OwnerInput({
  value,
  staffList,
  active,
  onActivate,
  onChange,
  onCommit,
  onDeleteStaff,
}: {
  value: string;
  staffList: StaffPerson[];
  active: boolean;
  onActivate: () => void;
  onChange: (value: string) => void;
  onCommit: (name: string) => void;
  onDeleteStaff: (id: number) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, width: 160 });

  const filtered = staffList.filter((p) =>
    value.trim() ? p.name.toLowerCase().includes(value.trim().toLowerCase()) : true
  );

  const updateMenuPos = () => {
    const el = inputRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setMenuPos({
      top: rect.bottom + 4,
      left: rect.left,
      width: Math.max(rect.width, 160),
    });
  };

  useEffect(() => {
    if (!open) return;
    updateMenuPos();
    const onScroll = () => updateMenuPos();
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, value, staffList.length]);

  useEffect(() => {
    if (!open) return;
    const onDocDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (inputRef.current?.contains(target)) return;
      const menu = document.getElementById("owner-suggest-menu");
      if (menu?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, [open]);

  const showMenu = open && filtered.length > 0;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={value}
        placeholder="이름 입력"
        onFocus={() => {
          onActivate();
          setOpen(true);
          updateMenuPos();
        }}
        onClick={() => {
          onActivate();
          setOpen(true);
          updateMenuPos();
        }}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          updateMenuPos();
        }}
        onBlur={() => {
          // 메뉴 클릭보다 먼저 blur가 뜨므로 약간 지연
          window.setTimeout(() => {
            if (value.trim()) onCommit(value);
          }, 150);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (value.trim()) {
              onCommit(value);
              setOpen(false);
            }
          }
          if (e.key === "Escape") setOpen(false);
        }}
        className={`field-input text-[12px] ${
          active ? "border-[var(--ssu-blue)] ring-2 ring-blue-100" : ""
        }`}
      />
      {showMenu &&
        createPortal(
          <ul
            id="owner-suggest-menu"
            className="fixed z-[1000] max-h-48 overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl"
            style={{ top: menuPos.top, left: menuPos.left, width: menuPos.width }}
          >
            {filtered.map((person) => (
              <li
                key={person.id}
                className="flex items-center justify-between gap-2 px-2 py-1.5 hover:bg-slate-50"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left text-[12px] text-slate-700"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onChange(person.name);
                    onCommit(person.name);
                    setOpen(false);
                  }}
                >
                  {person.name}
                </button>
                <button
                  type="button"
                  aria-label={`${person.name} 삭제`}
                  className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onDeleteStaff(person.id);
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>,
          document.body
        )}
    </div>
  );
}
