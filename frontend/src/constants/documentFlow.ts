/** 행정문서 작성 플로우 공통 단계 라벨 */

export const BRIEFING_FLOW_STEPS = [
  "문서 선택",
  "기본정보 입력",
  "예산 입력",
  "계획 생성",
  "내용 구성",
  "규정 검토",
  "완성 및 저장",
] as const;

export const OUTREACH_FLOW_STEPS = [
  "문서 선택",
  "기본정보 입력",
  "계획 생성",
  "내용 구성",
  "규정 검토",
  "완성 및 저장",
] as const;

export const BUDGET_FLOW_STEPS = [
  "문서 선택",
  "예산 입력",
  "내용 점검",
  "규정 검토",
  "예산안 작성",
  "문서 완성",
] as const;

/** DocumentCreate = 1, 위저드 내부 step n → 표시 step n+1 */
export function flowStepFromWizard(wizardStep: number) {
  return wizardStep + 1;
}
