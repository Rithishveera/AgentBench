"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
}

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) ref.current?.showModal();
    else ref.current?.close();
  }, [open]);

  if (!open) return null;

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      className={cn(
        "rounded-card border-2 border-tan bg-ink-raised p-0 shadow-teal",
        "text-paper backdrop:bg-ink/70 open:flex open:flex-col",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-tan px-5 py-3">
        {title && <h2 className="text-sm">{title}</h2>}
        <button onClick={onClose} aria-label="Close dialog" className="ml-auto text-tan hover:text-paper">
          <X size={16} />
        </button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  );
}
