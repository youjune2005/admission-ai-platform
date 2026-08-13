import { useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client";
import type { GeneratedDocument } from "../types";

export function useArchiveHydration(
  archiveIdParam: string | null,
  apply: (doc: GeneratedDocument) => void,
  onError?: (message: string) => void,
) {
  const [hydrating, setHydrating] = useState(!!archiveIdParam);
  const applyRef = useRef(apply);
  const onErrorRef = useRef(onError);
  applyRef.current = apply;
  onErrorRef.current = onError;

  useEffect(() => {
    if (!archiveIdParam) return;
    const id = Number(archiveIdParam);
    if (!Number.isFinite(id) || id <= 0) {
      setHydrating(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const { data } = await apiClient.get<GeneratedDocument>(`/api/archive/${id}`);
        if (cancelled) return;
        applyRef.current(data);
      } catch {
        if (!cancelled) onErrorRef.current?.("작성 중이던 문서를 불러오지 못했습니다.");
      } finally {
        if (!cancelled) setHydrating(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [archiveIdParam]);

  return hydrating;
}
