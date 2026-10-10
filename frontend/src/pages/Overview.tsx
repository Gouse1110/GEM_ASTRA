import { useEffect, useState } from "react";
import { Database, FileText, Users, ShieldAlert, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { MetricCard } from "../components/ui/MetricCard";
import { EmptyState } from "../components/ui/EmptyState";
import { fetchHealth, fetchSummary, type SummaryData } from "../lib/api";

type ApiStatus = "checking" | "online" | "offline";

// Badge shown under metrics sourced from synthetic demo data
function SyntheticNote() {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium
      px-1.5 py-0.5 rounded bg-amber-50 border border-amber-200 text-amber-700">
      🧪 synthetic demo
    </span>
  );
}

export function Overview() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryError, setSummaryError] = useState(false);

  useEffect(() => {
    fetchHealth()
      .then(() => setApiStatus("online"))
      .catch(() => setApiStatus("offline"));
  }, []);

  useEffect(() => {
    if (apiStatus === "online") {
      fetchSummary()
        .then(setSummary)
        .catch(() => setSummaryError(true));
    }
  }, [apiStatus]);

  const isSynthetic = (source: string) => source.includes("synthetic");

  return (
    <div className="max-w-5xl mx-auto space-y-8">

      {/* Disclaimer */}
      <div className="flex gap-3 p-4 rounded-xl bg-amber-50 border border-amber-200">
        <ShieldAlert size={16} className="text-amber-600 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-800 leading-relaxed">
          <span className="font-semibold">Disclaimer — </span>
          Risk indicators surfaced by this platform are analytical signals only.
          They are not evidence of collusion, fraud, or wrongdoing.
          All findings require expert human review before any action is taken.
        </p>
      </div>

      {/* API status */}
      <div className="flex items-center gap-2 text-xs">
        <span className={`w-1.5 h-1.5 rounded-full ${
          apiStatus === "online"  ? "bg-gem-emerald" :
          apiStatus === "offline" ? "bg-red-500"     :
          "bg-gem-subtle animate-pulse"
        }`} />
        <span className="text-gem-muted">
          {apiStatus === "checking" && "Checking API…"}
          {apiStatus === "online"   && "API online · http://localhost:8000"}
          {apiStatus === "offline"  && "API offline — start the FastAPI server"}
        </span>
      </div>

      {/* Metrics */}
      <section>
        <h2 className="section-label">Platform summary</h2>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

          {/* Tenders in DB — real public data from SQLite */}
          <MetricCard
            label="Tenders in DB"
            value={summary?.tender_count ?? "—"}
            icon={Database}
            sub={
              summary
                ? `${summary.tender_count} verified public record${summary.tender_count !== 1 ? "s" : ""}`
                : summaryError ? "Unavailable" : "Loading…"
            }
            accent="emerald"
            empty={summary === null}
          />

          {/* Bid records — synthetic demo */}
          <MetricCard
            label="Bid records"
            value={summary?.bid_record_count ?? "—"}
            icon={FileText}
            sub={
              summary
                ? summary.bid_source_label
                : summaryError ? "Unavailable" : "Loading…"
            }
            accent="slate"
            empty={summary === null}
          />

          {/* Unique bidders — synthetic demo */}
          <MetricCard
            label="Unique bidders"
            value={summary?.unique_bidder_count ?? "—"}
            icon={Users}
            sub={
              summary
                ? summary.bid_source_label
                : summaryError ? "Unavailable" : "Loading…"
            }
            accent="slate"
            empty={summary === null}
          />

          {/* Active findings — risk engine on demo bids */}
          <MetricCard
            label="Active findings"
            value={summary?.active_findings_count ?? "—"}
            icon={ShieldAlert}
            sub={
              summary
                ? summary.findings_source_label
                : summaryError ? "Unavailable" : "Loading…"
            }
            accent="amber"
            empty={summary === null || summary.active_findings_count === null}
          />

        </div>

        {/* Source clarification */}
        {summary && (
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-gem-muted">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-gem-emerald inline-block" />
              Tenders: verified public records (SQLite)
            </span>
            {isSynthetic(summary.bid_source) && (
              <span className="flex items-center gap-1">
                <SyntheticNote />
                Bid records, bidders & findings: synthetic demo data only — not real GeM procurement
              </span>
            )}
          </div>
        )}
        {summaryError && (
          <p className="mt-3 text-xs text-red-500">
            Could not load summary metrics. Check the API server is running.
          </p>
        )}
      </section>

      {/* How it works */}
      <section>
        <h2 className="section-label">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            {
              step: "01",
              title: "Import Tenders",
              body: "Load verified GeM tender metadata via the Tender Explorer. Only confirmed public records should be marked as real data.",
              to: "/tenders",
            },
            {
              step: "02",
              title: "Run Risk Analysis",
              body: "The detection engine screens bids for price similarity, repeated co-participation, and possible winner rotation.",
              to: "/risk",
            },
            {
              step: "03",
              title: "Review Findings",
              body: "Investigators examine flagged patterns, review supporting evidence, and generate structured reports for compliance teams.",
              to: "/reports",
            },
          ].map(({ step, title, body, to }) => (
            <div key={step} className="card hover:shadow-elevated hover:border-emerald-200 transition-all duration-150">
              <div className="text-[10px] font-mono text-gem-emerald mb-2 tracking-widest">{step}</div>
              <h3 className="text-sm font-semibold text-gem-text mb-2">{title}</h3>
              <p className="text-xs text-gem-muted leading-relaxed mb-4">{body}</p>
              <Link
                to={to}
                className="inline-flex items-center gap-1 text-xs text-gem-emerald hover:text-gem-emerald-hover transition-colors font-medium"
              >
                Go to {title} <ArrowRight size={11} />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* Empty state — only when tenders table is genuinely empty */}
      {summary?.tender_count === 0 && (
        <div className="card">
          <EmptyState
            icon={Database}
            title="No tender records loaded"
            description="Import verified GeM tender records via the Tender Explorer to begin analysis."
            action={
              <Link
                to="/tenders"
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gem-emerald text-sm font-medium text-white hover:bg-gem-emerald-hover transition-colors"
              >
                Go to Tender Explorer <ArrowRight size={13} />
              </Link>
            }
          />
        </div>
      )}
    </div>
  );
}
