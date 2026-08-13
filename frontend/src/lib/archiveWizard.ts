import { apiClient } from "../api/client";
import type { ArchiveStatus, GeneratedDocument, RegulationReviewResult } from "../types";

export type StaffPerson = { id: number; name: string };

export type ProgramRow = {
  id: string;
  time: string;
  content: string;
  owner: string;
};

export type BudgetLineRow = {
  id: string;
  name: string;
  basis: string;
  unit_price: number;
  quantity: number;
};

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

export function archiveStatusFromRegulation(
  result: Pick<RegulationReviewResult, "summary"> | null | undefined,
): ArchiveStatus {
  if (!result) return "approved";
  if ((result.summary.violations || 0) > 0) return "issue";
  if ((result.summary.needs_check || 0) > 0) return "review";
  return "approved";
}

export async function applyArchiveReviewStatus(
  archiveId: number | null | undefined,
  result: Pick<RegulationReviewResult, "summary"> | null | undefined,
) {
  if (archiveId == null) return;
  await apiClient.patch(`/api/archive/${archiveId}/status`, {
    status: archiveStatusFromRegulation(result),
  });
}

export async function archiveAndLeave(
  archiveId: number | null | undefined,
  navigate: (path: string) => void,
) {
  try {
    if (archiveId != null) {
      await apiClient.patch(`/api/archive/${archiveId}/status`, { status: "archived" });
    }
  } finally {
    navigate("/archive");
  }
}

export function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function formatWon(n: number) {
  return `${Number(n || 0).toLocaleString("ko-KR")}원`;
}

export function formatBudgetInput(raw: string) {
  const digits = raw.replace(/[^\d]/g, "");
  if (!digits) return "";
  return Number(digits).toLocaleString("ko-KR");
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

export function mapPayloadRows<T>(
  value: unknown,
  mapFn: (rec: Record<string, unknown>, idx: number) => T | null,
): T[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((row, idx) => {
    const rec = asRecord(row);
    if (!rec) return [];
    const mapped = mapFn(rec, idx);
    return mapped ? [mapped] : [];
  });
}

export function parseProgramRows(
  value: unknown,
  idForIndex: (idx: number) => string,
): ProgramRow[] {
  return mapPayloadRows(value, (rec, idx) => ({
    id: idForIndex(idx),
    time: asString(rec.time),
    content: asString(rec.content),
    owner: asString(rec.owner),
  }));
}

export function parseBudgetLineRows(
  value: unknown,
  idForIndex: (idx: number) => string,
): BudgetLineRow[] {
  return mapPayloadRows(value, (rec, idx) => ({
    id: idForIndex(idx),
    name: asString(rec.name),
    basis: asString(rec.basis),
    unit_price: asNumber(rec.unit_price),
    quantity: asNumber(rec.quantity, 1),
  }));
}
