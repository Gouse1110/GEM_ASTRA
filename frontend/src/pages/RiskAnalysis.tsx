import { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert, AlertTriangle, RefreshCw, ChevronDown, ChevronUp, Info,
} from "lucide-react";
import {
  fetchRiskAnalysis,
  type RiskData, type RiskFinding,
} from "../lib/api";
import { cn } from "../lib/cn";

// --------------------------------------------------------------------------
// Score band config
// --------------------------------------------------------------------------

const BAND_CONFIG: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  Low:      { bg: "bg-emerald-50",  text: "text-emerald-700", border: "border-emerald-200", dot: "bg-emerald-500" },
  Moderate: { bg: "bg-amber-50",    text: "text-amber-700",   border: "border-amber-200",   dot: "bg-amber-500"   },
  Elevated: { bg: "bg-orange-50",   text: "text-orange-700",  border: "border-orange-200",  dot: "bg-orange-500"  },
  High:     { bg: "bg-red-50",      text: "text-red-700",     border: "border-red-200",     dot: "bg-red-500"     },
};

const RULE_LABELS: Record<string, string> = {
  A: "A — Bid-price similarity",
  B: "B — Bidder co-participation",
  C: "C — Winner rotation",
  D: "D — Participation anomalies",
};

function BandBadge({ band }: { band: string }) {
  const cfg = BAND_CONFIG[band] ?? BAND_CONFIG["Low"];
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border",
      cfg.bg, cfg.text, cfg.border,
    )}>
      <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
      {band}
    </span>
  );
}

function ScoreGauge({ score, band }: { score: number; band: string }) {
  const cfg = BAND_CONFIG[band] ?? BAND_CONFIG["Low"];
  const pct = Math.min(100, Math.max(0, score));
  return (
    <div className={cn("rounded-xl p-5 border text-center", cfg.bg, cfg.border)}>
      <div className={cn("text-4xl font-bold mb-1", cfg.text)}>{score}</div>
      <div className="text-xs text-gem-muted mb-3">out of 100</div>
      <div className="w-full bg-white/60 rounded-full h-2 mb-3">
        <div
          className={cn("h-2 rounded-full transition-all", cfg.dot.replace("bg-", "bg-"))}
          style={{ width: `${pct}%` }}
        />
      </div>
      <BandBadge band={band} />
      <p className="text-xs text-gem-muted mt-2">Review-priority score · not a collusion probability</p>
    </div>
  );
}

// --------------------------------------------------------------------------
// Finding detail
// --------------------------------------------------------------------------

