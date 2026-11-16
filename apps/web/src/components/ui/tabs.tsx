"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Tab { id: string; label: string; content: ReactNode }

export function Tabs({ tabs, className }: { tabs: Tab[]; className?: string }) {
  const [active, setActive] = useState(tabs[0]?.id ?? "");
  return (
    <div className={cn("flex flex-col gap-0", className)}>
      <div className="flex border-b border-tan" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={active === tab.id}
            aria-controls={`tab-panel-${tab.id}`}
            className={cn(
              "px-4 py-2 text-sm font-semibold uppercase tracking-wide transition-colors",
              active === tab.id
                ? "border-b-2 border-tan text-paper"
                : "text-tan hover:text-paper",
            )}
            onClick={() => setActive(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`tab-panel-${tab.id}`}
          hidden={active !== tab.id}
          className="p-4 bg-ink-raised"
        >
          {tab.content}
        </div>
      ))}
    </div>
  );
}
