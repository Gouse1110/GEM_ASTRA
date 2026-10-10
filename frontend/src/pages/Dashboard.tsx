import { ShieldAlert, FileText, Users, BarChart2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "../lib/auth";

const ROLE_CONFIG = {
  official: {
    title: "Government Official Dashboard",
    description:
      "Publish contracts, monitor bid activity, and review risk-analysis findings.",
    color: "text-gem-emerald",
    bg: "bg-gem-emerald-soft",
    border: "border-emerald-200",
    actions: [
      { label: "Tender Explorer", to: "/tenders", icon: FileText,
        desc: "Browse and manage published tenders" },
      { label: "Risk Analysis",   to: "/risk",    icon: ShieldAlert,
        desc: "Review detection findings" },
      { label: "Bidder Network",  to: "/network", icon: Users,
        desc: "Explore co-participation graph" },
    ],
  },
  bidder: {
    title: "Bidder Dashboard",
    description:
      "Browse open tenders and prepare your bid submissions.",
    color: "text-blue-600",
    bg: "bg-blue-50",
    border: "border-blue-200",
    actions: [
      { label: "Tender Explorer", to: "/tenders", icon: FileText,
        desc: "Browse open tenders" },
    ],
  },
  reviewer: {
    title: "Reviewer Dashboard",
    description:
      "Analyse procurement patterns and review risk signals.",
    color: "text-purple-600",
    bg: "bg-purple-50",
    border: "border-purple-200",
    actions: [
      { label: "Risk Analysis",  to: "/risk",    icon: ShieldAlert,
        desc: "Review detection findings" },
      { label: "Bidder Network", to: "/network", icon: Users,
        desc: "Explore co-participation graph" },
      { label: "Overview",       to: "/",        icon: BarChart2,
        desc: "Platform summary metrics" },
    ],
  },
  admin: {
    title: "Admin Dashboard",
    description: "Full platform access.",
    color: "text-slate-700",
    bg: "bg-slate-100",
    border: "border-slate-200",
    actions: [
      { label: "Overview",        to: "/",        icon: BarChart2,  desc: "" },
      { label: "Tender Explorer", to: "/tenders", icon: FileText,   desc: "" },
      { label: "Risk Analysis",   to: "/risk",    icon: ShieldAlert,desc: "" },
      { label: "Bidder Network",  to: "/network", icon: Users,      desc: "" },
    ],
  },
};

export function Dashboard() {
  const { user } = useAuth();
  const role = user?.role ?? "official";
  const cfg = ROLE_CONFIG[role as keyof typeof ROLE_CONFIG] ?? ROLE_CONFIG.official;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className={`p-4 rounded-xl border ${cfg.bg} ${cfg.border}`}>
        <p className={`text-xs font-semibold uppercase tracking-wide mb-1 ${cfg.color}`}>
          {role}
        </p>
        <h2 className="text-base font-semibold text-gem-text">{cfg.title}</h2>
        <p className="text-sm text-gem-muted mt-1">{cfg.description}</p>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {cfg.actions.map(({ label, to, icon: Icon, desc }) => (
          <Link
            key={to}
            to={to}
            className="card hover:shadow-elevated hover:border-emerald-200 transition-all flex items-start gap-3"
          >
            <div className="p-2 rounded-lg bg-gem-emerald-soft border border-emerald-200 shrink-0">
              <Icon size={16} className="text-gem-emerald" />
            </div>
            <div>
              <p className="text-sm font-semibold text-gem-text">{label}</p>
              {desc && <p className="text-xs text-gem-muted mt-0.5">{desc}</p>}
            </div>
          </Link>
        ))}
      </div>

      {/* Step 3 placeholder */}
      <div className="card border-dashed text-center py-8 text-gem-muted text-sm">
        Contract publishing, bid submission and award workflows — coming in Step 3.
      </div>
    </div>
  );
}
