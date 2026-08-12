export default function SettingsPage() {
  return (
    <div className="mx-auto max-w-[800px] px-6 py-6">
      <h1 className="text-[24px] font-bold text-slate-900">설정</h1>
      <p className="mt-1 text-[13px] text-slate-500">
        계정·알림·시스템 설정은 이후 단계에서 연결됩니다.
      </p>
      <div className="ui-surface mt-5 rounded-xl border border-[var(--ssu-border)] bg-white p-5 text-[13px] text-slate-600">
        <p>· 조직: 숭실대학교 입학팀</p>
        <p className="mt-2">· 기준 학년도: 2027학년도 · 수시모집</p>
        <p className="mt-2">· LLM: OpenAI (gpt-4o-mini)</p>
      </div>
    </div>
  );
}
