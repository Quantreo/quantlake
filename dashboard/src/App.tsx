import { useEffect, useState } from "react";
import { Sidebar } from "./components/Sidebar";
import { ChartPanel } from "./components/ChartPanel";
import { TablePanel } from "./components/TablePanel";
import { TableHeader } from "./components/TableHeader";
import { WorkflowPanel } from "./components/WorkflowPanel";
import { useQuery } from "@tanstack/react-query";
import { api, type Layer } from "./lib/api";

export interface Selection {
  layer: Layer;
  name: string;
}

export function App() {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [tsFrom, setTsFrom] = useState<string | null>(null);
  const [tsTo, setTsTo] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [normalized, setNormalized] = useState(false);
  const [view, setView] = useState<"chart" | "workflow">("chart");

  const schemaQuery = useQuery({
    queryKey: ["schema", selection?.layer, selection?.name],
    queryFn: () => api.schema(selection!.layer, selection!.name),
    enabled: !!selection,
  });

  const tablesQuery = useQuery({
    queryKey: ["tables", selection?.layer],
    queryFn: () => api.tables(selection!.layer),
    enabled: !!selection,
  });

  // Auto-select first symbol when selection changes — "all" mixes symbols
  // in series queries and produces unusable zigzag charts.
  useEffect(() => {
    if (!selection) return;
    const t = tablesQuery.data?.tables.find((x) => x.name === selection.name);
    if (t && t.symbols.length > 0) setSymbols([t.symbols[0]]);
    else setSymbols([]);
    setTsFrom(null);
    setTsTo(null);
  }, [selection?.layer, selection?.name, tablesQuery.data]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-bg text-fg">
      <Sidebar
        selection={selection}
        onSelect={(s) => { setSelection(s); setSymbols([]); }}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={() => setSidebarCollapsed((c) => !c)}
      />

      <main className="flex flex-1 flex-col overflow-hidden">
        {!selection ? (
          <EmptyState />
        ) : (
          <>
            <TableHeader
              selection={selection}
              schema={schemaQuery.data?.schema ?? []}
              symbols={symbols}
              onSymbolsChange={setSymbols}
              tsFrom={tsFrom}
              tsTo={tsTo}
              onTsFromChange={setTsFrom}
              onTsToChange={setTsTo}
              normalized={normalized}
              onToggleNormalized={() => setNormalized((v) => !v)}
              view={view}
              onViewChange={setView}
            />
            {view === "workflow" ? (
              <div className="flex-1 min-h-0">
                <WorkflowPanel
                  onSelect={(s) => {
                    setSelection(s);
                    setView("chart");
                  }}
                />
              </div>
            ) : (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-1 min-h-0 border-b border-border">
                  <ChartPanel
                    selection={selection}
                    schema={schemaQuery.data?.schema ?? []}
                    symbols={symbols}
                    tsFrom={tsFrom}
                    tsTo={tsTo}
                    normalized={normalized}
                  />
                </div>
                <div className="h-[40%] min-h-0">
                  <TablePanel
                    selection={selection}
                    schema={schemaQuery.data?.schema ?? []}
                    symbols={symbols}
                    tsFrom={tsFrom}
                    tsTo={tsTo}
                  />
                </div>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center text-fg-muted">
      <div className="font-mono text-sm tracking-wide">
        <span className="text-accent">▸</span> SELECT A TABLE FROM THE SIDEBAR
      </div>
      <div className="mt-2 text-xs text-fg-dim">bronze · silver · gold</div>
    </div>
  );
}
