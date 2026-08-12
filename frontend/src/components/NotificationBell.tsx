import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";

export type AppNotification = {
  id: string;
  title: string;
  body?: string;
  createdAt: string;
  read?: boolean;
};

type NotificationBellProps = {
  /** 알림 소스. 비우면 빈 목록(배지 숨김). 나중에 API 연동 시 주입. */
  notifications?: AppNotification[];
};

export default function NotificationBell({ notifications }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[]>(notifications ?? []);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setItems(notifications ?? []);
  }, [notifications]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const unreadCount = items.filter((n) => !n.read).length;
  const showBadge = unreadCount > 0;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`ui-pressable relative rounded-full p-2 text-slate-500 hover:bg-slate-50 hover:text-slate-700 ${
          open ? "bg-slate-50 text-slate-700" : ""
        }`}
        aria-label="알림"
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Bell className="h-5 w-5" />
        {showBadge && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="dropdown-enter absolute right-0 top-[calc(100%+8px)] z-50 w-[320px] overflow-hidden rounded-xl border border-[var(--ssu-border)] bg-white shadow-lg"
          role="dialog"
          aria-label="알림 목록"
        >
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <p className="text-[13px] font-bold text-slate-900">알림</p>
            {showBadge && (
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-semibold text-red-600">
                읽지 않음 {unreadCount}
              </span>
            )}
          </div>

          {items.length === 0 ? (
            <div className="px-4 py-10 text-center">
              <p className="text-[13px] font-semibold text-slate-700">새 알림이 없습니다</p>
              <p className="mt-1 text-[12px] text-slate-500">
                문서 승인·검토 알림이 여기에 표시됩니다.
              </p>
            </div>
          ) : (
            <ul className="max-h-[360px] overflow-y-auto">
              {items.map((item) => (
                <li
                  key={item.id}
                  className={`border-b border-slate-50 px-4 py-3 last:border-0 ${
                    item.read ? "bg-white" : "bg-blue-50/40"
                  }`}
                >
                  <p className="text-[13px] font-bold text-slate-900">{item.title}</p>
                  {item.body && (
                    <p className="mt-0.5 text-[12px] leading-relaxed text-slate-600">{item.body}</p>
                  )}
                  <p className="mt-1 text-[11px] font-medium text-slate-400">
                    {new Date(item.createdAt).toLocaleString("ko-KR")}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
