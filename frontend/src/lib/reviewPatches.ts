import type { ContentReviewPatch } from "../types";

export function applyReviewPatches<T>(payload: T, patches: ContentReviewPatch[]): T {
  const root = structuredClone(payload) as unknown;
  for (const patch of patches) {
    if (!patch?.path) continue;
    setByPath(root, patch.path, patch.value);
  }
  return root as T;
}

function setByPath(root: unknown, path: string, value: unknown) {
  const parts = path.split(".").filter(Boolean);
  if (!parts.length) return;
  let cursor: unknown = root;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i];
    const nextKey = parts[i + 1];
    const asIndex = Number.isInteger(Number(key)) ? Number(key) : null;
    if (Array.isArray(cursor) && asIndex != null) {
      if (cursor[asIndex] == null) {
        cursor[asIndex] = Number.isInteger(Number(nextKey)) ? [] : {};
      }
      cursor = cursor[asIndex];
      continue;
    }
    if (!cursor || typeof cursor !== "object") return;
    const rec = cursor as Record<string, unknown>;
    if (rec[key] == null) {
      rec[key] = Number.isInteger(Number(nextKey)) ? [] : {};
    }
    cursor = rec[key];
  }
  const last = parts[parts.length - 1];
  const lastIndex = Number.isInteger(Number(last)) ? Number(last) : null;
  if (Array.isArray(cursor) && lastIndex != null) {
    cursor[lastIndex] = value;
    return;
  }
  if (cursor && typeof cursor === "object") {
    (cursor as Record<string, unknown>)[last] = value;
  }
}
