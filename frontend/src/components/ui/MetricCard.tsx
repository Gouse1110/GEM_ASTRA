import { cn } from "../../lib/cn";
import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  sub?: string;
  accent?: "emerald" | "amber" | "red" | "slate";
  empty?: boolean;
}

const accentMap: Record<string, string> = {
  emerald: "text-gem-emerald bg-gem-emerald-soft border-emerald-200",
  amber:   "text-amber-600 bg-amber-50 border-amber-200",
  red:     "text-red-600 bg-red-50 border-red-200",
  slate:   "text-gem-muted bg-slate-100 border-slate-200",
};

export function MetricCard({
  label,
  value,
  icon: Icon,
  sub,
  accent = "slate",
  empty = false,
}: MetricCardProps) {
  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium text-gem-muted uppercase tracking-wider">
          {label}
        </span>
        {Icon && (
          <span className={cn("p-1.5 rounded-lg border", accentMap[accent])}>
            <Icon size={14} />
          </span>
        )}
      </div>
      <div>
        {empty ? (
          <span className="text-2xl font-semibold text-gem-subtle">—</span>
        ) : (
          <span className="text-2xl font-semibold text-gem-text">{value}</span>
        )}
        {sub && <p className="mt-1 text-xs text-gem-muted">{sub}</p>}
      </div>
    </div>
  );
}
