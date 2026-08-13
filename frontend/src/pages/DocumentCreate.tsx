import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ClipboardList,
  School,
  Tent,
  Mic2,
  Wallet,
  FileBarChart,
  Check,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import WizardStepper from "../components/WizardStepper";
import StepTransition from "../components/StepTransition";
import { BRIEFING_FLOW_STEPS, BUDGET_FLOW_STEPS, OUTREACH_FLOW_STEPS } from "../constants/documentFlow";

type Template = {
  id: string;
  title: string;
  desc: string;
  icon: LucideIcon;
  ready: boolean;
};

const templates: Template[] = [
  {
    id: "briefing",
    title: "입시설명회 운영계획서",
    desc: "일정·역할·예산이 포함된 설명회 운영 계획 문서를 생성합니다.",
    icon: ClipboardList,
    ready: true,
  },
  {
    id: "visit",
    title: "고교 방문 홍보계획서",
    desc: "방문 일정과 홍보 프로그램, 담당자 배정을 정리합니다.",
    icon: School,
    ready: true,
  },
  {
    id: "fair",
    title: "박람회 참가계획서",
    desc: "부스 운영·인력·홍보물 계획을 문서화합니다.",
    icon: Tent,
    ready: true,
  },
  {
    id: "interview",
    title: "면접·실기 운영 보조문서",
    desc: "운영 체크리스트와 역할 분담표를 작성합니다.",
    icon: Mic2,
    ready: false,
  },
  {
    id: "budget",
    title: "예상 예산안",
    desc: "행사 예산 항목과 산출근거를 정리한 예산안을 생성합니다.",
    icon: Wallet,
    ready: true,
  },
  {
    id: "report",
    title: "행사 결과보고서",
    desc: "행사 결과와 개선사항을 보고서로 정리합니다.",
    icon: FileBarChart,
    ready: false,
  },
];

