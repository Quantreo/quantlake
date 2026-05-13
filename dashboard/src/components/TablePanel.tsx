import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Columns3,
} from "lucide-react";
import { api, type SchemaField } from "@/lib/api";
import type { Selection } from "@/App";
import { cn, formatCell, formatNumber } from "@/lib/cn";

const PAGE_SIZE = 50;

interface Props {
  selection: Selection;
  schema: SchemaField[];
  symbols: string[];
  tsFrom: string | null;
  tsTo: string | null;
}

export function TablePanel({ selection, schema, symbols, tsFrom, tsTo }: Props) {
  const [page, setPage] = useState(1);
  const [orderBy, setOrderBy] = useState<string>("timestamp");
  const [descending, setDescending] = useState(true);
  const [hidden, setHidden] = useState<Set<string>>(new Set());

  // Reset hidden columns when table changes.
  useEffect(() => {
    setHidden(new Set());
  }, [selection.layer, selection.name]);

  // Reset pagination when filters change.
  useMemo(() => setPage(1), [selection.layer, selection.name, symbols.join(","), tsFrom, tsTo]);

  const dataQ = useQuery({
    queryKey: [
      "data",
      selection.layer,
      selection.name,
      symbols.join(","),
      tsFrom,
      tsTo,
      page,
      orderBy,
      descending,
    ],
    queryFn: () =>
      api.data(selection.layer, selection.name, {
        symbols,
        page,
        pageSize: PAGE_SIZE,
        orderBy,
        descending,
        tsFrom,
        tsTo,
      }),
    placeholderData: keepPreviousData,
  });

  const allColumns = dataQ.data?.columns ?? [];
  const visibleColumns = useMemo(
    () => allColumns.filter((c) => !hidden.has(c)),
    [allColumns, hidden]
  );
  const rows = dataQ.data?.rows ?? [];
  const total = dataQ.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const handleSort = (col: string) => {
    if (col === orderBy) {
      setDescending((d) => !d);
    } else {
      setOrderBy(col);
      setDescending(true);
    }
    setPage(1);
  };

  return (
    <div className="h-full bg-bg p-3">
      <div className="flex h-full flex-col overflow-hidden rounded border border-border bg-bg-panel">
        <div className="flex items-center gap-3 border-b border-border bg-bg-panel px-3 py-1.5 font-mono text-xs">
          <span className="text-fg-dim uppercase tracking-wider">rows</span>
          <span className="text-fg">
            {formatNumber((page - 1) * PAGE_SIZE + 1)}–
            {formatNumber(Math.min(page * PAGE_SIZE, total))}
          </span>
          <span className="text-fg-dim">of</span>
          <span className="text-fg">{formatNumber(total)}</span>

          <ColumnsMenu
            allColumns={allColumns}
            hidden={hidden}
            onChange={setHidden}
          />

          <div className="ml-auto flex items-center gap-1">
            <PageBtn onClick={() => setPage(1)} disabled={page === 1}>
              <ChevronsLeft className="h-3.5 w-3.5" />
            </PageBtn>
            <PageBtn onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              <ChevronLeft className="h-3.5 w-3.5" />
            </PageBtn>
            <span className="px-2 text-fg">
              {page} / {totalPages}
            </span>
            <PageBtn
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </PageBtn>
            <PageBtn
              onClick={() => setPage(totalPages)}
              disabled={page >= totalPages}
            >
              <ChevronsRight className="h-3.5 w-3.5" />
            </PageBtn>
          </div>
        </div>

        <div className="flex-1 overflow-auto scrollbar-thin">
          <table className="w-full border-collapse font-mono text-xs">
            <thead className="sticky top-0 z-10 bg-bg-panel">
              <tr className="border-b border-border">
                {visibleColumns.map((col) => {
                  const f = schema.find((s) => s.column === col);
                  const isActive = orderBy === col;
                  return (
                    <th
                      key={col}
                      onClick={() => handleSort(col)}
                      className={cn(
                        "cursor-pointer border-r border-border px-3 py-1.5 text-left font-medium uppercase tracking-wider transition-colors hover:bg-bg-elevated",
                        isActive ? "text-accent" : "text-fg-muted"
                      )}
                    >
                      <div className="flex items-center gap-1">
                        <span>{col}</span>
                        {isActive && (
                          <span className="text-[10px]">{descending ? "▼" : "▲"}</span>
                        )}
                        {f && (
                          <span className="ml-auto text-[9px] text-fg-dim">{f.dtype}</span>
                        )}
                      </div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className={cn(
                    "border-b border-border/50 transition-colors hover:bg-bg-elevated",
                    i % 2 === 1 && "bg-bg-panel/30"
                  )}
                >
                  {visibleColumns.map((col) => {
                    const f = schema.find((s) => s.column === col);
                    const v = row[col];
                    return (
                      <td
                        key={col}
                        className={cn(
                          "border-r border-border/50 px-3 py-1",
                          f?.numeric ? "text-right tabular-nums text-fg" : "text-fg-muted"
                        )}
                      >
                        {formatCell(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {dataQ.isLoading && (
                <tr>
                  <td
                    colSpan={visibleColumns.length || 1}
                    className="px-3 py-4 text-center text-fg-dim"
                  >
                    loading…
                  </td>
                </tr>
              )}
              {!dataQ.isLoading && rows.length === 0 && (
                <tr>
                  <td
                    colSpan={visibleColumns.length || 1}
                    className="px-3 py-4 text-center text-fg-dim"
                  >
                    no data
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ColumnsMenu({
  allColumns,
  hidden,
  onChange,
}: {
  allColumns: string[];
  hidden: Set<string>;
  onChange: (s: Set<string>) => void;
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

  const toggle = (col: string) => {
    const next = new Set(hidden);
    if (next.has(col)) next.delete(col);
    else next.add(col);
    onChange(next);
  };

  const shown = allColumns.length - hidden.size;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs transition-colors",
          open
            ? "border-accent text-accent"
            : "border-border text-fg-muted hover:border-accent hover:text-accent"
        )}
        title="Show/hide columns"
      >
        <Columns3 className="h-3 w-3" />
        columns
        <span className="text-fg-dim">
          ({shown}/{allColumns.length})
        </span>
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-56 rounded border border-border-strong bg-bg-panel shadow-xl">
          <div className="flex items-center gap-2 border-b border-border px-2 py-1.5 text-[11px]">
            <button
              onClick={() => onChange(new Set())}
              className="rounded border border-border px-1.5 py-0.5 text-fg-muted transition-colors hover:border-accent hover:text-accent"
            >
              all
            </button>
            <button
              onClick={() => onChange(new Set(allColumns))}
              className="rounded border border-border px-1.5 py-0.5 text-fg-muted transition-colors hover:border-accent hover:text-accent"
            >
              none
            </button>
          </div>
          <div className="max-h-72 overflow-y-auto scrollbar-thin py-1">
            {allColumns.map((col) => {
              const isHidden = hidden.has(col);
              return (
                <button
                  key={col}
                  onClick={() => toggle(col)}
                  className="flex w-full items-center gap-2 px-2 py-1 text-left text-xs hover:bg-bg-elevated"
                >
                  <span
                    className={cn(
                      "flex h-3 w-3 items-center justify-center rounded-sm border",
                      isHidden
                        ? "border-border"
                        : "border-accent bg-accent/20 text-accent"
                    )}
                  >
                    {!isHidden && <span className="text-[9px] leading-none">✓</span>}
                  </span>
                  <span className={cn(isHidden ? "text-fg-dim" : "text-fg")}>{col}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function PageBtn({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded border border-border p-1 transition-colors",
        disabled ? "text-fg-dim" : "text-fg hover:border-accent hover:text-accent"
      )}
    >
      {children}
    </button>
  );
}