function EvidenceBlock({ finding }: { finding: RiskFinding }) {
  const ev = finding.evidence;

  if (finding.rule === "A" && Array.isArray(ev.pairs)) {
    const pairs = ev.pairs as Array<{
      bidder_a: string; bidder_b: string;
      bid_a: number; bid_b: number; diff_pct: number;
    }>;
    return (
      <div className="space-y-2">
        <p className="text-xs text-gem-muted">
          Category: <span className="font-medium text-gem-text">{String(ev.product_category ?? "—")}</span>
        </p>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gem-border">
              {["Bidder A", "Bidder B", "Bid A (₹)", "Bid B (₹)", "Diff %"].map(h => (
                <th key={h} className="pb-1.5 pr-3 text-left font-medium text-gem-muted">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pairs.map((p, i) => (
              <tr key={i} className="border-b border-gem-border/50">
                <td className="py-1.5 pr-3 font-mono text-gem-emerald">{p.bidder_a}</td>
                <td className="py-1.5 pr-3 font-mono text-gem-emerald">{p.bidder_b}</td>
                <td className="py-1.5 pr-3">₹{p.bid_a.toLocaleString()}</td>
                <td className="py-1.5 pr-3">₹{p.bid_b.toLocaleString()}</td>
                <td className="py-1.5 pr-3 font-semibold text-amber-600">{p.diff_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  if (finding.rule === "B") {
    return (
      <div className="space-y-1 text-sm">
        <p>
          <span className="text-gem-muted">Co-participation count: </span>
          <span className="font-semibold text-gem-text">{String(ev.co_participation_count ?? "—")}</span>
        </p>
        {Array.isArray(ev.shared_tender_ids) && (
          <p>
            <span className="text-gem-muted">Shared tenders: </span>
            <span className="font-mono text-gem-text">{(ev.shared_tender_ids as string[]).join(", ")}</span>
          </p>
        )}
      </div>
    );
  }

  if (finding.rule === "C") {
    const winCounts = ev.win_counts && typeof ev.win_counts === "object"
      ? ev.win_counts as Record<string, number>
      : null;
    return (
      <div className="space-y-1 text-sm">
        <p>
          <span className="text-gem-muted">Total awarded tenders: </span>
          <span className="font-semibold">{String(ev.total_awarded_tenders ?? "—")}</span>
        </p>
        <p>
          <span className="text-gem-muted">Coverage: </span>
          <span className="font-semibold">{String(ev.coverage_pct ?? "—")}%</span>
        </p>
        {winCounts && (
          <div>
            <p className="text-gem-muted mb-1">Win counts:</p>
            {Object.entries(winCounts).map(([b, w]) => (
              <p key={b} className="font-mono text-xs">
                {b}: {w} win{w !== 1 ? "s" : ""}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <pre className="text-xs bg-slate-50 rounded p-2 overflow-auto">
      {JSON.stringify(ev, null, 2)}
    </pre>
  );
}

function FindingRow({ finding, isOpen, onToggle }: {
  finding: RiskFinding;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const isInsuf = finding.insufficient_data;

  return (
    <div className={cn(
      "border border-gem-border rounded-lg overflow-hidden",
      isInsuf ? "opacity-60" : "",
    )}>
      {/* Header row */}
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 p-4 text-left hover:bg-slate-50 transition-colors"
        aria-expanded={isOpen}
      >
        <span className={cn(
          "shrink-0 text-xs font-bold px-2 py-0.5 rounded border mt-0.5",
          isInsuf ? "bg-slate-100 text-slate-500 border-slate-200" : "bg-gem-emerald-soft text-gem-emerald-text border-emerald-200",
        )}>
          {finding.rule}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gem-text">{finding.rule_name}</p>
          <p className="text-xs text-gem-muted mt-0.5 truncate">
            {isInsuf ? finding.data_limitations : (finding.tender_ids.join(", ") || "—")}
          </p>
        </div>
        {!isInsuf && (
          <span className="shrink-0 text-xs text-gem-muted font-mono">
            {finding.bidder_ids.slice(0, 3).join(", ")}{finding.bidder_ids.length > 3 ? "…" : ""}
          </span>
        )}
        {isOpen ? <ChevronUp size={14} className="shrink-0 text-gem-muted" /> : <ChevronDown size={14} className="shrink-0 text-gem-muted" />}
      </button>

      {/* Expanded detail */}
      {isOpen && !isInsuf && (
        <div className="border-t border-gem-border p-4 bg-slate-50/50 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs text-gem-muted mb-0.5">Tender(s)</p>
              <p className="font-mono text-gem-text">{finding.tender_ids.join(", ") || "—"}</p>
            </div>
            <div>
              <p className="text-xs text-gem-muted mb-0.5">Affected bidder(s)</p>
              <p className="font-mono text-gem-text">{finding.bidder_ids.join(", ") || "—"}</p>
            </div>
            <div>
              <p className="text-xs text-gem-muted mb-0.5">Source type</p>
              <p className="text-gem-text">{finding.source_type}</p>
            </div>
            <div>
              <p className="text-xs text-gem-muted mb-0.5">Criterion</p>
              <p className="text-gem-text">{finding.threshold_or_criterion}</p>
            </div>
          </div>
          <div>
            <p className="text-xs text-gem-muted mb-1">Explanation</p>
            <p className="text-sm text-gem-text leading-relaxed">{finding.explanation}</p>
          </div>
          {Object.keys(finding.evidence).length > 0 && (
            <div>
              <p className="text-xs text-gem-muted mb-2">Supporting evidence</p>
              <EvidenceBlock finding={finding} />
            </div>
          )}
          {finding.data_limitations && (
            <p className="text-xs text-gem-muted flex items-start gap-1">
              <Info size={11} className="mt-0.5 shrink-0" />
              {finding.data_limitations}
            </p>
          )}
        </div>
      )}

      {isOpen && isInsuf && (
        <div className="border-t border-gem-border p-4 bg-slate-50/50">
          <p className="text-xs text-gem-muted">{finding.data_limitations}</p>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------
// Main page
// --------------------------------------------------------------------------

export function RiskAnalysis() {
  const [data, setData] = useState<RiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [ruleFilter, setRuleFilter] = useState("All");
  const [showInsufficient, setShowInsufficient] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchRiskAnalysis()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div className="max-w-5xl mx-auto card flex items-center justify-center py-16 gap-3">
      <RefreshCw size={16} className="animate-spin text-gem-muted" />
      <span className="text-sm text-gem-muted">Running analysis…</span>
    </div>
  );

  if (error) return (
    <div className="max-w-5xl mx-auto card flex items-center gap-3 py-8">
      <ShieldAlert size={20} className="text-red-500 shrink-0" />
      <div>
        <p className="text-sm font-medium text-gem-text">Could not load risk analysis</p>
        <p className="text-xs text-gem-muted mt-1">{error}</p>
        <button onClick={load} className="mt-2 text-xs text-gem-emerald hover:underline">Retry</button>
      </div>
    </div>
  );

  if (!data) return null;

  const { summary, findings, source_label } = data;
  const isSynthetic = source_label.toLowerCase().includes("synthetic");

  // Filter findings for display
  const visible = findings.filter(f => {
    if (!showInsufficient && f.insufficient_data) return false;
    if (ruleFilter !== "All" && f.rule !== ruleFilter) return false;
    return true;
  });

  const actionable = findings.filter(f => !f.insufficient_data);
  const availableRules = [...new Set(actionable.map(f => f.rule))].sort();

  return (
    <div className="max-w-5xl mx-auto space-y-5">

      {/* Disclaimer */}
      <div className="flex gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200">
        <AlertTriangle size={15} className="text-amber-600 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-800 leading-relaxed">
          <span className="font-semibold">Review-priority indicators only — </span>
          {data.disclaimer}
        </p>
      </div>

      {/* Synthetic warning */}
      {isSynthetic && (
        <div className="flex gap-3 p-3 rounded-xl bg-amber-50 border border-amber-200">
          <span className="text-sm shrink-0 mt-0.5">🧪</span>
          <p className="text-xs text-amber-800 leading-relaxed">
            <span className="font-semibold">Synthetic demo data — </span>
            Findings are generated from <code>demo_bids.csv</code> (artificial records, not real GeM procurement).
            Source: <span className="font-medium">{source_label}</span>
          </p>
        </div>
      )}

      {/* Engine warnings */}
      {summary.warnings.map((w, i) => (
        <div key={i} className="text-xs text-gem-muted flex items-start gap-2 px-1">
          <Info size={12} className="mt-0.5 shrink-0" />
          {w}
        </div>
      ))}

      {/* Score + summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <ScoreGauge score={summary.score} band={summary.score_band} />
        <div className="lg:col-span-2 card space-y-4">
          <h3 className="text-xs font-semibold text-gem-muted uppercase tracking-wide">Analysis summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Bids analysed",     value: summary.total_bids_analysed },
              { label: "Actionable findings", value: summary.actionable_findings_count },
              { label: "Rules fired",        value: summary.rules_fired.join(", ") || "None" },
              { label: "Data source",        value: summary.source_type },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-xs text-gem-muted mb-0.5">{label}</p>
                <p className="text-sm font-semibold text-gem-text">{value}</p>
              </div>
            ))}
          </div>
          <div>
            <p className="text-xs text-gem-muted mb-1">Score breakdown</p>
            <p className="text-xs text-gem-muted leading-relaxed">{summary.score_explanation}</p>
          </div>
        </div>
      </div>

      {/* Findings list */}
      <div className="card space-y-4">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <h3 className="text-xs font-semibold text-gem-muted uppercase tracking-wide">
            Findings ({actionable.length} actionable)
          </h3>
          <div className="flex flex-wrap gap-3 items-center">
            {/* Rule filter */}
            <select
              value={ruleFilter}
              onChange={e => { setRuleFilter(e.target.value); setOpenIdx(null); }}
              className="select text-xs py-1.5 min-w-36"
            >
              <option value="All">All rules</option>
              {availableRules.map(r => (
                <option key={r} value={r}>{RULE_LABELS[r] ?? r}</option>
              ))}
            </select>
            {/* Insufficient toggle */}
            <label className="flex items-center gap-1.5 text-xs text-gem-muted cursor-pointer">
              <input
                type="checkbox"
                checked={showInsufficient}
                onChange={e => setShowInsufficient(e.target.checked)}
                className="accent-gem-emerald"
              />
              Show unavailable rules
            </label>
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="py-8 text-center">
            <ShieldAlert size={24} className="text-gem-muted mx-auto mb-2" />
            <p className="text-sm text-gem-muted">No findings match the current filters.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {visible.map((f, i) => (
              <FindingRow
                key={`${f.rule}-${f.tender_ids.join(",")}-${i}`}
                finding={f}
                isOpen={openIdx === i}
                onToggle={() => setOpenIdx(openIdx === i ? null : i)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