const recent = [
  { templateId: "briefing", title: "입시설명회 운영계획서", date: "2025-05-20" },
  { templateId: "visit", title: "고교 방문 홍보계획서", date: "2025-05-15" },
  { templateId: "fair", title: "박람회 참가계획서", date: "2025-05-08" },
  { templateId: "interview", title: "면접·실기 운영 보조문서", date: "2025-04-30" },
  { templateId: "budget", title: "예상 예산안", date: "2025-04-18" },
];

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function DocumentCreate() {
  const navigate = useNavigate();
  const [selected, setSelected] = useState("briefing");
  const [comingSoonOpen, setComingSoonOpen] = useState(false);
  const [flowStep, setFlowStep] = useState(1);
  const [leaving, setLeaving] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((t) => t.id === selected) ?? templates[0],
    [selected]
  );

  const flowSteps =
    selected === "budget"
      ? BUDGET_FLOW_STEPS
      : selected === "visit" || selected === "fair"
        ? OUTREACH_FLOW_STEPS
        : BRIEFING_FLOW_STEPS;

  const goNext = async () => {
    if (!selectedTemplate.ready) {
      setComingSoonOpen(true);
      return;
    }

    setLeaving(true);
    // 1단계 완료 체크 → 2단계 하이라이트로 전환 후 이동
    setFlowStep(2);
    await sleep(420);

    if (selected === "budget") {
      navigate("/documents/create/budget", { state: { fromSelect: true } });
      return;
    }
    if (selected === "visit") {
      navigate("/documents/create/visit", { state: { fromSelect: true } });
      return;
    }
    if (selected === "fair") {
      navigate("/documents/create/fair", { state: { fromSelect: true } });
      return;
    }
    navigate(
      `/documents/create/wizard?template=${encodeURIComponent(selectedTemplate.title)}`,
      { state: { fromSelect: true } }
    );
  };

  return (
    <div className={`mx-auto max-w-[1280px] px-6 py-6 phone:px-4 phone:py-4`}>
      <h1 className="text-[24px] font-bold text-slate-900 phone:text-[20px]">행정문서 작성</h1>
      <p className="mt-1 text-[13px] text-slate-500">작성할 문서의 양식을 선택해주세요.</p>

      <WizardStepper steps={flowSteps} current={flowStep} className="mt-5" />

      <StepTransition stepKey="document-select">
        <div
          className={`mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[1fr_280px] transition-opacity duration-300 ${
            leaving ? "opacity-40" : "opacity-100"
          }`}
        >
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 phone:grid-cols-1!">
            {templates.map((tpl) => {
              const Icon = tpl.icon;
              const active = selected === tpl.id;
              return (
                <button
                  key={tpl.id}
                  type="button"
                  disabled={leaving}
                  onClick={() => setSelected(tpl.id)}
                className={`ui-surface ui-pressable relative rounded-xl border bg-white p-5 text-left ${
                  active
                    ? "border-[var(--ssu-blue)] ring-2 ring-blue-100"
                    : "border-[var(--ssu-border)] hover:border-slate-300"
                }`}
                >
                  {active && (
                    <span className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--ssu-blue)] text-white">
                      <Check className="h-3.5 w-3.5" />
                    </span>
                  )}
                  <span className="inline-flex rounded-lg bg-blue-50 p-2 text-[var(--ssu-blue)]">
                    <Icon className="h-5 w-5" />
                  </span>
                  <p className="mt-3 text-[14px] font-bold text-slate-900">{tpl.title}</p>
                  <p className="mt-1 text-[12px] leading-relaxed text-slate-500">{tpl.desc}</p>
                </button>
              );
            })}
          </div>

          <aside className="rounded-xl border border-[var(--ssu-border)] bg-white p-4">
            <p className="text-[14px] font-bold text-slate-900">최근 사용한 양식</p>
            <ul className="mt-3 space-y-2">
              {recent.map((item) => {
                const tpl = templates.find((t) => t.id === item.templateId);
                const Icon = tpl?.icon ?? ClipboardList;
                return (
                  <li key={`${item.title}-${item.date}`}>
                    <button
                      type="button"
                      disabled={leaving}
                      onClick={() => setSelected(item.templateId)}
                      className={`flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition duration-200 ${
                        selected === item.templateId
                          ? "bg-blue-50 ring-1 ring-blue-100"
                          : "bg-slate-50 hover:bg-slate-100"
                      }`}
                    >
                      <span className="mt-0.5 inline-flex shrink-0 rounded-md bg-blue-50 p-1.5 text-[var(--ssu-blue)]">
                        <Icon className="h-4 w-4" />
                      </span>
                      <span className="min-w-0">
                        <p className="text-[12px] font-bold text-slate-800">{item.title}</p>
                        <p className="mt-0.5 text-[11px] font-medium text-slate-500">
                          {item.date}
                        </p>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </aside>
        </div>
      </StepTransition>

      <div className="mt-6 flex justify-end phone:justify-stretch">
        <button
          type="button"
          disabled={leaving}
          onClick={() => void goNext()}
          className="ui-pressable rounded-lg bg-[var(--ssu-blue)] px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-[var(--ssu-blue-dark)] disabled:opacity-70 phone:w-full"
        >
          {leaving ? "이동 중…" : "다음 단계 >"}
        </button>
      </div>

      {comingSoonOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4 page-enter"
          role="dialog"
          aria-modal="true"
          aria-labelledby="coming-soon-title"
          onClick={() => setComingSoonOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p id="coming-soon-title" className="text-[16px] font-bold text-slate-900">
                  추후 개발 예정
                </p>
                <p className="mt-2 text-[13px] leading-relaxed text-slate-600">
                  <span className="font-semibold text-slate-800">{selectedTemplate.title}</span>
                  은(는) 현재 준비 중입니다. 조금만 기다려 주세요.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setComingSoonOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                aria-label="닫기"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => setComingSoonOpen(false)}
                className="rounded-lg bg-[var(--ssu-blue)] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[var(--ssu-blue-dark)]"
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
