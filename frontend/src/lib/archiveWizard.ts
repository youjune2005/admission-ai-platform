import type { GeneratedDocument } from "../types";

export type ArchiveSortBy = "title" | "updated_at";
export type ArchiveSortDir = "asc" | "desc";

export function archiveWizardPath(kind: string, id: number): string | null {
  switch (kind) {
    case "briefing":
      return `/documents/create/wizard?archiveId=${id}`;
    case "budget":
      return `/documents/create/budget?archiveId=${id}`;
    case "visit":
      return `/documents/create/visit?archiveId=${id}`;
    case "fair":
      return `/documents/create/fair?archiveId=${id}`;
    default:
      return null;
  }
}

export function canResumeArchive(doc: Pick<GeneratedDocument, "source_kind" | "status">): boolean {
  return (
    doc.status === "draft" &&
    ["briefing", "budget", "visit", "fair"].includes(doc.source_kind)
  );
}

export function asString(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return fallback;
}

export function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value.replace(/[^\d.-]/g, ""));
    return Number.isFinite(n) ? n : fallback;
  }
  return fallback;
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}
