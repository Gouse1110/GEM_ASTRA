import { useEffect, useState, useCallback } from "react";
import { Network, AlertTriangle, RefreshCw } from "lucide-react";
import { fetchNetwork, type NetworkData, type BidderNode, type BidderEdge } from "../lib/api";
import { cn } from "../lib/cn";

// --------------------------------------------------------------------------
// Layout: arrange nodes in a circle
// --------------------------------------------------------------------------

const W = 600;
const H = 500;
const CX = W / 2;
const CY = H / 2;
const R = 190; // circle radius for nodes

function circlePositions(nodes: BidderNode[]): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    pos.set(n.bidder_id, {
      x: CX + R * Math.cos(angle),
      y: CY + R * Math.sin(angle),
    });
  });
  return pos;
}

// Edge stroke width scales with shared tender count
function edgeWidth(count: number): number {
  return Math.min(1 + count * 1.2, 6);
}

// --------------------------------------------------------------------------
// Edge colour by strength
// --------------------------------------------------------------------------

function edgeColor(count: number, selected: boolean): string {
  if (selected) return "#059669"; // emerald
  if (count >= 3) return "#d97706"; // amber — strong connection
  return "#cbd5e1"; // slate-300 — weak
}

// --------------------------------------------------------------------------
// Network SVG
// --------------------------------------------------------------------------

interface SVGNetworkProps {
  data: NetworkData;
  selected: string | null;
  onSelect: (id: string | null) => void;
}

