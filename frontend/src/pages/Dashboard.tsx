import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  MessageSquare,
  FilePenLine,
  FileText,
  CheckCircle2,
  UserRound,
  BookOpen,
  ChevronRight,
  ChevronLeft,
  X,
} from "lucide-react";
import { apiClient } from "../api/client";
import {
  ACADEMIC_YEAR_LABEL,
  ADMISSION_SCHEDULE_2027,
  groupScheduleByMonth,
  initialPageStart,
  nearestUpcomingIndex,
  sortedSchedule,
  todayIso,
  type AdmissionScheduleItem,
} from "../constants/admissionSchedule";
import { formatKstDateTimeDash } from "../lib/datetime";

const PAGE_SIZE = 5;

type HomeKpi = {
  value: number;
  delta: number;
  delta_label: string;
  trend: string;
};

type KpiCard = {
  key: keyof typeof DEFAULT_KPIS;
  label: string;
  value: number;
  unit: string;
  delta: string;
  deltaClass: string;
  icon: LucideIcon;
  iconClass: string;
};

const DEFAULT_KPIS: Record<string, HomeKpi> = {
  today_received: { value: 0, delta: 0, delta_label: "어제 대비 ±0건", trend: "flat" },
  draft_completed: { value: 0, delta: 0, delta_label: "어제 대비 ±0건", trend: "flat" },
  needs_review: { value: 0, delta: 0, delta_label: "어제 대비 ±0건", trend: "flat" },
  regulation_review: { value: 0, delta: 0, delta_label: "어제 대비 ±0건", trend: "flat" },
};

const KPI_META: Array<{
  key: keyof typeof DEFAULT_KPIS;
  label: string;
  unit: string;
  icon: LucideIcon;
  iconClass: string;
}> = [
  {
    key: "today_received",
    label: "오늘 접수 문의",
    unit: "건",
    icon: FileText,
    iconClass: "bg-[#E8F1FF] text-[#2F6BFF]",
  },
  {
    key: "draft_completed",
    label: "답변 초안 완료",
    unit: "건",
    icon: CheckCircle2,
    iconClass: "bg-[#E8F8EF] text-[#12B76A]",
  },
  {
    key: "needs_review",
    label: "담당자 확인 필요",
    unit: "건",
    icon: UserRound,
    iconClass: "bg-[#FFF4E8] text-[#F79009]",
  },
  {
    key: "regulation_review",
    label: "규정 검토 필요",
    unit: "건",
    icon: BookOpen,
    iconClass: "bg-[#F3E8FF] text-[#7A5AF8]",
  },
];

function trendClass(trend: string, key: string) {
  if (trend === "up") {
    if (key === "needs_review") return "text-orange-600";
    if (key === "draft_completed") return "text-emerald-600";
    if (key === "regulation_review") return "text-violet-600";
    return "text-blue-600";
  }
  if (trend === "down") {
    if (key === "needs_review") return "text-emerald-600";
    return "text-slate-500";
  }
  return "text-slate-500";
}

const priorityTasks = [
  {
    badge: "담당자 확인 필요",
    badgeClass: "bg-orange-50 text-orange-700",
    title: "학생부종합/교과 동시지원 가능 여부 문의",
    meta: "김○○ · 학부모 · 오늘 09:42",
    action: "답변 초안 작성됨",
    actionClass: "border-blue-200 bg-blue-50 text-blue-700",
  },
  {
    badge: "규정 검토 필요",
    badgeClass: "bg-rose-50 text-rose-700",
    title: "수시 입시설명회 운영계획서 예산 항목 검토",
    meta: "입학팀 · 행정문서 · 어제 17:20",
    action: "규정 검토 대기",
    actionClass: "border-violet-200 bg-violet-50 text-violet-700",
  },
  {
    badge: "담당자 확인 필요",
    badgeClass: "bg-orange-50 text-orange-700",
    title: "논술우수자전형 수능최저 적용 기준 문의",
    meta: "이○○ · 학생 · 어제 15:08",
    action: "답변 초안 작성됨",
    actionClass: "border-blue-200 bg-blue-50 text-blue-700",
  },
];

type RecentDoc = {
  id: number;
  name: string;
  type: string;
  updated: string | null;
  status: string;
  status_key?: string;
};

type FaqItem = {
  label: string;
  count: number;
};

