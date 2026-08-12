import { Check } from "lucide-react";

type WizardStepperProps = {
  steps: readonly string[];
  /** 1-based current step index */
  current: number;
  className?: string;
};

export default function WizardStepper({ steps, current, className = "" }: WizardStepperProps) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2 text-[12px] ${className}`}
      aria-label="작성 단계"
    >
      {steps.map((label, idx) => {
        const n = idx + 1;
        const done = n < current;
        const active = n === current;
        return (
          <div key={`${n}-${label}`} className="flex items-center gap-2">
            <span
              className={`ui-nav-item flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold ${
                done
                  ? "bg-emerald-500 text-white"
                  : active
                    ? "step-dot-active bg-[var(--ssu-blue)] text-white"
                    : "border border-slate-300 text-slate-400"
              }`}
            >
              {done ? (
                <Check className="step-check-pop h-3.5 w-3.5" strokeWidth={2.5} />
              ) : (
                n
              )}
            </span>
            <span
              className={`transition-colors duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                active
                  ? "font-bold text-[var(--ssu-blue)]"
                  : done
                    ? "font-semibold text-slate-700"
                    : "font-medium text-slate-400"
              }`}
            >
              {label}
            </span>
            {idx < steps.length - 1 && (
              <span
                className={`mx-1 h-0.5 w-8 rounded-full transition-colors duration-700 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                  done ? "bg-emerald-400" : "bg-slate-200"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
