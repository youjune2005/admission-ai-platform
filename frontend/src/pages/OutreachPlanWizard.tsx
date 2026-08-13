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
  OUTREACH_FLOW_STEPS,
  flowStepFromWizard,
} from "../constants/documentFlow";
import { asRecord, asString } from "../lib/archiveWizard";
import { applyReviewPatches } from "../lib/reviewPatches";
import type {
  ContentReviewPatch,
  ContentReviewResult,
  GeneratedDocument,
  RegulationReviewResult,
} from "../types";

export type OutreachKind = "visit" | "fair";

type ProgramRow = {
  id: string;
  time: string;
  content: string;
  owner: string;
};

type StaffPerson = {
  id: number;
  name: string;
};

type WizardStep = 1 | 2 | 3 | 4 | 5;

const STEP_LABELS = [
  "문서 선택",
  "기본정보 입력",
  "계획 생성",
  "내용 구성",
  "규정 검토",
  "완성 및 저장",
] as const;

const VISIT_DEFAULT_PROGRAMS: ProgramRow[] = [
  { id: "1", time: "14:00~14:10", content: "인사 및 대학 소개", owner: "" },
  { id: "2", time: "14:10~14:40", content: "2027학년도 전형 안내", owner: "" },
  { id: "3", time: "14:40~15:00", content: "질의응답", owner: "" },
  { id: "4", time: "15:00~15:30", content: "개별·교사 상담", owner: "" },
];

