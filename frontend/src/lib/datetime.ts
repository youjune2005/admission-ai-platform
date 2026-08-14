/** API naive datetime(= KST 벽시계)를 Asia/Seoul로 표시합니다. */

const HAS_TZ = /(Z|[+-]\d{2}:?\d{2})$/;

/** API/ISO 문자열을 Date로 파싱. 타임존 없으면 KST(+09:00)로 해석. */
export function parseApiDate(value?: string | null): Date | null {
  if (!value) return null;
  const raw = value.trim();
  if (!raw) return null;
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const withTz = HAS_TZ.test(normalized) ? normalized : `${normalized}+09:00`;
  const d = new Date(withTz);
  return Number.isNaN(d.getTime()) ? null : d;
}

function partsOf(d: Date) {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return {
    y: get("year"),
    m: get("month"),
    day: get("day"),
    hh: get("hour"),
    mm: get("minute"),
    ss: get("second"),
  };
}

/** 2026.08.13 09:15 */
export function formatKstDateTime(value?: string | null, fallback = "-"): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  const p = partsOf(d);
  return `${p.y}.${p.m}.${p.day} ${p.hh}:${p.mm}`;
}

/** 2026-08-13 09:15:32 */
export function formatKstDateTimeLong(value?: string | null, fallback = ""): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  const p = partsOf(d);
  return `${p.y}-${p.m}-${p.day} ${p.hh}:${p.mm}:${p.ss}`;
}

/** 2026-08-13 09:15 */
export function formatKstDateTimeDash(value?: string | null, fallback = "-"): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  const p = partsOf(d);
  return `${p.y}-${p.m}-${p.day} ${p.hh}:${p.mm}`;
}

/** 2026.08.13 / 2026-08-13 */
export function formatKstDate(
  value?: string | null,
  fallback = "-",
  sep: "." | "-" = "-"
): string {
  const d = parseApiDate(value);
  if (!d) return fallback;
  const p = partsOf(d);
  return `${p.y}${sep}${p.m}${sep}${p.day}`;
}

/** 오늘(Asia/Seoul) YYYY-MM-DD */
export function todayKstDate(): string {
  const p = partsOf(new Date());
  return `${p.y}-${p.m}-${p.day}`;
}
