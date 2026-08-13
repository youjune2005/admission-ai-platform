import type { ReactNode } from "react";

export default function WizardField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium text-slate-600">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
