import { useLayoutEffect, useRef } from "react";

/** 정렬 시 같은 id 행이 이전 위치에서 새 위치로 미끄러지듯 이동 */
export function useFlipSort(ids: Array<string | number>) {
  const rootRef = useRef<HTMLElement | null>(null); // div | tbody
  const prev = useRef<Map<string, DOMRect>>(new Map());
  const key = ids.join(",");

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>("[data-flip-id]"));
    const next = new Map<string, DOMRect>();

    for (const el of nodes) {
      const id = el.dataset.flipId;
      if (!id) continue;
      const rect = el.getBoundingClientRect();
      next.set(id, rect);
      const from = prev.current.get(id);
      if (!from) continue;
      const dy = from.top - rect.top;
      const dx = from.left - rect.left;
      if (Math.abs(dy) < 1 && Math.abs(dx) < 1) continue;
      el.animate(
        [
          { transform: `translate(${dx}px, ${dy}px)`, opacity: 0.72 },
          { transform: "translate(0, 0)", opacity: 1 },
        ],
        {
          duration: 360,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
          fill: "both",
        }
      );
    }
    prev.current = next;
  }, [key]);

  return rootRef;
}