function statusClass(statusKey?: string, label?: string) {
  const key = statusKey || "";
  if (key === "approved" || label?.includes("승인")) return "bg-emerald-50 text-emerald-700";
  if (key === "archived" || label?.includes("보관") || label?.includes("게시"))
    return "bg-blue-50 text-blue-700";
  if (key === "review" || label?.includes("검토") || label?.includes("확인"))
    return "bg-orange-50 text-orange-700";
  if (key === "draft" || label?.includes("작성") || label?.includes("초안"))
    return "bg-slate-100 text-slate-600";
  return "bg-slate-100 text-slate-600";
}

function formatUpdated(value: string | null) {
  if (!value) return "-";
  return formatKstDateTimeDash(value, value.slice(0, 10));
}

const FALLBACK_DOCS: RecentDoc[] = [
  {
    id: 1,
    name: "수시 입시설명회 운영계획서.pdf",
    type: "계획서",
    updated: "2026-05-20T14:30:00",
    status: "승인 완료",
    status_key: "approved",
  },
  {
    id: 2,
    name: "고교 방문 홍보계획서.pdf",
    type: "계획서",
    updated: "2026-05-18T11:05:00",
    status: "직원 확인 필요",
    status_key: "review",
  },
  {
    id: 3,
    name: "예상 예산안.pdf",
    type: "예산안",
    updated: "2026-05-15T16:20:00",
    status: "보관 완료",
    status_key: "archived",
  },
];

/** 실문의가 없을 때 보여줄 유형 라벨(건수는 0). 가짜 건수를 넣으면 최근 문의와 어긋나 보임. */
const EMPTY_FAQ: FaqItem[] = [
  { label: "수능최저학력기준", count: 0 },
  { label: "학생부 반영방법", count: 0 },
  { label: "전형별 지원자격", count: 0 },
  { label: "제출서류 안내", count: 0 },
  { label: "면접고사 안내", count: 0 },
];

