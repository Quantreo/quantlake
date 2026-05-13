import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Plus, X } from "lucide-react";
import { api, type SchemaField } from "@/lib/api";
import type { Selection } from "@/App";
import { cn } from "@/lib/cn";

const SERIES_COLORS = [
  "#f59e0b", "#06b6d4", "#22c55e", "#e879f9",
  "#f87171", "#a78bfa", "#fb923c", "#34d399",
];

const PARTITION_COLS = new Set(["year", "month", "day", "hour"]);

interface Props {
  selection: Selection;
  schema: SchemaField[];
  symbols: string[];
  tsFrom: string | null;
  tsTo: string | null;
  normalized: boolean;
}

export function ChartPanel({ selection, schema, symbols, tsFrom, tsTo, normalized }: Props) {
  const numericCols = useMemo(
    () =>
      schema.filter((f) => f.numeric && !PARTITION_COLS.has(f.column)).map((f) => f.column),
    [schema]
  );
  const hasTimestamp = schema.some((f) => f.column === "timestamp");

  // Each entry = one chart, holding the list of selected columns.
  const [charts, setCharts] = useState<string[][]>([[]]);

  useEffect(() => {
    if (numericCols.length === 0) setCharts([[]]);
    else setCharts([[numericCols[0]]]);
  }, [selection.layer, selection.name, numericCols.join(",")]);

  // Union of all columns across charts — one fetch to feed every chart.
  const allSelected = useMemo(() => {
    const s = new Set<string>();
    charts.forEach((cols) => cols.forEach((c) => s.add(c)));
    return [...s];
  }, [charts]);

  const seriesQ = useQuery({
    queryKey: [
      "series",
      selection.layer,
      selection.name,
      symbols.join(","),
      tsFrom,
      tsTo,
      allSelected.join(","),
    ],
    queryFn: () =>
      api.series(selection.layer, selection.name, {
        columns: allSelected,
        symbols,
        x: "timestamp",
        maxPoints: 3000,
        tsFrom,
        tsTo,
      }),
    enabled: hasTimestamp && allSelected.length > 0 && symbols.length > 0,
  });

  const multiSymbol = symbols.length > 1;

  // Pivot server rows into one record per timestamp with keys like "col:symbol"
  // so Recharts can render one Line per (symbol × column) in the same LineChart.
  const data = useMemo(() => {
    const points = seriesQ.data?.points ?? [];
    if (!multiSymbol) {
      return points.map((p) => ({ ...p, _t: new Date(p.timestamp as string).getTime() }));
    }
    const byTs = new Map<number, Record<string, unknown>>();
    for (const p of points) {
      const t = new Date(p.timestamp as string).getTime();
      if (!byTs.has(t)) byTs.set(t, { _t: t, timestamp: p.timestamp });
      const row = byTs.get(t)!;
      const sym = p.symbol as string;
      for (const col of allSelected) {
        row[`${col}:${sym}`] = p[col];
      }
    }
    return [...byTs.values()].sort((a, b) => (a._t as number) - (b._t as number));
  }, [seriesQ.data, multiSymbol, allSelected]);

  const toggleCol = (chartIdx: number, col: string) => {
    setCharts((cs) =>
      cs.map((cols, i) =>
        i !== chartIdx ? cols : cols.includes(col) ? cols.filter((c) => c !== col) : [...cols, col]
      )
    );
  };
  const addChart = () => {
    const used = new Set(allSelected);
    const fallback = numericCols.find((c) => !used.has(c)) ?? numericCols[0];
    setCharts((cs) => [...cs, fallback ? [fallback] : []]);
  };
  const removeChart = (idx: number) => {
    setCharts((cs) => (cs.length <= 1 ? cs : cs.filter((_, i) => i !== idx)));
  };

  if (symbols.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-4 font-mono text-xs text-fg-dim">
        <span>select at least one symbol in the header to display charts</span>
      </div>
    );
  }

  if (!hasTimestamp) {
    return (
      <div className="flex h-full items-center justify-center p-4 font-mono text-xs text-fg-dim">
        no timestamp column on this table
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <div
        className={cn(
          "grid flex-1 min-h-0 gap-3 p-3",
          gridClass(charts.length)
        )}
      >
        {charts.map((cols, idx) => (
          <ChartCard
            key={idx}
            index={idx}
            total={charts.length}
            cellClass={cellClass(idx, charts.length)}
            columns={cols}
            numericCols={numericCols}
            onToggle={(c) => toggleCol(idx, c)}
            onRemove={() => removeChart(idx)}
            data={data}
            symbols={symbols}
            loading={seriesQ.isLoading}
            normalized={normalized}
          />
        ))}
      </div>

      <div className="border-t border-border bg-bg-panel px-4 py-2">
        <button
          onClick={addChart}
          disabled={charts.length >= 4}
          className={cn(
            "flex items-center gap-1.5 rounded border border-border px-2.5 py-1 font-mono text-xs transition-colors",
            charts.length >= 4
              ? "text-fg-dim cursor-not-allowed"
              : "text-fg-muted hover:border-accent hover:text-accent"
          )}
          title={charts.length >= 4 ? "Max 4 charts" : "Add a new chart"}
        >
          <Plus className="h-3 w-3" />
          add chart
          <span className="text-fg-dim">({charts.length}/4)</span>
        </button>
      </div>
    </div>
  );
}

