import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/cn";

type Interval = 0 | 10 | 30 | 60 | 300;

const OPTIONS: { value: Interval; label: string }[] = [
  { value: 0, label: "off" },
  { value: 10, label: "10s" },
  { value: 30, label: "30s" },
  { value: 60, label: "1m" },
  { value: 300, label: "5m" },
];

export function RefreshControl() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [interval, setInterval] = useState<Interval>(0);
  const [spinning, setSpinning] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const refreshNow = () => {
    queryClient.invalidateQueries();
    setSpinning(true);
    window.setTimeout(() => setSpinning(false), 500);
  };

  useEffect(() => {
    if (interval === 0) return;
    const id = window.setInterval(refreshNow, interval * 1000);
    return () => window.clearInterval(id);
  }, [interval]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const active = interval !== 0;
  const label = active ? OPTIONS.find((o) => o.value === interval)!.label : "refresh";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex items-center gap-1.5 rounded border px-2 py-1 text-xs transition-colors",
          open || active
            ? "border-accent text-accent"
            : "border-border text-fg-muted hover:border-accent hover:text-accent"
        )}
        title={active ? `auto-refresh every ${label}` : "refresh data"}
      >
        <RefreshCw className={cn("h-3 w-3", spinning && "animate-spin")} />
        {label}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-40 rounded border border-border-strong bg-bg-panel shadow-xl">
          <button
            onClick={() => {
              refreshNow();
              setOpen(false);
            }}
            className="flex w-full items-center gap-2 border-b border-border px-2 py-1.5 text-left text-xs text-fg-muted hover:bg-bg-elevated hover:text-fg"
          >
            <RefreshCw className="h-3 w-3" />
            refresh now
          </button>
          <div className="py-1">
            <div className="px-2 py-1 text-[10px] uppercase tracking-wider text-fg-dim">
              auto-refresh
            </div>
            {OPTIONS.map((o) => {
              const isSelected = o.value === interval;
              return (
                <button
                  key={o.value}
                  onClick={() => {
                    setInterval(o.value);
                    setOpen(false);
                  }}
                  className="flex w-full items-center gap-2 px-2 py-1 text-left text-xs hover:bg-bg-elevated"
                >
                  <span
                    className={cn(
                      "flex h-3 w-3 items-center justify-center rounded-sm border",
                      isSelected
                        ? "border-accent bg-accent/20 text-accent"
                        : "border-border"
                    )}
                  >
                    {isSelected && <span className="text-[9px] leading-none">✓</span>}
                  </span>
                  <span className={cn(isSelected ? "text-fg" : "text-fg-muted")}>{o.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
