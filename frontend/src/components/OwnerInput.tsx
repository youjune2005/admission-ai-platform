import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Trash2 } from "lucide-react";
import type { StaffPerson } from "../lib/archiveWizard";

type Props = {
  value: string;
  staffList: StaffPerson[];
  active: boolean;
  onActivate: () => void;
  onChange: (value: string) => void;
  onCommit: (name: string) => void;
  onDeleteStaff: (id: number) => void;
};

export default function OwnerInput({
  value,
  staffList,
  active,
  onActivate,
  onChange,
  onCommit,
  onDeleteStaff,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState({ top: 0, left: 0, width: 160 });

  const filtered = staffList.filter((p) =>
    value.trim() ? p.name.toLowerCase().includes(value.trim().toLowerCase()) : true
  );

  const updateMenuPos = () => {
    const el = inputRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setMenuPos({
      top: rect.bottom + 4,
      left: rect.left,
      width: Math.max(rect.width, 160),
    });
  };

  useEffect(() => {
    if (!open) return;
    updateMenuPos();
    const onScroll = () => updateMenuPos();
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, value, staffList.length]);

  useEffect(() => {
    if (!open) return;
    const onDocDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (inputRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, [open]);

  const showMenu = open && filtered.length > 0;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={value}
        placeholder="이름 입력"
        onFocus={() => {
          onActivate();
          setOpen(true);
          updateMenuPos();
        }}
        onClick={() => {
          onActivate();
          setOpen(true);
          updateMenuPos();
        }}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          updateMenuPos();
        }}
        onBlur={() => {
          window.setTimeout(() => {
            if (value.trim()) onCommit(value);
          }, 150);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (value.trim()) {
              onCommit(value);
              setOpen(false);
            }
          }
          if (e.key === "Escape") setOpen(false);
        }}
        className={`field-input text-[12px] ${
          active ? "border-[var(--ssu-blue)] ring-2 ring-blue-100" : ""
        }`}
      />
      {showMenu &&
        createPortal(
          <ul
            ref={menuRef}
            className="fixed z-[1000] max-h-48 overflow-auto rounded-lg border border-slate-200 bg-white py-1 shadow-xl"
            style={{ top: menuPos.top, left: menuPos.left, width: menuPos.width }}
          >
            {filtered.map((person) => (
              <li
                key={person.id}
                className="flex items-center justify-between gap-2 px-2 py-1.5 hover:bg-slate-50"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left text-[12px] text-slate-700"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onChange(person.name);
                    onCommit(person.name);
                    setOpen(false);
                  }}
                >
                  {person.name}
                </button>
                <button
                  type="button"
                  aria-label={`${person.name} 삭제`}
                  className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onDeleteStaff(person.id);
                  }}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </li>
            ))}
          </ul>,
          document.body
        )}
    </div>
  );
}