function gridClass(n: number): string {
  if (n <= 1) return "grid-cols-1 grid-rows-1";
  if (n === 2) return "grid-cols-1 grid-rows-2";
  return "grid-cols-2 grid-rows-2";
}

function cellClass(idx: number, n: number): string {
  // 3 charts: third one spans both columns on the bottom row.
  if (n === 3 && idx === 2) return "col-span-2";
  return "";
}

interface ChartCardProps {
  index: number;
  total: number;
  cellClass: string;
  columns: string[];
  numericCols: string[];
  onToggle: (col: string) => void;
  onRemove: () => void;
  data: any[];
  symbols: string[];
  loading: boolean;
  normalized: boolean;
}

function ChartCard({
  index,
  total,
  cellClass,
  columns,
  numericCols,
  onToggle,
  onRemove,
  data,
  symbols,
  loading,
  normalized,
}: ChartCardProps) {
  const multiSymbol = symbols.length > 1;
  // For multi-symbol, compose dataKeys as "col:symbol". Each key gets its
  // own color slot. Use a deterministic palette index across (symbol, col).
  const lines = multiSymbol
    ? columns.flatMap((col, ci) =>
        symbols.map((sym, si) => ({
          key: `${col}:${sym}`,
          label: `${col} · ${sym}`,
          color: SERIES_COLORS[(ci * symbols.length + si) % SERIES_COLORS.length],
          dasharray: si === 0 ? undefined : "4 3",
        }))
      )
    : columns.map((col, ci) => ({
        key: col,
        label: col,
        color: SERIES_COLORS[ci % SERIES_COLORS.length],
        dasharray: undefined as string | undefined,
      }));

  const fmtTick = useMemo(() => {
    if (data.length < 2) return makeFormatTick(0);
    const first = data[0]?._t as number | undefined;
    const last = data[data.length - 1]?._t as number | undefined;
    const range = typeof first === "number" && typeof last === "number" ? last - first : 0;
    return makeFormatTick(range);
  }, [data]);

  // Rebase each line to 100 at its first non-null value so series with very
  // different magnitudes (e.g. BTC ≈ $40k vs ETH ≈ $2k) become comparable.
  const displayData = useMemo(() => {
    if (!normalized || lines.length === 0 || data.length === 0) return data;
    const firsts = new Map<string, number>();
    for (const row of data) {
      for (const l of lines) {
        if (firsts.has(l.key)) continue;
        const v = row[l.key];
        if (typeof v === "number" && Number.isFinite(v) && v !== 0) {
          firsts.set(l.key, v);
        }
      }
      if (firsts.size === lines.length) break;
    }
    return data.map((row) => {
      const copy: Record<string, unknown> = { ...row };
      for (const l of lines) {
        const base = firsts.get(l.key);
        const v = row[l.key];
        copy[l.key] =
          base && typeof v === "number" && Number.isFinite(v) ? (v / base) * 100 : null;
      }
      return copy;
    });
  }, [normalized, data, lines]);

  return (
    <div
      className={cn(
        "flex flex-col min-h-0 min-w-0 overflow-hidden rounded border border-border bg-bg-panel",
        cellClass
      )}
    >
      <div className="flex items-center gap-2 border-b border-border bg-bg-panel px-3 py-1.5">
        <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-fg-dim">
          chart {index + 1}
        </span>
        <div className="flex flex-1 min-w-0 items-center gap-2 overflow-x-auto scrollbar-thin">
          {numericCols.length === 0 && (
            <span className="font-mono text-xs text-fg-dim">no numeric columns</span>
          )}
          {numericCols.map((col) => {
            const active = columns.includes(col);
            const ci = columns.indexOf(col);
            // Single-symbol: show the actual series color. Multi-symbol: one
            // column maps to N lines so we just highlight active vs inactive.
            const dotColor = !active
              ? "#3f3f46"
              : multiSymbol
              ? "#f59e0b"
              : SERIES_COLORS[ci % SERIES_COLORS.length];
            return (
              <button
                key={col}
                onClick={() => onToggle(col)}
                className={cn(
                  "shrink-0 flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-xs transition-colors",
                  active
                    ? "border-border-strong bg-bg-elevated text-fg"
                    : "border-border text-fg-muted hover:text-fg"
                )}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: dotColor }} />
                {col}
              </button>
            );
          })}
        </div>
        {total > 1 && (
          <button
            onClick={onRemove}
            className="shrink-0 rounded border border-border p-1 text-fg-muted transition-colors hover:border-red-500/50 hover:text-red-400"
            title="Remove chart"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="relative flex-1 min-h-0 w-full">
        {columns.length === 0 ? (
          <Centered>select one or more series above</Centered>
        ) : loading ? (
          <Centered>loading…</Centered>
        ) : (
          <div className="absolute inset-0 px-5 pt-4 pb-2">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={displayData}
              margin={{ top: 8, right: 20, left: 8, bottom: 8 }}
              syncId="quantlake-charts"
            >
              <CartesianGrid stroke="#1f1f23" strokeDasharray="2 4" />
              <XAxis
                dataKey="_t"
                type="number"
                domain={["dataMin", "dataMax"]}
                scale="time"
                stroke="#52525b"
                tick={{ fill: "#71717a", fontSize: 10, fontFamily: "JetBrains Mono" }}
                tickFormatter={(v) => fmtTick(v as number)}
                minTickGap={60}
                allowDataOverflow
              />
              <YAxis
                stroke="#52525b"
                tick={{ fill: "#71717a", fontSize: 10, fontFamily: "JetBrains Mono" }}
                width={64}
                tickFormatter={(v) => formatY(v as number)}
                domain={["auto", "auto"]}
              />
              <Tooltip content={<ChartTooltip />} />
              {lines.map((l) => (
                <Line
                  key={l.key}
                  type="monotone"
                  dataKey={l.key}
                  stroke={l.color}
                  strokeDasharray={l.dasharray}
                  strokeWidth={1.25}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={true}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

const DAY_MS = 86_400_000;

// Return a tick formatter adapted to the visible time span. Short windows
// need HH:MM; long ones need the year so users don't get lost in history.
function makeFormatTick(rangeMs: number): (ms: number) => string {
  return (ms: number) => {
    const d = new Date(ms);
    const YYYY = d.getUTCFullYear();
    const MM = String(d.getUTCMonth() + 1).padStart(2, "0");
    const DD = String(d.getUTCDate()).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const mm = String(d.getUTCMinutes()).padStart(2, "0");
    if (rangeMs > 365 * DAY_MS) return `${YYYY}-${MM}-${DD}`;
    if (rangeMs > 30 * DAY_MS) return `${YYYY}-${MM}-${DD}`;
    if (rangeMs > DAY_MS) return `${MM}-${DD} ${hh}:${mm}`;
    return `${hh}:${mm}`;
  };
}

// Full timestamp for tooltips — always unambiguous regardless of zoom.
function formatFull(ms: number): string {
  const d = new Date(ms);
  const YYYY = d.getUTCFullYear();
  const MM = String(d.getUTCMonth() + 1).padStart(2, "0");
  const DD = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${YYYY}-${MM}-${DD} ${hh}:${mm} UTC`;
}

function formatY(v: number): string {
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
  if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(1) + "k";
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(4);
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center font-mono text-xs text-fg-dim">
      {children}
    </div>
  );
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-border-strong bg-bg-panel px-3 py-2 font-mono text-xs shadow-xl">
      <div className="mb-1 text-fg-dim">{formatFull(label)}</div>
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full" style={{ background: p.color }} />
          <span className="text-fg-muted">{p.dataKey}</span>
          <span className="ml-auto text-fg">{formatY(p.value)}</span>
        </div>
      ))}
    </div>
  );
}
