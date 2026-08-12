/** 2027학년도 숭실대 수시 — 실제 일정은 2026년에 진행 */

export type AdmissionScheduleItem = {
  /** YYYY-MM-DD */
  iso: string;
  date: string; // MM.DD
  day: string;
  title: string;
  note?: string;
  year: number;
  month: number;
};

export const ACADEMIC_YEAR_LABEL = "2027학년도";

/**
 * 2027학년도 수시 모집요강·시행계획 기준 주요 일정 (달력 연도 = 2026)
 */
export const ADMISSION_SCHEDULE_2027: AdmissionScheduleItem[] = [
  {
    iso: "2026-08-31",
    year: 2026,
    month: 8,
    date: "08.31",
    day: "월",
    title: "학생부 작성 기준일",
    note: "수시 학생부 기준",
  },
  {
    iso: "2026-09-08",
    year: 2026,
    month: 9,
    date: "09.08",
    day: "화",
    title: "수시모집 원서접수 시작",
    note: "10:00~",
  },
  {
    iso: "2026-09-11",
    year: 2026,
    month: 9,
    date: "09.11",
    day: "금",
    title: "일부 전형 서류제출 마감",
    note: "18:00",
  },
  {
    iso: "2026-09-14",
    year: 2026,
    month: 9,
    date: "09.14",
    day: "월",
    title: "원서접수·서류제출 마감",
    note: "17:00",
  },
  {
    iso: "2026-09-18",
    year: 2026,
    month: 9,
    date: "09.18",
    day: "금",
    title: "학교장 추천 입력 마감",
    note: "교과우수자 등",
  },
  {
    iso: "2026-10-03",
    year: 2026,
    month: 10,
    date: "10.03",
    day: "토",
    title: "실기·면접(예체능 등)",
    note: "전형별 상이",
  },
  {
    iso: "2026-10-13",
    year: 2026,
    month: 10,
    date: "10.13",
    day: "화",
    title: "2단계 면접·실기(일부)",
    note: "전형별 상이",
  },
  {
    iso: "2026-11-21",
    year: 2026,
    month: 11,
    date: "11.21",
    day: "토",
    title: "논술고사",
    note: "논술우수자전형",
  },
  {
    iso: "2026-11-23",
    year: 2026,
    month: 11,
    date: "11.23",
    day: "월",
    title: "1단계 합격자 발표",
    note: "면접형 등",
  },
  {
    iso: "2026-11-28",
    year: 2026,
    month: 11,
    date: "11.28",
    day: "토",
    title: "면접고사",
    note: "SSU미래인재(면접형) 등",
  },
  {
    iso: "2026-12-18",
    year: 2026,
    month: 12,
    date: "12.18",
    day: "금",
    title: "최초합격자 발표",
    note: "수시 합격 발표",
  },
  {
    iso: "2026-12-30",
    year: 2026,
    month: 12,
    date: "12.30",
    day: "수",
    title: "등록 마감",
    note: "22:00까지",
  },
];

export function sortedSchedule(items = ADMISSION_SCHEDULE_2027) {
  return [...items].sort((a, b) => a.iso.localeCompare(b.iso));
}

/** 오늘(로컬) YYYY-MM-DD */
export function todayIso(now = new Date()) {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function isPastOrToday(iso: string, today = todayIso()) {
  return iso <= today;
}

/** 가장 가까운 다가올(또는 오늘) 일정 인덱스. 전부 지났으면 마지막 */
export function nearestUpcomingIndex(items: AdmissionScheduleItem[], today = todayIso()) {
  const sorted = sortedSchedule(items);
  const idx = sorted.findIndex((s) => s.iso >= today);
  if (idx >= 0) return idx;
  return Math.max(0, sorted.length - 1);
}

/** 페이지: nearest가 가운데에 오도록 start 계산 */
export function initialPageStart(total: number, nearestIdx: number, pageSize: number) {
  if (total <= pageSize) return 0;
  const half = Math.floor(pageSize / 2);
  let start = nearestIdx - half;
  if (start < 0) start = 0;
  if (start + pageSize > total) start = total - pageSize;
  return start;
}

export function groupScheduleByMonth(items: AdmissionScheduleItem[]) {
  const sorted = sortedSchedule(items);
  const groups: { key: string; label: string; items: AdmissionScheduleItem[] }[] = [];
  for (const item of sorted) {
    const key = `${item.year}-${item.month}`;
    const label = `${item.year}년 ${item.month}월`;
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.items.push(item);
    else groups.push({ key, label, items: [item] });
  }
  return groups;
}
