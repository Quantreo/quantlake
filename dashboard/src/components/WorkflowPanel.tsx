import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Layer, type Workflow, type WorkflowNode } from "@/lib/api";
import type { Selection } from "@/App";
import { cn } from "@/lib/cn";

type NodeKey = string; // "layer/name" e.g. "silver/eth_gas" or "gold/top10_crypto/5m"

const LAYERS: { key: Layer; label: string; accent: string }[] = [
  { key: "bronze", label: "BRONZE", accent: "text-amber-700" },
  { key: "silver", label: "SILVER", accent: "text-zinc-400" },
  { key: "gold", label: "GOLD", accent: "text-accent" },
];

interface Props {
  onSelect: (sel: Selection) => void;
}

export function WorkflowPanel({ onSelect }: Props) {
  const q = useQuery({ queryKey: ["workflow"], queryFn: api.workflow });

  if (q.isLoading) {
    return (
      <div className="flex h-full items-center justify-center font-mono text-xs text-fg-dim">
        loading workflow…
      </div>
    );
  }
  if (q.isError || !q.data) {
    return (
      <div className="flex h-full items-center justify-center font-mono text-xs text-red-400">
        workflow.yaml not found or invalid
      </div>
    );
  }
  return <Graph data={q.data} onSelect={onSelect} />;
}