function ScheduleTimeline({
  items,
  nearestIso,
  fill = false,
}: {
  items: AdmissionScheduleItem[];
  nearestIso: string;
  /** true면 부모 높이를 5등분해서 채움 */
  fill?: boolean;
}) {
  return (
    <ul className={`relative ${fill ? "flex h-full flex-col" : ""}`}>
      {items.map((item, idx) => {
        const past = item.iso < nearestIso;
        const nearest = item.iso === nearestIso;
        const hasNext = idx < items.length - 1;
        return (
          <li
            key={`${item.iso}-${item.title}`}
            className={`relative flex items-center rounded-md ${
              fill ? "min-h-0 flex-1" : "h-[34px]"
            } ${nearest ? "bg-blue-50 ring-1 ring-blue-100" : ""}`}
          >
            <div className="flex w-11 shrink-0 items-center justify-center text-center">
              <div>
                <p
                  className={`font-bold leading-none ${
                    nearest ? "text-[13px] text-blue-700" : "text-[11px] text-slate-800"
                  }`}
                >
                  {item.date}
                </p>
                <p
                  className={`mt-0.5 leading-none text-slate-500 ${
                    nearest ? "text-[10px] font-semibold" : "text-[9px]"
                  }`}
                >
                  {item.day}
                </p>
              </div>
            </div>

            <div className="relative flex w-4 shrink-0 items-center justify-center self-stretch">
              {/* 점 아래→다음 점까지 회색 선 (점 위로는 그리지 않음) */}
              {hasNext && (
                <span
                  aria-hidden
                  className="pointer-events-none absolute left-1/2 top-1/2 z-0 w-px -translate-x-1/2 bg-slate-300"
                  style={{ height: fill ? "100%" : 34 }}
                />
              )}
              <span
                className={`relative z-[1] h-2.5 w-2.5 shrink-0 rounded-full ring-2 ${
                  nearest ? "ring-blue-50" : "ring-white"
                } ${nearest || past ? "bg-[var(--ssu-blue)]" : "bg-slate-300"}`}
              />
            </div>

            <div className="min-w-0 flex-1 pr-1.5">
              <p
                className={`truncate leading-tight font-semibold ${
                  nearest ? "text-[13px] text-blue-800" : "text-[11px] text-slate-800"
                }`}
              >
                {item.title}
              </p>
              {item.note && (
                <p
                  className={`truncate leading-tight text-slate-500 ${
                    nearest ? "text-[11px] font-medium" : "text-[10px]"
                  }`}
                >
                  {item.note}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const allSchedule = useMemo(() => sortedSchedule(ADMISSION_SCHEDULE_2027), []);
  const today = todayIso();
  const nearestIdx = useMemo(
    () => nearestUpcomingIndex(allSchedule, today),
    [allSchedule, today]
  );
  const nearestIso = allSchedule[nearestIdx]?.iso ?? "";

  const [pageStart, setPageStart] = useState(() =>
    initialPageStart(allSchedule.length, nearestIdx, PAGE_SIZE)
  );
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [recentDocs, setRecentDocs] = useState<RecentDoc[]>(FALLBACK_DOCS);
  const [faqBars, setFaqBars] = useState<FaqItem[]>(EMPTY_FAQ);
  const [faqTotal, setFaqTotal] = useState(0);
  const [faqLive, setFaqLive] = useState(false);
  const [kpiMap, setKpiMap] = useState<Record<string, HomeKpi>>(DEFAULT_KPIS);

  const kpiCards: KpiCard[] = useMemo(
    () =>
      KPI_META.map((meta) => {
        const live = kpiMap[meta.key] ?? DEFAULT_KPIS[meta.key];
        return {
          ...meta,
          value: live.value,
          delta: live.delta_label,
          deltaClass: trendClass(live.trend, meta.key),
        };
      }),
    [kpiMap],
  );

  const pageItems = allSchedule.slice(pageStart, pageStart + PAGE_SIZE);
  const pageYear = pageItems[0]?.year ?? 2026;
  const canPrev = pageStart > 0;
  const canNext = pageStart + PAGE_SIZE < allSchedule.length;

  const goNext = () => {
    if (!canNext) return;
    setPageStart(pageStart + PAGE_SIZE);
  };

  const goPrev = () => {
    if (!canPrev) return;
    setPageStart(Math.max(0, pageStart - PAGE_SIZE));
  };

  const monthGroups = useMemo(() => groupScheduleByMonth(allSchedule), [allSchedule]);

  useEffect(() => {
    apiClient
      .get<{
        kpis?: Record<string, HomeKpi>;
        recent_documents: RecentDoc[];
        faq_topics: { total: number; items: FaqItem[] };
      }>("/api/dashboard/home")
      .then((res) => {
        if (res.data.kpis) {
          setKpiMap(res.data.kpis);
        }
        if (res.data.recent_documents?.length) {
          setRecentDocs(res.data.recent_documents.slice(0, 3));
        }
        const faq = res.data.faq_topics;
        if (faq?.total > 0 && faq.items?.length) {
          setFaqBars(faq.items.slice(0, 5));
          setFaqTotal(faq.total);
          setFaqLive(true);
        } else {
          setFaqBars(EMPTY_FAQ);
          setFaqTotal(0);
          setFaqLive(false);
        }
      })
      .catch(() => {
        // 홈 요약 실패 시 FAQ만이라도 별도 조회
        apiClient
          .get<{ total: number; items: FaqItem[] }>("/api/dashboard/faq-topics", {
            params: { days: 7, limit: 6 },
          })
          .then((res) => {
            if (res.data.total > 0 && res.data.items?.length) {
              setFaqBars(res.data.items.slice(0, 5));
              setFaqTotal(res.data.total);
              setFaqLive(true);
            }
          })
          .catch(() => undefined);
      });
  }, []);

  useEffect(() => {
    if (!scheduleOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setScheduleOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [scheduleOpen]);

  const maxFaq = Math.max(1, ...faqBars.map((f) => f.count));

  return (
    <div className="mx-auto flex h-full max-w-[1280px] flex-col overflow-hidden px-6 py-4 phone:h-auto phone:overflow-visible phone:px-4 phone:py-4">
      <div className="mb-4 flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-[24px] font-bold tracking-tight text-slate-900 phone:text-[20px]">
            안녕하세요, 입학팀 담당자님
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            오늘의 입시행정 업무 현황을 한눈에 확인하세요.
          </p>
        </div>
        <div className="flex gap-2 phone:w-full">
          <button
            type="button"
            onClick={() => navigate("/inquiry")}
            className="ui-pressable inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-navy)] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-navy-hover)] phone:flex-1 phone:justify-center"
          >
            <MessageSquare className="h-4 w-4" />
            문의 답변 생성
          </button>
          <button
            type="button"
            onClick={() => navigate("/documents/create")}
            className="ui-pressable inline-flex items-center gap-2 rounded-lg bg-[var(--ssu-blue)] px-4 py-2.5 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)] phone:flex-1 phone:justify-center"
          >
            <FilePenLine className="h-4 w-4" />
            행정문서 작성
          </button>
        </div>
      </div>

      <div className="mb-4 grid shrink-0 grid-cols-2 gap-3 xl:grid-cols-4 phone:gap-2">
        {kpiCards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className="ui-surface rounded-xl border border-[var(--ssu-border)] bg-white px-4 py-4 phone:px-3 phone:py-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-slate-500">{card.label}</p>
                  <p className="mt-2 text-[28px] font-bold leading-none tracking-tight text-slate-900 phone:text-[22px]">
                    {card.value}
                    <span className="ml-1 text-[14px] font-semibold text-slate-500">{card.unit}</span>
                  </p>
                  <p className={`mt-2 text-[12px] font-medium ${card.deltaClass}`}>{card.delta}</p>
                </div>
                <span
                  className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl phone:h-9 phone:w-9 ${card.iconClass}`}
                >
                  <Icon className="h-6 w-6" strokeWidth={2} aria-hidden />
                </span>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mb-2 grid min-h-0 flex-[1.1] grid-cols-1 gap-2 xl:grid-cols-[1.4fr_1fr] phone:flex-none">
        <section className="ui-surface flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white p-2.5 phone:min-h-0 phone:overflow-visible">
          <div className="mb-1.5 flex shrink-0 items-center justify-between">
            <h2 className="text-[13px] font-bold text-slate-900">우선 확인이 필요한 업무</h2>
            <button
              type="button"
              onClick={() => navigate("/inquiry")}
              className="inline-flex items-center gap-0.5 text-[11px] font-medium text-[var(--ssu-blue)] hover:underline"
            >
              전체 보기 <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <ul className="min-h-0 flex-1 space-y-1 overflow-hidden phone:overflow-visible">
            {priorityTasks.map((task) => (
              <li
                key={task.title}
                className="flex items-center justify-between gap-2 rounded-lg border border-slate-100 px-2 py-1.5 phone:flex-col phone:items-start"
              >
                <div className="min-w-0">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${task.badgeClass}`}
                  >
                    {task.badge}
                  </span>
                  <p className="mt-0.5 truncate text-[12px] font-semibold text-slate-800">
                    {task.title}
                  </p>
                  <p className="text-[10px] text-slate-500">{task.meta}</p>
                </div>
                <button
                  type="button"
                  className={`ui-pressable shrink-0 rounded-md border px-2 py-1 text-[10px] font-semibold phone:mt-1 ${task.actionClass}`}
                >
                  {task.action}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="ui-surface flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white p-2.5 phone:overflow-visible">
          <div className="mb-1 flex shrink-0 items-center justify-between">
            <h2 className="text-[13px] font-bold text-slate-900">입시 일정</h2>
            <button
              type="button"
              onClick={() => setScheduleOpen(true)}
              className="inline-flex items-center gap-0.5 text-[11px] font-medium text-[var(--ssu-blue)] hover:underline"
            >
              전체 일정 보기 <ChevronRight className="h-3 w-3" />
            </button>
          </div>

          <div className="mb-1 flex shrink-0 items-center justify-between">
            <button
              type="button"
              className="ui-pressable rounded-md p-0.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-30"
              disabled={!canPrev}
              onClick={goPrev}
              aria-label="이전 일정"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <p className="text-[12px] font-bold text-slate-700">{pageYear}</p>
            <button
              type="button"
              className="ui-pressable rounded-md p-0.5 text-slate-400 hover:bg-slate-50 hover:text-slate-700 disabled:opacity-30"
              disabled={!canNext}
              onClick={goNext}
              aria-label="다음 일정"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>

          <div className="min-h-0 flex-1 phone:h-[210px]">
            <ScheduleTimeline items={pageItems} nearestIso={nearestIso} fill />
          </div>
        </section>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-2 xl:grid-cols-[1.4fr_1fr] phone:flex-none">
        <section className="ui-surface flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white p-2.5 phone:overflow-visible">
          <div className="mb-1 flex shrink-0 items-center justify-between">
            <h2 className="text-[13px] font-bold text-slate-900">최근 생성 문서</h2>
            <button
              type="button"
              onClick={() => navigate("/archive")}
              className="inline-flex items-center gap-0.5 text-[11px] font-medium text-[var(--ssu-blue)] hover:underline"
            >
              전체 보기 <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden phone:overflow-x-auto">
            <table className="w-full text-left text-[11px] phone:min-w-[480px]">
              <thead>
                <tr className="border-b border-slate-200 text-[10px] text-slate-500">
                  <th className="pb-1 font-medium">문서명</th>
                  <th className="pb-1 font-medium">문서 유형</th>
                  <th className="pb-1 font-medium">최종 업데이트</th>
                  <th className="pb-1 font-medium">상태</th>
                </tr>
              </thead>
              <tbody>
                {recentDocs.slice(0, 3).map((doc) => (
                  <tr
                    key={`${doc.id}-${doc.name}`}
                    className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
                    onClick={() => navigate("/archive")}
                  >
                    <td className="py-1.5 font-semibold text-slate-800">{doc.name}</td>
                    <td className="py-1.5 text-slate-600">{doc.type}</td>
                    <td className="py-1.5 text-slate-600">{formatUpdated(doc.updated)}</td>
                    <td className="py-1.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${statusClass(
                          doc.status_key,
                          doc.status
                        )}`}
                      >
                        {doc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="ui-surface flex min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white p-2.5 phone:overflow-visible">
          <div className="mb-1 flex shrink-0 items-center justify-between">
            <h2 className="text-[13px] font-bold text-slate-900">자주 들어오는 문의</h2>
            <button
              type="button"
              onClick={() => navigate("/inquiry")}
              className="inline-flex items-center gap-0.5 text-[11px] font-medium text-[var(--ssu-blue)] hover:underline"
            >
              전체 보기 <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <ul className="min-h-0 flex-1 space-y-1.5 overflow-hidden">
            {faqLive ? (
              faqBars.slice(0, 5).map((item) => (
                <li key={item.label}>
                  <div className="mb-0.5 flex items-center justify-between text-[11px]">
                    <span className="font-medium text-slate-700">{item.label}</span>
                    <span className="font-semibold text-slate-500">{item.count}건</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-[var(--ssu-blue)] transition-[width] duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]"
                      style={{
                        width: `${item.count === 0 ? 0 : Math.max(8, (item.count / maxFaq) * 100)}%`,
                      }}
                    />
                  </div>
                </li>
              ))
            ) : (
              <li className="flex h-full items-center justify-center text-[12px] text-slate-400">
                아직 집계할 문의가 없습니다
              </li>
            )}
          </ul>
          <p className="mt-1 shrink-0 text-[10px] text-slate-400">
            {faqLive
              ? `최근 7일 문의 ${faqTotal}건 · 입시 문의 답변과 동일 데이터`
              : "입시 문의 답변에서 생성되면 여기에 집계됩니다"}
          </p>
        </section>
      </div>

      {scheduleOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4 soft-fade-in phone:items-end phone:px-0"
          role="dialog"
          aria-modal="true"
          aria-labelledby="schedule-modal-title"
          onClick={() => setScheduleOpen(false)}
        >
          <div
            className="dropdown-enter flex max-h-[86vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl phone:max-h-[80vh] phone:rounded-b-none"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <p id="schedule-modal-title" className="text-[16px] font-bold text-slate-900">
                  {ACADEMIC_YEAR_LABEL} 입시 일정
                </p>
                <p className="mt-0.5 text-[12px] text-slate-500">
                  수시 모집요강 기준 · 달력 연도 {pageYear}년 진행
                </p>
              </div>
              <button
                type="button"
                onClick={() => setScheduleOpen(false)}
                className="ui-pressable rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
              {monthGroups.map((group) => (
                <div key={group.key} className="mb-5 last:mb-0">
                  <p className="mb-2 text-[12px] font-bold text-slate-500">{group.label}</p>
                  <ScheduleTimeline items={group.items} nearestIso={nearestIso} />
                </div>
              ))}
            </div>

            <div className="shrink-0 border-t border-slate-100 px-5 py-3 text-[11px] text-slate-400">
              지난 일정은 파란 점 · 가장 가까운 일정은 파란 칸 · 이후 일정은 회색 점
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
