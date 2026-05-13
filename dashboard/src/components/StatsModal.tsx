import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { Selection } from "@/App";
import { formatCell } from "@/lib/cn";

interface Props {
  selection: Selection;
  symbols: string[];
  tsFrom: string | null;
  tsTo: string | null;
  onClose: () => void;
}

const FIELDS: { key: string; label: string }[] = [
  { key: "count", label: "count" },
  { key: "null_percentage", label: "nulls %" },
  { key: "approx_unique", label: "unique" },
  { key: "min", label: "min" },
  { key: "max", label: "max" },
  { key: "avg", label: "mean" },
  { key: "std", label: "std" },
  { key: "q25", label: "p25" },
  { key: "q50", label: "p50" },
  { key: "q75", label: "p75" },
];

export function StatsModal({ selection, symbols, tsFrom, tsTo, onClose }: Props) {
  const q = useQuery({
    queryKey: ["stats", selection.layer, selection.name, symbols.join(","), tsFrom, tsTo],
    queryFn: () =>
      api.stats(selection.layer, selection.name, { symbols, tsFrom, tsTo }),
  });

  // Close on Escape.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-8"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded border border-border-strong bg-bg-panel shadow-2xl"
      >
        <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
          <span className="font-mono text-xs uppercase tracking-wider text-fg-dim">stats</span>
          <span className="font-mono text-sm font-semibold text-fg">
            {selection.layer}/{selection.name}
          </span>
          <span className="font-mono text-xs text-fg-muted">
            {symbols.length === 0
              ? "all symbols"
              : symbols.length === 1
              ? symbols[0]
              : `${symbols.length} symbols`}
          </span>
          <button
            onClick={onClose}
            className="ml-auto rounded p-1 text-fg-muted transition-colors hover:bg-bg-elevated hover:text-fg"
            title="Close (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-auto scrollbar-thin">
          {q.isLoading && (
            <div className="p-8 text-center font-mono text-xs text-fg-dim">loading…</div>
          )}
          {q.isError && (
            <div className="p-8 text-center font-mono text-xs text-red-400">
              failed to compute stats
            </div>
          )}
          {q.data && (
            <table className="w-full border-collapse font-mono text-xs">
              <thead className="sticky top-0 z-10 bg-bg-panel">
                <tr className="border-b border-border">
                  <th className="border-r border-border px-3 py-2 text-left font-medium uppercase tracking-wider text-fg-muted">
                    column
                  </th>
                  <th className="border-r border-border px-3 py-2 text-left font-medium uppercase tracking-wider text-fg-muted">
                    dtype
                  </th>
                  {FIELDS.map((f) => (
                    <th
                      key={f.key}
                      className="border-r border-border px-3 py-2 text-right font-medium uppercase tracking-wider text-fg-muted"
                    >
                      {f.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {q.data.stats.map((row, i) => {
                  const nullsPct = row.null_percentage;
                  const isUnhealthy =
                    typeof nullsPct === "number" && nullsPct > 1;
                  return (
                    <tr
                      key={row.column ?? i}
                      className="border-b border-border/50 hover:bg-bg-elevated"
                    >
                      <td className="border-r border-border/50 px-3 py-1 text-fg">
                        {row.column ?? "—"}
                      </td>
                      <td className="border-r border-border/50 px-3 py-1 text-fg-muted">
                        {row.dtype ?? "—"}
                      </td>
                      {FIELDS.map((f) => {
                        const v = (row as any)[f.key];
                        const highlight =
                          f.key === "null_percentage" && isUnhealthy
                            ? "text-amber-400"
                            : "text-fg";
                        return (
                          <td
                            key={f.key}
                            className={`border-r border-border/50 px-3 py-1 text-right tabular-nums ${highlight}`}
                          >
                            {formatStatValue(f.key, v)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function formatStatValue(key: string, v: unknown): string {
  if (v == null) return "—";
  if (key === "null_percentage") {
    const n = typeof v === "number" ? v : parseFloat(String(v));
    if (!Number.isFinite(n)) return formatCell(v);
    return n.toFixed(2) + "%";
  }
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return formatCell(v);
}