function SVGNetwork({ data, selected, onSelect }: SVGNetworkProps) {
  const pos = circlePositions(data.nodes);

  const isHighlighted = (edge: BidderEdge) =>
    selected !== null &&
    (edge.bidder_a === selected || edge.bidder_b === selected);

  const isConnected = (nodeId: string) =>
    selected === null ||
    nodeId === selected ||
    data.edges.some(
      (e) =>
        (e.bidder_a === selected && e.bidder_b === nodeId) ||
        (e.bidder_b === selected && e.bidder_a === nodeId)
    );

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full max-w-xl mx-auto"
      style={{ height: 420 }}
      aria-label="Bidder co-participation network"
    >
      {/* Edges */}
      {data.edges.map((e) => {
        const a = pos.get(e.bidder_a);
        const b = pos.get(e.bidder_b);
        if (!a || !b) return null;
        const hi = isHighlighted(e);
        const dim = selected !== null && !hi;
        return (
          <line
            key={`${e.bidder_a}-${e.bidder_b}`}
            x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={edgeColor(e.shared_tender_count, hi)}
            strokeWidth={edgeWidth(e.shared_tender_count)}
            strokeOpacity={dim ? 0.15 : 0.8}
            strokeLinecap="round"
          />
        );
      })}

      {/* Nodes */}
      {data.nodes.map((n) => {
        const p = pos.get(n.bidder_id);
        if (!p) return null;
        const isSelected = n.bidder_id === selected;
        const dim = selected !== null && !isConnected(n.bidder_id);
        // Label position — push outward from centre
        const dx = p.x - CX;
        const dy = p.y - CY;
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const lx = p.x + (dx / len) * 22;
        const ly = p.y + (dy / len) * 22;
        const anchor = dx > 10 ? "start" : dx < -10 ? "end" : "middle";
        const labelDy = dy > 10 ? "1em" : dy < -10 ? "-0.3em" : "0.35em";

        return (
          <g
            key={n.bidder_id}
            onClick={() => onSelect(isSelected ? null : n.bidder_id)}
            className="cursor-pointer"
            role="button"
            aria-label={`Bidder ${n.bidder_id}, ${n.tender_count} tender(s)`}
            tabIndex={0}
            onKeyDown={(ev) => ev.key === "Enter" && onSelect(isSelected ? null : n.bidder_id)}
          >
            <circle
              cx={p.x} cy={p.y}
              r={isSelected ? 13 : 9}
              fill={isSelected ? "#059669" : dim ? "#e2e8f0" : "#0f172a"}
              stroke={isSelected ? "#d1fae5" : "#ffffff"}
              strokeWidth={2}
              opacity={dim ? 0.3 : 1}
            />
            <text
              x={lx} y={ly}
              dy={labelDy}
              textAnchor={anchor}
              fontSize={10}
              fontFamily="Inter, system-ui, sans-serif"
              fontWeight={isSelected ? 700 : 400}
              fill={dim ? "#94a3b8" : isSelected ? "#059669" : "#334155"}
              opacity={dim ? 0.4 : 1}
            >
              {n.bidder_id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// --------------------------------------------------------------------------
// Detail panel
// --------------------------------------------------------------------------

function DetailPanel({
  bidder,
  edges,
  onClose,
}: {
  bidder: BidderNode;
  edges: BidderEdge[];
  onClose: () => void;
}) {
  const myEdges = edges.filter(
    (e) => e.bidder_a === bidder.bidder_id || e.bidder_b === bidder.bidder_id
  );
  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-gem-muted mb-0.5">Selected bidder</p>
          <h3 className="text-base font-semibold text-gem-text">{bidder.bidder_id}</h3>
          <p className="text-xs text-gem-muted mt-0.5">
            {bidder.tender_count} tender{bidder.tender_count !== 1 ? "s" : ""} participated
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gem-muted hover:text-gem-text text-xs px-2 py-1 rounded border border-gem-border"
        >
          Clear
        </button>
      </div>

      {myEdges.length === 0 ? (
        <p className="text-xs text-gem-muted">No co-participation edges for this bidder.</p>
      ) : (
        <div>
          <p className="text-xs font-medium text-gem-muted uppercase tracking-wide mb-2">
            Co-participated with
          </p>
          <div className="space-y-2">
            {myEdges.map((e) => {
              const other = e.bidder_a === bidder.bidder_id ? e.bidder_b : e.bidder_a;
              return (
                <div
                  key={other}
                  className="flex items-start justify-between gap-3 p-2 rounded-lg bg-slate-50 border border-gem-border text-sm"
                >
                  <div>
                    <span className="font-medium text-gem-text">{other}</span>
                    <p className="text-xs text-gem-muted mt-0.5">
                      Shared: {e.shared_tender_ids.join(", ")}
                    </p>
                  </div>
                  <span className={cn(
                    "shrink-0 text-xs font-semibold px-2 py-0.5 rounded-full",
                    e.shared_tender_count >= 3
                      ? "bg-amber-100 text-amber-700"
                      : "bg-slate-100 text-slate-600"
                  )}>
                    {e.shared_tender_count} tender{e.shared_tender_count !== 1 ? "s" : ""}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Legend
// --------------------------------------------------------------------------

function Legend() {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-gem-muted">
      <span className="flex items-center gap-1.5">
        <svg width={24} height={6}>
          <line x1={0} y1={3} x2={24} y2={3} stroke="#d97706" strokeWidth={3} />
        </svg>
        Strong link (≥3 shared tenders)
      </span>
      <span className="flex items-center gap-1.5">
        <svg width={24} height={6}>
          <line x1={0} y1={3} x2={24} y2={3} stroke="#cbd5e1" strokeWidth={1.5} />
        </svg>
        Weak link (1–2 shared tenders)
      </span>
      <span className="flex items-center gap-1.5">
        <svg width={16} height={16}>
          <circle cx={8} cy={8} r={7} fill="#059669" />
        </svg>
        Selected bidder
      </span>
    </div>
  );
}

// --------------------------------------------------------------------------
// Main page
// --------------------------------------------------------------------------

export function BidderNetwork() {
  const [data, setData] = useState<NetworkData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchNetwork()
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load network")
      )
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const selectedNode = data?.nodes.find((n) => n.bidder_id === selected) ?? null;

  return (
    <div className="max-w-5xl mx-auto space-y-5">

      {/* Synthetic disclaimer */}
      <div className="flex gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200">
        <AlertTriangle size={15} className="text-amber-600 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-800 leading-relaxed">
          <span className="font-semibold">🧪 Synthetic demo data — </span>
          This network is built from <code>demo_bids.csv</code> (artificial records).
          Shared participation is a review signal only — it is{" "}
          <strong>not evidence of coordination or collusion</strong>.
          Do not treat these relationships as real GeM findings.
        </p>
      </div>

      {loading && (
        <div className="card flex items-center justify-center py-16 gap-3">
          <RefreshCw size={16} className="animate-spin text-gem-muted" />
          <span className="text-sm text-gem-muted">Loading network…</span>
        </div>
      )}

      {error && (
        <div className="card flex items-center gap-3 py-8 text-red-600">
          <Network size={20} className="shrink-0" />
          <div>
            <p className="text-sm font-medium">Could not load bidder network</p>
            <p className="text-xs text-gem-muted mt-1">{error}</p>
            <button onClick={load} className="mt-2 text-xs text-gem-emerald hover:underline">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && data && data.total_bidders === 0 && (
        <div className="card flex flex-col items-center py-16 text-center">
          <Network size={28} className="text-gem-muted mb-3" />
          <p className="text-sm text-gem-text mb-1">No bidder data available</p>
          <p className="text-xs text-gem-muted max-w-xs">
            The synthetic bid dataset is empty. Load bid records to view the network.
          </p>
        </div>
      )}

      {!loading && !error && data && data.total_bidders > 0 && (
        <>
          {/* Summary row */}
          <div className="flex flex-wrap gap-4">
            {[
              { label: "Bidders", value: data.total_bidders },
              { label: "Co-participation links", value: data.total_edges },
              { label: "Data source", value: data.source_label },
            ].map(({ label, value }) => (
              <div key={label} className="card flex-1 min-w-36 py-3">
                <p className="text-xs text-gem-muted uppercase tracking-wide mb-1">{label}</p>
                <p className="text-base font-semibold text-gem-text">{value}</p>
              </div>
            ))}
          </div>

          {/* Main layout: graph + detail */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Graph */}
            <div className="lg:col-span-2 card">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-medium text-gem-muted">
                  Click a node to inspect connections
                </p>
                {selected && (
                  <button
                    onClick={() => setSelected(null)}
                    className="text-xs text-gem-emerald hover:underline"
                  >
                    Clear selection
                  </button>
                )}
              </div>
              <SVGNetwork data={data} selected={selected} onSelect={setSelected} />
              <div className="mt-3">
                <Legend />
              </div>
            </div>

            {/* Detail panel / instructions */}
            <div>
              {selectedNode ? (
                <DetailPanel
                  bidder={selectedNode}
                  edges={data.edges}
                  onClose={() => setSelected(null)}
                />
              ) : (
                <div className="card h-full flex flex-col justify-center items-center text-center py-10 gap-3">
                  <Network size={24} className="text-gem-muted" />
                  <p className="text-sm text-gem-muted">
                    Select a bidder node to see which other bidders it co-participated with
                    and which tenders they shared.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Edge table */}
          <div className="card">
            <h3 className="text-xs font-semibold text-gem-muted uppercase tracking-wide mb-3">
              All co-participation links
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gem-border text-left">
                    {["Bidder A", "Bidder B", "Shared tenders", "Tender IDs"].map((h) => (
                      <th key={h} className="pb-2 pr-4 text-xs font-medium text-gem-muted uppercase tracking-wide whitespace-nowrap">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.edges
                    .slice()
                    .sort((a, b) => b.shared_tender_count - a.shared_tender_count)
                    .map((e) => (
                      <tr
                        key={`${e.bidder_a}-${e.bidder_b}`}
                        className={cn(
                          "border-b border-gem-border hover:bg-slate-50 cursor-pointer transition-colors",
                          selected === e.bidder_a || selected === e.bidder_b
                            ? "bg-gem-emerald-soft"
                            : ""
                        )}
                        onClick={() => setSelected(e.bidder_a)}
                      >
                        <td className="py-2 pr-4 font-mono text-xs text-gem-emerald">{e.bidder_a}</td>
                        <td className="py-2 pr-4 font-mono text-xs text-gem-emerald">{e.bidder_b}</td>
                        <td className="py-2 pr-4">
                          <span className={cn(
                            "text-xs font-semibold px-2 py-0.5 rounded-full",
                            e.shared_tender_count >= 3
                              ? "bg-amber-100 text-amber-700"
                              : "bg-slate-100 text-slate-600"
                          )}>
                            {e.shared_tender_count}
                          </span>
                        </td>
                        <td className="py-2 pr-4 text-xs text-gem-muted font-mono">
                          {e.shared_tender_ids.join(", ")}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
