import type { ReactNode } from "react";

type StepTransitionProps = {
  stepKey: string | number;
  children: ReactNode;
  className?: string;
};

/** 단계가 바뀔 때마다 패널을 다시 마운트해 fade/slide 피드백을 줍니다. */
export default function StepTransition({
  stepKey,
  children,
  className = "",
}: StepTransitionProps) {
  return (
    <div key={stepKey} className={`step-panel step-panel-in ${className}`}>
      {children}
    </div>
  );
}
