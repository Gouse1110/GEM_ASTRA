import { cn } from "../../lib/cn";

type Variant = "planned" | "active" | "warning" | "neutral";

const variants: Record<Variant, string> = {
  active:  "bg-gem-emerald-soft text-gem-emerald-text border border-emerald-200",
  warning: "bg-amber-50 text-amber-700 border border-amber-200",
  planned: "bg-slate-100 text-slate-500 border border-slate-200",
  neutral: "bg-slate-50 text-gem-muted border border-gem-border",
};

interface StatusBadgeProps {
  label: string;
  variant?: Variant;
  className?: string;
}

export function StatusBadge({ label, variant = "neutral", className }: StatusBadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
      variants[variant],
      className,
    )}>
      {label}
    </span>
  );
}
