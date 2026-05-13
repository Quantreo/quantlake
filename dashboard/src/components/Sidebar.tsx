import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Database, Search } from "lucide-react";
import { api, type Layer, type TableInfo } from "@/lib/api";
import { cn, formatNumber, formatTimestamp } from "@/lib/cn";
import type { Selection } from "@/App";

const LAYERS: { id: Layer; label: string; accent: string }[] = [
  { id: "bronze", label: "BRONZE", accent: "text-amber-700" },
  { id: "silver", label: "SILVER", accent: "text-zinc-400" },
  { id: "gold",   label: "GOLD",   accent: "text-accent" },
];

interface Props {
  selection: Selection | null;
  onSelect: (s: Selection) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function Sidebar({ selection, onSelect, collapsed, onToggleCollapsed }: Props) {
  const [open, setOpen] = useState<Record<Layer, boolean>>({
    bronze: true,
    silver: true,
    gold: true,
  });
  const [filter, setFilter] = useState("");

  if (collapsed) {
    return (
      <aside className="flex w-10 flex-col items-center border-r border-border bg-bg-panel">
        <button
          onClick={onToggleCollapsed}
          className="flex h-12 w-full items-center justify-center border-b border-border text-accent transition-colors hover:bg-bg-elevated"
          title="Expand sidebar"
        >
          <Database className="h-4 w-4" />
        </button>
        <button
          onClick={onToggleCollapsed}
          className="flex h-8 w-full items-center justify-center text-fg-muted transition-colors hover:bg-bg-elevated hover:text-fg"
          title="Expand sidebar"
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="flex w-72 flex-col border-r border-border bg-bg-panel">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Database className="h-4 w-4 text-accent" />
        <span className="font-mono text-sm font-semibold tracking-wide">QUANTLAKE</span>
        <button
          onClick={onToggleCollapsed}
          className="ml-auto rounded p-1 text-fg-muted transition-colors hover:bg-bg-elevated hover:text-fg"
          title="Collapse sidebar"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="border-b border-border px-3 py-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-dim" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Search tables…"
            className="w-full rounded border border-border bg-bg px-7 py-1.5 text-xs text-fg placeholder:text-fg-dim focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {LAYERS.map((layer) => (
          <LayerSection
            key={layer.id}
            layer={layer}
            isOpen={open[layer.id]}
            onToggle={() => setOpen((o) => ({ ...o, [layer.id]: !o[layer.id] }))}
            filter={filter.toLowerCase()}
            selection={selection}
            onSelect={onSelect}
          />
        ))}
      </div>

      <div className="border-t border-border px-4 py-2 font-mono text-xs text-fg-dim">
        medallion · delta lake
      </div>
    </aside>
  );
}

function LayerSection({
  layer,
  isOpen,
  onToggle,
  filter,
  selection,
  onSelect,
}: {
  layer: typeof LAYERS[number];
  isOpen: boolean;
  onToggle: () => void;
  filter: string;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) {
  const q = useQuery({
    queryKey: ["tables", layer.id],
    queryFn: () => api.tables(layer.id),
  });

  const tables = (q.data?.tables ?? []).filter((t) =>
    !filter || t.name.toLowerCase().includes(filter)
  );

  return (
    <div className="border-b border-border">
      <button
        onClick={onToggle}
        className="group flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-bg-elevated"
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 text-fg-muted transition-transform",
            isOpen && "rotate-90"
          )}
        />
        <span className={cn("font-mono text-xs font-semibold tracking-wider", layer.accent)}>
          {layer.label}
        </span>
        <span className="ml-auto font-mono text-xs text-fg-dim">
          {q.data ? tables.length : "·"}
        </span>
      </button>

      {isOpen && (
        <div className="pb-1">
          {q.isLoading && <div className="px-6 py-1 font-mono text-xs text-fg-dim">loading…</div>}
          {!q.isLoading && tables.length === 0 && (
            <div className="px-6 py-1 font-mono text-xs text-fg-dim">no tables</div>
          )}
          {tables.map((t) => (
            <TableRow
              key={`${t.layer}/${t.name}`}
              table={t}
              active={
                selection?.layer === t.layer && selection?.name === t.name
              }
              onSelect={() => onSelect({ layer: t.layer, name: t.name })}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function TableRow({
  table,
  active,
  onSelect,
}: {
  table: TableInfo;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        "flex w-full flex-col items-start px-6 py-1.5 text-left transition-colors",
        active ? "bg-accent/10 border-l-2 border-accent" : "border-l-2 border-transparent hover:bg-bg-elevated"
      )}
    >
      <span className={cn("font-mono text-xs", active ? "text-accent" : "text-fg")}>
        {table.name}
      </span>
      <span className="font-mono text-[10px] text-fg-dim">
        {formatNumber(table.rows)} rows · {formatTimestamp(table.last_update)}
      </span>
    </button>
  );
}
