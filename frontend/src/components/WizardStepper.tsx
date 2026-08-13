import { Fragment } from "react";
import { Check } from "lucide-react";

type WizardStepperProps = {
  steps: readonly string[];
  /** 1-based current step index */
  current: number;
  className?: string;
};

export default function WizardStepper({ steps, current, className = "" }: WizardStepperProps) {
  const activeLabel = steps[Math.max(0, Math.min(current, steps.length) - 1)] ?? "";

  return (
    <div className={className}>
      <div
        className="flex flex-wrap items-center gap-2 text-[12px] phone:flex-nowrap phone:gap-0"
        aria-label="작성 단계"
      >
        {steps.map((label, idx) => {
          const n = idx + 1;
          const done = n < current;
          const active = n === current;
          return (
            <Fragment key={`${n}-${label}`}>
              <div className="flex shrink-0 items-center gap-2">
                <span
                  className={`ui-nav-item flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[12px] font-bold phone:h-5 phone:w-5 phone:text-[10px] ${
                    done
                      ? "bg-emerald-500 text-white"
                      : active
                        ? "step-dot-active bg-[var(--ssu-blue)] text-white"
                        : "border border-slate-300 text-slate-400"
                  }`}
                >
                  {done ? (
                    <Check className="step-check-pop h-3.5 w-3.5 phone:h-3 phone:w-3" strokeWidth={2.5} />
                  ) : (
                    n
                  )}
                </span>
                <span
                  className={`transition-colors duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] phone:hidden! ${
                    active
                      ? "font-bold text-[var(--ssu-blue)]"
                      : done
                        ? "font-semibold text-slate-700"
                        : "font-medium text-slate-400"
                  }`}
                >
                  {label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <span
                  aria-hidden
                  className={`mx-1 h-0.5 w-8 shrink-0 rounded-full transition-colors duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] phone:mx-1.5 phone:w-auto phone:min-w-2 phone:flex-1 ${
                    done ? "bg-emerald-400" : "bg-slate-200"
                  }`}
                />
              )}
            </Fragment>
          );
        })}
      </div>
      <p className="mt-2 hidden text-[12px] font-semibold text-[var(--ssu-blue)] phone:block">
        {current}. {activeLabel}
      </p>
    </div>
  );
}