interface Edge {
  from: NodeKey;
  to: NodeKey;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

function Graph({ data, onSelect }: { data: Workflow; onSelect: (s: Selection) => void }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Map<NodeKey, HTMLDivElement>>(new Map());
  const [edges, setEdges] = useState<Edge[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hovered, setHovered] = useState<NodeKey | null>(null);

  // Adjacency for lineage traversal — forward and reverse.
  const { forward, reverse } = useMemo(() => {
    const fwd = new Map<NodeKey, Set<NodeKey>>();
    const rev = new Map<NodeKey, Set<NodeKey>>();
    for (const layer of ["bronze", "silver", "gold"] as const) {
      for (const [name, node] of Object.entries(data[layer])) {
        const to: NodeKey = `${layer}/${name}`;
        if (!fwd.has(to)) fwd.set(to, new Set());
        if (!rev.has(to)) rev.set(to, new Set());
        for (const src of node.from ?? []) {
          if (!fwd.has(src)) fwd.set(src, new Set());
          if (!rev.has(src)) rev.set(src, new Set());
          fwd.get(src)!.add(to);
          rev.get(to)!.add(src);
        }
      }
    }
    return { forward: fwd, reverse: rev };
  }, [data]);

  // Transitive closure from the hovered node, in both directions.
  const lineage = useMemo<Set<NodeKey> | null>(() => {
    if (!hovered) return null;
    const out = new Set<NodeKey>([hovered]);
    const walk = (start: NodeKey, adj: Map<NodeKey, Set<NodeKey>>) => {
      const stack = [start];
      while (stack.length) {
        const n = stack.pop()!;
        for (const nb of adj.get(n) ?? []) {
          if (!out.has(nb)) {
            out.add(nb);
            stack.push(nb);
          }
        }
      }
    };
    walk(hovered, forward);
    walk(hovered, reverse);
    return out;
  }, [hovered, forward, reverse]);

  useLayoutEffect(() => {
    const measure = () => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      setSize({ w: container.scrollWidth, h: container.scrollHeight });
      const next: Edge[] = [];
      for (const layer of ["silver", "gold"] as const) {
        for (const [name, node] of Object.entries(data[layer])) {
          const toKey: NodeKey = `${layer}/${name}`;
          const toEl = nodeRefs.current.get(toKey);
          if (!toEl) continue;
          const tr = toEl.getBoundingClientRect();
          for (const src of node.from ?? []) {
            const fromEl = nodeRefs.current.get(src as NodeKey);
            if (!fromEl) continue;
            const fr = fromEl.getBoundingClientRect();
            next.push({
              from: src as NodeKey,
              to: toKey,
              x1: fr.right - cr.left + container.scrollLeft,
              y1: fr.top + fr.height / 2 - cr.top + container.scrollTop,
              x2: tr.left - cr.left + container.scrollLeft,
              y2: tr.top + tr.height / 2 - cr.top + container.scrollTop,
            });
          }
        }
      }
      setEdges(next);
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (containerRef.current) ro.observe(containerRef.current);
    for (const el of nodeRefs.current.values()) ro.observe(el);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [data]);

  const registerRef = (key: NodeKey) => (el: HTMLDivElement | null) => {
    if (el) nodeRefs.current.set(key, el);
    else nodeRefs.current.delete(key);
  };

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-auto scrollbar-thin bg-bg"
    >
      <svg
        className="pointer-events-none absolute left-0 top-0"
        width={Math.max(size.w, 1)}
        height={Math.max(size.h, 1)}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#52525b" />
          </marker>
          <marker
            id="arrow-hot"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#f59e0b" />
          </marker>
        </defs>
        {edges.map((e, i) => {
          const inLineage =
            lineage !== null && lineage.has(e.from) && lineage.has(e.to);
          const dim = lineage !== null && !inLineage;
          return (
            <path
              key={i}
              d={bezier(e.x1, e.y1, e.x2, e.y2)}
              stroke={inLineage ? "#f59e0b" : "#52525b"}
              strokeWidth={inLineage ? 1.75 : 1.25}
              fill="none"
              opacity={dim ? 0.15 : 1}
              markerEnd={inLineage ? "url(#arrow-hot)" : "url(#arrow)"}
              style={{ transition: "opacity 120ms, stroke 120ms" }}
            />
          );
        })}
      </svg>

      <div className="relative grid min-w-max grid-cols-3 gap-16 p-6">
        {LAYERS.map((l) => (
          <div key={l.key} className="flex flex-col gap-6">
            <div className={cn("font-mono text-xs font-semibold tracking-wider", l.accent)}>
              {l.label}
            </div>
            {topoSort(l.key, data).map(([name, node]) => {
              const key: NodeKey = `${l.key}/${name}`;
              const inLineage = lineage !== null && lineage.has(key);
              const dim = lineage !== null && !inLineage;
              return (
                <NodeCard
                  key={name}
                  layerKey={l.key}
                  name={name}
                  node={node}
                  source={data.sources[node.source ?? ""]}
                  registerRef={registerRef(key)}
                  onClick={() => onSelect({ layer: l.key, name })}
                  onHover={(h) => setHovered(h ? key : (cur) => (cur === key ? null : cur))}
                  highlighted={inLineage}
                  dim={dim}
                />
              );
            })}
            {Object.keys(data[l.key]).length === 0 && (
              <div className="font-mono text-xs text-fg-dim">no tables</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function bezier(x1: number, y1: number, x2: number, y2: number): string {
  // Forward edge (target to the right of source): smooth S-curve between columns.
  if (x2 > x1 + 20) {
    const dx = Math.max(60, (x2 - x1) * 0.55);
    return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
  }
  // Same-column or backward edge: detour to the right so the curve never
  // crosses through the source/target cards — the arrow exits the right edge,
  // arcs out, and re-enters the target's left edge.
  const r = 64;
  return `M ${x1} ${y1} C ${x1 + r} ${y1}, ${x1 + r} ${y2}, ${x2} ${y2}`;
}

function topoSort(
  layer: Layer,
  data: Workflow
): [string, WorkflowNode][] {
  const entries = Object.entries(data[layer]);
  const names = new Set(entries.map(([n]) => n));
  const deps = new Map<string, string[]>();
  for (const [name, node] of entries) {
    deps.set(
      name,
      (node.from ?? [])
        .filter((f) => f.startsWith(`${layer}/`))
        .map((f) => f.slice(layer.length + 1))
        .filter((d) => names.has(d))
    );
  }
  const ordered: string[] = [];
  const visited = new Set<string>();
  const visit = (n: string) => {
    if (visited.has(n)) return;
    visited.add(n);
    for (const d of deps.get(n) ?? []) visit(d);
    ordered.push(n);
  };
  for (const [name] of entries) visit(name);
  const byName = new Map(entries);
  return ordered.map((n) => [n, byName.get(n)!]);
}

function NodeCard({
  layerKey,
  name,
  node,
  source,
  registerRef,
  onClick,
  onHover,
  highlighted,
  dim,
}: {
  layerKey: Layer;
  name: string;
  node: WorkflowNode;
  source?: { type?: string; modes?: string[]; docs?: string };
  registerRef: (el: HTMLDivElement | null) => void;
  onClick: () => void;
  onHover: (hovering: boolean) => void;
  highlighted: boolean;
  dim: boolean;
}) {
  const baseBorder =
    layerKey === "bronze"
      ? "border-amber-700/40"
      : layerKey === "silver"
      ? "border-zinc-600/50"
      : "border-accent/40";

  return (
    <div
      ref={registerRef}
      onClick={onClick}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
      className={cn(
        "w-64 cursor-pointer rounded border bg-bg-panel p-3 shadow-sm transition-all duration-150",
        highlighted
          ? "border-accent ring-1 ring-accent/60 shadow-accent/10"
          : baseBorder,
        dim && "opacity-35"
      )}
    >
      <div className="mb-2 font-mono text-xs font-semibold text-fg">{name}</div>

      {layerKey === "bronze" && source && (
        <div className="mb-2 space-y-0.5 font-mono text-[10px] text-fg-dim">
          <div>
            <span className="text-fg-muted">source · </span>
            {node.source} <span className="text-fg-dim">({source.type})</span>
          </div>
          {node.grain && (
            <div>
              <span className="text-fg-muted">grain · </span>
              {node.grain}
            </div>
          )}
        </div>
      )}

      {node.transforms && node.transforms.length > 0 && (
        <ul className="space-y-0.5 font-mono text-[10px] text-fg-muted">
          {node.transforms.map((t, i) => (
            <li key={i} className="flex gap-1">
              <span className="text-accent">›</span>
              <span>{t}</span>
            </li>
          ))}
        </ul>
      )}

      {node.notes && (
        <div className="mt-2 font-mono text-[10px] italic text-fg-dim">{node.notes}</div>
      )}
    </div>
  );
}