const FAIR_DEFAULT_PROGRAMS: ProgramRow[] = [
  { id: "1", time: "10:00~12:00", content: "부스 세팅 및 자료 비치", owner: "" },
  { id: "2", time: "12:00~17:00", content: "전형 상담·안내", owner: "" },
  { id: "3", time: "17:00~18:00", content: "정리 및 인수인계", owner: "" },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function OutreachPlanWizard({ kind }: { kind: OutreachKind }) {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const archiveIdParam = params.get("archiveId");
  const isVisit = kind === "visit";
  const templateTitle = isVisit ? "고교 방문 홍보계획서" : "박람회 참가계획서";
  const docTypeLabel = isVisit ? "홍보계획서" : "참가계획서";
  const apiPath = isVisit ? "/api/plans/visit" : "/api/plans/fair";

  const [step, setStep] = useState<WizardStep>(1);
  const [eventName, setEventName] = useState(
    isVisit ? "2027학년도 ○○고등학교 방문 홍보" : "2026 대입정보 박람회"
  );
  const [schoolName, setSchoolName] = useState("");
  const [region, setRegion] = useState("서울");
  const [host, setHost] = useState("한국대학교육협의회");
  const [boothNo, setBoothNo] = useState("");
  const [target, setTarget] = useState(
    isVisit ? "3학년 학생 및 진학담당 교사" : "고등학생 및 학부모"
  );
  const [attendees, setAttendees] = useState(isVisit ? "50" : "200");
  const [schedule, setSchedule] = useState(
    isVisit ? "2025-07-10 (목) 14:00 ~ 15:30" : "2025-07-25 (금) ~ 07-27 (일) 10:00 ~ 17:00"
  );
  const [location, setLocation] = useState(
    isVisit ? "시청각실" : "코엑스 홀"
  );
  const [format, setFormat] = useState("오프라인");
  const [contactTeacher, setContactTeacher] = useState("");
  const [staffCount, setStaffCount] = useState("입학팀 3명");
  const [department, setDepartment] = useState("입학팀");
  const [equipment, setEquipment] = useState("노트북, 빔프로젝터, 마이크");
  const [materials, setMaterials] = useState(
    isVisit ? "전형안내 리플렛, 모집요강" : "현수막, 리플렛, 상담일지, 명함"
  );
  const [consultingFocus, setConsultingFocus] = useState(
    "수시 전형 안내, 전년도 입시결과, 학과 상담"
  );
  const [notes, setNotes] = useState("");
  const [programs, setPrograms] = useState<ProgramRow[]>(
    isVisit ? VISIT_DEFAULT_PROGRAMS : FAIR_DEFAULT_PROGRAMS
  );
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

  const title = useMemo(
    () => `${eventName} ${docTypeLabel}`,
    [eventName, docTypeLabel]
  );

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
        setEventName(
          asString(
            p.event_name,
            isVisit ? "2027학년도 ○○고등학교 방문 홍보" : "2026 대입정보 박람회"
          )
        );
        setSchoolName(asString(p.school_name));
        setRegion(asString(p.region, "서울"));
        setHost(asString(p.host, "한국대학교육협의회"));
        setBoothNo(asString(p.booth_no));
        setTarget(
          asString(p.target, isVisit ? "3학년 학생 및 진학담당 교사" : "고등학생 및 학부모")
        );
        setAttendees(asString(p.attendees, isVisit ? "50" : "200"));
        setSchedule(asString(p.schedule));
        setLocation(asString(p.location));
        setFormat(asString(p.format, "오프라인"));
        setContactTeacher(asString(p.contact_teacher));
        setStaffCount(asString(p.staff_count, "입학팀 3명"));
        setDepartment(asString(p.department, "입학팀"));
        setEquipment(asString(p.equipment, "노트북, 빔프로젝터, 마이크"));
        setMaterials(asString(p.materials));
        setConsultingFocus(asString(p.consulting_focus));
        setNotes(asString(p.notes));
        const programRows: ProgramRow[] = Array.isArray(p.programs)
          ? p.programs.flatMap((row, idx) => {
              const rec = asRecord(row);
              if (!rec) return [];
              return [
                {
                  id: `resume-${idx}`,
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
  }, [archiveIdParam, isVisit]);

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
      { id, time: "15:30~16:00", content: "", owner: "" },
    ]);
    setActiveOwnerId(id);
  };

  const removeProgram = (id: string) => {
    setPrograms((prev) => (prev.length <= 1 ? prev : prev.filter((row) => row.id !== id)));
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

  const reviewKind = isVisit ? "visit" : "fair";

  const buildPayload = () => {
    const basePrograms = programs.map(({ time, content, owner }) => ({
      time,
      content,
      owner,
    }));
    const payload = isVisit
      ? {
          event_name: eventName.trim(),
          school_name: schoolName.trim(),
          region: region.trim(),
          target: target.trim(),
          attendees: attendees.trim() || "50",
          schedule: schedule.trim(),
          location: location.trim(),
          format: format.trim() || "오프라인",
          contact_teacher: contactTeacher.trim(),
          department: department.trim() || "입학팀",
          equipment: equipment.trim(),
          materials: materials.trim(),
          notes: notes.trim(),
          programs: basePrograms,
        }
      : {
          event_name: eventName.trim(),
          host: host.trim(),
          booth_no: boothNo.trim(),
          target: target.trim(),
          attendees: attendees.trim() || "200",
          schedule: schedule.trim(),
          location: location.trim(),
          staff_count: staffCount.trim(),
          department: department.trim() || "입학팀",
          materials: materials.trim(),
          consulting_focus: consultingFocus.trim(),
          notes: notes.trim(),
          programs: basePrograms,
        };
    return { ...payload, archive_id: archiveId };
  };

  const applyOutreachPayload = (p: Record<string, unknown>) => {
    setEventName(asString(p.event_name, eventName));
    setSchoolName(asString(p.school_name, schoolName));
    setRegion(asString(p.region, region));
    setHost(asString(p.host, host));
    setBoothNo(asString(p.booth_no, boothNo));
    setTarget(asString(p.target, target));
    setAttendees(asString(p.attendees, attendees));
    setSchedule(asString(p.schedule, schedule));
    setLocation(asString(p.location, location));
    setFormat(asString(p.format, format));
    setContactTeacher(asString(p.contact_teacher, contactTeacher));
    setStaffCount(asString(p.staff_count, staffCount));
    setDepartment(asString(p.department, department));
    setEquipment(asString(p.equipment, equipment));
    setMaterials(asString(p.materials, materials));
    setConsultingFocus(asString(p.consulting_focus, consultingFocus));
    setNotes(asString(p.notes, notes));
    const programRows: ProgramRow[] = Array.isArray(p.programs)
      ? p.programs.flatMap((row, idx) => {
          const rec = asRecord(row);
          if (!rec) return [];
          return [
            {
              id: programs[idx]?.id ?? `patched-${idx}`,
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
    }>(apiPath, payload);
    setPlanId(data.id);
    setArchiveId(data.archive_id ?? null);
    setPdfUrl(data.pdf_url);
    setPreviewUrl(data.preview_url);
    await loadStaff();
  };

  const runRegulationReview = async (payload: ReturnType<typeof buildPayload>) => {
    setPausedPhase(null);
    setStep(4);
    setLoadingLabel("관련 규정을 검토하고 있습니다…");
    const { archive_id: _aid, ...reviewPayload } = payload;
    const { data } = await apiClient.post<RegulationReviewResult>("/api/plans/review/regulations", {
      kind: reviewKind,
      payload: reviewPayload,
    });
    setRegulationReview(data);
    if (!data.ok && data.findings.length > 0) {
      setPausedPhase("regulation");
      setLoadingLabel("");
      return;
    }
    setStep(5);
    setLoadingLabel("");
  };

  const runContentReview = async (payload: ReturnType<typeof buildPayload>) => {
    setPausedPhase(null);
    setStep(3);
    setLoadingLabel("입력하신 정보로 문서 내용을 구성하고 있습니다…");
    const { archive_id: _aid, ...reviewPayload } = payload;
    const { data } = await apiClient.post<ContentReviewResult>("/api/plans/review/consistency", {
      kind: reviewKind,
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
    const payload = buildPayload();
    try {
      setStep(2);
      setLoadingLabel("계획안을 생성하고 있습니다…");
      const apiPromise = generatePlan(payload);
      await sleep(1200);
      await apiPromise;
      await runContentReview(payload);
    } catch (e) {
      setStep(1);
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
        applyOutreachPayload(patched);
        payload = { ...patched, archive_id };
        setPausedPhase(null);
        setStep(2);
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
      {step === 5 ? (
        <div className="mb-4 flex items-center gap-3">
          <button
            type="button"
            onClick={() => setStep(1)}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="기본정보로 돌아가기"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[22px] font-bold text-slate-900">{docTypeLabel} 완성</h1>
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
            onClick={() => navigate("/documents/create")}
            className="mt-0.5 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            aria-label="문서 선택으로 돌아가기"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-[22px] font-bold text-slate-900">{templateTitle} 작성</h1>
            <p className="mt-1 text-[13px] text-slate-500">
              기본 정보를 입력하면 계획서 초안과 PDF를 자동으로 생성합니다. (예산 항목 없음)
            </p>
          </div>
        </div>
      )}

      <WizardStepper
        steps={OUTREACH_FLOW_STEPS}
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
                <p className="text-[14px] font-bold text-slate-900">
                  {isVisit ? "방문 기본 정보" : "박람회 기본 정보"}
                </p>
                <div className="mt-4 space-y-3">
                  <Field label={isVisit ? "계획명" : "박람회명"}>
                    <input
                      value={eventName}
                      onChange={(e) => setEventName(e.target.value)}
                      className="field-input"
                    />
                  </Field>
                  {isVisit ? (
                    <>
                      <Field label="방문 고교명">
                        <input
                          value={schoolName}
                          onChange={(e) => setSchoolName(e.target.value)}
                          className="field-input"
                          placeholder="예: ○○고등학교"
                        />
                      </Field>
                      <Field label="지역">
                        <input
                          value={region}
                          onChange={(e) => setRegion(e.target.value)}
                          className="field-input"
                        />
                      </Field>
                    </>
                  ) : (
                    <>
                      <Field label="주최·주관">
                        <input
                          value={host}
                          onChange={(e) => setHost(e.target.value)}
                          className="field-input"
                        />
                      </Field>
                      <Field label="부스 번호">
                        <input
                          value={boothNo}
                          onChange={(e) => setBoothNo(e.target.value)}
                          className="field-input"
                          placeholder="예: A-12"
                        />
                      </Field>
                    </>
                  )}
                  <Field label="대상">
                    <input
                      value={target}
                      onChange={(e) => setTarget(e.target.value)}
                      className="field-input"
                    />
                  </Field>
                  <Field label={isVisit ? "예상 참석 인원" : "예상 상담 인원"}>
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
                  <Field label={isVisit ? "장소" : "개최 장소"}>
                    <input
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      className="field-input"
                    />
                  </Field>
                  {isVisit ? (
                    <>
                      <Field label="진행 형태">
                        <select
                          value={format}
                          onChange={(e) => setFormat(e.target.value)}
                          className="field-input"
                        >
                          <option value="오프라인">오프라인</option>
                          <option value="온라인">온라인</option>
                        </select>
                      </Field>
                      <Field label="고교 담당교사">
                        <input
                          value={contactTeacher}
                          onChange={(e) => setContactTeacher(e.target.value)}
                          className="field-input"
                          placeholder="성명"
                        />
                      </Field>
                    </>
                  ) : (
                    <Field label="배치 인력">
                      <input
                        value={staffCount}
                        onChange={(e) => setStaffCount(e.target.value)}
                        className="field-input"
                      />
                    </Field>
                  )}
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
                  <p className="text-[14px] font-bold text-slate-900">
                    {isVisit ? "운영 프로그램" : "부스 운영 일정"}
                  </p>
                  <button
                    type="button"
                    onClick={addProgram}
                    className="inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--ssu-blue)] hover:underline"
                  >
                    <Plus className="h-3.5 w-3.5" /> 항목 추가
                  </button>
                </div>

                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[520px] text-left text-[12px]">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-500">
                        <th className="px-1 py-2 font-medium">순서</th>
                        <th className="px-1 py-2 font-medium">시간</th>
                        <th className="px-1 py-2 font-medium">내용</th>
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
                              onChange={(e) =>
                                updateProgram(row.id, { content: e.target.value })
                              }
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
              <p className="text-[14px] font-bold text-slate-900">준비사항</p>
              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                {isVisit ? (
                  <>
                    <Field label="필요 장비">
                      <input
                        value={equipment}
                        onChange={(e) => setEquipment(e.target.value)}
                        className="field-input"
                        placeholder="노트북, 빔, 마이크 등"
                      />
                    </Field>
                    <Field label="홍보·배포 자료">
                      <input
                        value={materials}
                        onChange={(e) => setMaterials(e.target.value)}
                        className="field-input"
                      />
                    </Field>
                  </>
                ) : (
                  <>
                    <Field label="홍보물·준비물">
                      <input
                        value={materials}
                        onChange={(e) => setMaterials(e.target.value)}
                        className="field-input"
                      />
                    </Field>
                    <Field label="상담 중점 내용">
                      <input
                        value={consultingFocus}
                        onChange={(e) => setConsultingFocus(e.target.value)}
                        className="field-input"
                      />
                    </Field>
                  </>
                )}
                <div className="md:col-span-2">
                  <Field label={isVisit ? "요청·특이사항" : "기타사항"}>
                    <textarea
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      className="field-input min-h-[72px] resize-y"
                      placeholder="일정 조율, 주차, 안전 등"
                    />
                  </Field>
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
                onClick={() => void startGeneration()}
                disabled={!eventName.trim()}
                className="rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] disabled:opacity-50"
              >
                계획서 생성
              </button>
            </div>
          </>
        )}

        {step === 3 && pausedPhase === "content" && contentReview && (
          <ContentReviewPanel
            result={contentReview}
            busy={reviewBusy}
            onApply={(patches) => void continueContentReview(patches)}
            onSkip={() => void skipContentReview()}
          />
        )}

        {step === 4 && pausedPhase === "regulation" && regulationReview && (
          <RegulationReviewPanel
            result={regulationReview}
            busy={reviewBusy}
            onBack={() => {
              setPausedPhase(null);
              setStep(1);
            }}
            onContinue={() => {
              setPausedPhase(null);
              setStep(5);
              setLoadingLabel("");
            }}
          />
        )}

        {(step === 2 ||
          (step === 3 && pausedPhase !== "content") ||
          (step === 4 && pausedPhase !== "regulation")) && (
          <section className="mt-10 flex min-h-[360px] flex-col items-center justify-center rounded-xl border border-[var(--ssu-border)] bg-white px-6 py-16 text-center shadow-sm">
            <LoaderCircle className="h-10 w-10 animate-spin text-[var(--ssu-blue)]" />
            <p className="mt-5 text-[16px] font-bold text-slate-900">
              {step === 2 && "계획 생성 중"}
              {step === 3 && "내용 구성 중"}
              {step === 4 && "규정 검토 중"}
            </p>
            <p className="mt-2 max-w-md text-[13px] leading-relaxed text-slate-500">
              {loadingLabel}
            </p>
            <div className="mt-6 flex gap-2">
            {STEP_LABELS.slice(2, 5).map((label, idx) => {
              const n = (idx + 2) as WizardStep;
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

        {step === 5 && (
          <div className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[1fr_280px]">
            <section className="rounded-xl border border-[var(--ssu-border)] bg-[#f5f6f8] p-5">
              <div className="mx-auto max-w-[720px] rounded-sm bg-white px-10 py-10 shadow-sm ring-1 ring-slate-200">
                {previewUrl ? (
                  <img
                    src={`${API_BASE_URL}${previewUrl}`}
                    alt={`${docTypeLabel} PDF 미리보기`}
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
                  {["기본정보 입력", "계획 생성", "내용 구성", "규정 검토", "표절·형식 점검"].map(
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
                    <dd className="font-medium text-slate-800">{docTypeLabel}</dd>
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
      const menu = document.getElementById("owner-suggest-menu-outreach");
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
            id="owner-suggest-menu-outreach"
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
