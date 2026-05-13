import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, GitBranch, LineChart, X } from "lucide-react";
import { api, type SchemaField } from "@/lib/api";
import type { Selection } from "@/App";
import { cn, formatNumber } from "@/lib/cn";
import { StatsModal } from "./StatsModal";
import { RefreshControl } from "./RefreshControl";

interface Props {
  selection: Selection;
  schema: SchemaField[];
  symbols: string[];
  onSymbolsChange: (s: string[]) => void;
  tsFrom: string | null;
  tsTo: string | null;
  onTsFromChange: (v: string | null) => void;
  onTsToChange: (v: string | null) => void;
  normalized: boolean;
  onToggleNormalized: () => void;
  view: "chart" | "workflow";
  onViewChange: (v: "chart" | "workflow") => void;
}

export function TableHeader({
  selection,
  schema,
  symbols,
  onSymbolsChange,
  tsFrom,
  tsTo,
  onTsFromChange,
  onTsToChange,
  normalized,
  onToggleNormalized,
  view,
  onViewChange,
}: Props) {
  const listQ = useQuery({
    queryKey: ["tables", selection.layer],
    queryFn: () => api.tables(selection.layer),
  });
  const table = listQ.data?.tables.find((t) => t.name === selection.name);
  const availableSymbols = table?.symbols ?? [];

  const hasTimestamp = schema.some((f) => f.column === "timestamp");

  // Bounds are based on the first selected symbol (or none).
  const primarySymbol = symbols[0] ?? null;
  const boundsQ = useQuery({
    queryKey: ["bounds", selection.layer, selection.name, primarySymbol],
    queryFn: () => api.bounds(selection.layer, selection.name, primarySymbol),
    enabled: hasTimestamp,
  });

  const minBound = boundsQ.data?.min ? toLocalInput(boundsQ.data.min) : undefined;
  const maxBound = boundsQ.data?.max ? toLocalInput(boundsQ.data.max) : undefined;

  useEffect(() => {
    if (!boundsQ.data) return;
    const min = boundsQ.data.min ? new Date(boundsQ.data.min).getTime() : null;
    const max = boundsQ.data.max ? new Date(boundsQ.data.max).getTime() : null;
    if (tsFrom) {
      const t = new Date(tsFrom).getTime();
      if ((min !== null && t < min) || (max !== null && t > max)) onTsFromChange(null);
    }
    if (tsTo) {
      const t = new Date(tsTo).getTime();
      if ((min !== null && t < min) || (max !== null && t > max)) onTsToChange(null);
    }
  }, [boundsQ.data]);

  const applyPreset = (days: number | "all") => {
    if (days === "all" || !boundsQ.data?.max) {
      onTsFromChange(null);
      onTsToChange(null);
      return;
    }
    const max = new Date(boundsQ.data.max);
    const from = new Date(max.getTime() - days * 86_400_000);
    onTsFromChange(toIsoLike(from));
    onTsToChange(toIsoLike(max));
  };

  const [statsOpen, setStatsOpen] = useState(false);

  const layerColor =
    selection.layer === "bronze" ? "text-amber-700"
    : selection.layer === "silver" ? "text-zinc-400"
    : "text-accent";

  return (
    <>
      <div className="flex flex-wrap items-center gap-3 gap-y-2 border-b border-border bg-bg-panel px-4 py-2.5">
        <div className="flex items-baseline gap-2">
          <span className={cn("font-mono text-xs font-semibold tracking-wider", layerColor)}>
            {selection.layer.toUpperCase()}
          </span>
          <span className="text-fg-dim">/</span>
          <span className="font-mono text-sm font-semibold text-fg">{selection.name}</span>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3 font-mono text-xs text-fg-muted">
          <div className="flex items-center rounded border border-border">
            <button
              onClick={() => onViewChange("chart")}
              className={cn(
                "flex items-center gap-1.5 px-2 py-1 text-xs transition-colors",
                view === "chart"
                  ? "bg-accent/10 text-accent"
                  : "text-fg-muted hover:text-fg"
              )}
              title="Chart view"
            >
              <LineChart className="h-3 w-3" />
              chart
            </button>
            <button
              onClick={() => onViewChange("workflow")}
              className={cn(
                "flex items-center gap-1.5 border-l border-border px-2 py-1 text-xs transition-colors",
                view === "workflow"
                  ? "bg-accent/10 text-accent"
                  : "text-fg-muted hover:text-fg"
              )}
              title="Pipeline workflow view"
            >
              <GitBranch className="h-3 w-3" />
              workflow
            </button>
          </div>

          <button
            onClick={onToggleNormalized}
            disabled={view !== "chart"}
            className={cn(
              "flex items-center gap-1.5 rounded border px-2 py-1 text-xs transition-colors",
              view !== "chart"
                ? "cursor-not-allowed border-border text-fg-dim"
                : normalized
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-fg-muted hover:border-accent hover:text-accent"
            )}
            title="Rebase each chart series to 100 at its first value"
          >
            <Activity className="h-3 w-3" />
            normalize
          </button>

          {availableSymbols.length > 0 && (
            <SymbolPicker
              available={availableSymbols}
              selected={symbols}
              onChange={onSymbolsChange}
            />
          )}

          {hasTimestamp && (
            <>
              <label className="flex items-center gap-2">
                <span className="text-fg-dim">start</span>
                <input
                  type="datetime-local"
                  value={tsFrom ?? ""}
                  min={minBound}
                  max={maxBound}
                  onChange={(e) => onTsFromChange(e.target.value || null)}
                  className="rounded border border-border bg-bg px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
                />
              </label>
              <label className="flex items-center gap-2">
                <span className="text-fg-dim">end</span>
                <input
                  type="datetime-local"
                  value={tsTo ?? ""}
                  min={minBound}
                  max={maxBound}
                  onChange={(e) => onTsToChange(e.target.value || null)}
                  className="rounded border border-border bg-bg px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
                />
              </label>

              <div className="flex items-center gap-1">
                <PresetBtn onClick={() => applyPreset(1)}>1d</PresetBtn>
                <PresetBtn onClick={() => applyPreset(7)}>7d</PresetBtn>
                <PresetBtn onClick={() => applyPreset(30)}>30d</PresetBtn>
                <PresetBtn onClick={() => applyPreset("all")}>all</PresetBtn>
                {(tsFrom || tsTo) && (
                  <button
                    onClick={() => applyPreset("all")}
                    className="rounded border border-border p-1 text-fg-muted transition-colors hover:border-accent hover:text-accent"
                    title="Clear range"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </>
          )}

          <button
            onClick={() => setStatsOpen(true)}
            className="flex items-center gap-1.5 rounded border border-border px-2 py-1 text-xs text-fg-muted transition-colors hover:border-accent hover:text-accent"
            title="Column statistics"
          >
            <BarChart3 className="h-3 w-3" />
            stats
          </button>

          <RefreshControl />

          <div className="flex items-center gap-3 border-l border-border pl-3">
            <span>{formatNumber(table?.rows)} rows</span>
            <span>{schema.length} cols</span>
          </div>
        </div>
      </div>

      {statsOpen && (
        <StatsModal
          selection={selection}
          symbols={symbols}
          tsFrom={tsFrom}
          tsTo={tsTo}
          onClose={() => setStatsOpen(false)}
        />
      )}
    </>
  );
}

function SymbolPicker({
  available,
  selected,
  onChange,
}: {
  available: string[];
  selected: string[];
  onChange: (s: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const toggle = (s: string) => {
    if (selected.includes(s)) {
      if (selected.length > 1) onChange(selected.filter((x) => x !== s));
    } else {
      onChange([...selected, s]);
    }
  };

  const label =
    selected.length === 0 ? "none"
    : selected.length === 1 ? selected[0]
    : `${selected[0]} +${selected.length - 1}`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex items-center gap-2 rounded border px-2 py-1 text-xs transition-colors",
          open
            ? "border-accent text-accent"
            : "border-border text-fg hover:border-accent hover:text-accent"
        )}
      >
        <span className="text-fg-dim">symbol</span>
        <span>{label}</span>
        <span className="text-fg-dim">
          ({selected.length}/{available.length})
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 w-56 rounded border border-border-strong bg-bg-panel shadow-xl">
          <div className="flex items-center gap-2 border-b border-border px-2 py-1.5 text-[11px]">
            <button
              onClick={() => onChange(available.slice(0, 1))}
              className="rounded border border-border px-1.5 py-0.5 text-fg-muted transition-colors hover:border-accent hover:text-accent"
            >
              single
            </button>
            <button
              onClick={() => onChange([...available])}
              className="rounded border border-border px-1.5 py-0.5 text-fg-muted transition-colors hover:border-accent hover:text-accent"
            >
              all
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto scrollbar-thin py-1">
            {available.map((s) => {
              const isSelected = selected.includes(s);
              return (
                <button
                  key={s}
                  onClick={() => toggle(s)}
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
                  <span className={cn(isSelected ? "text-fg" : "text-fg-muted")}>{s}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function PresetBtn({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded border border-border px-1.5 py-0.5 text-[11px] text-fg-muted transition-colors hover:border-accent hover:text-accent"
    >
      {children}
    </button>
  );
}

function toLocalInput(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    d.getUTCFullYear() + "-" +
    pad(d.getUTCMonth() + 1) + "-" +
    pad(d.getUTCDate()) + "T" +
    pad(d.getUTCHours()) + ":" +
    pad(d.getUTCMinutes())
  );
}

function toIsoLike(d: Date): string {
  return toLocalInput(d.toISOString());
}
