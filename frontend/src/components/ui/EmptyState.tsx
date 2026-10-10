import type { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-8 text-center">
      {Icon && (
        <div className="mb-4 p-4 rounded-full bg-slate-100 border border-gem-border">
          <Icon size={28} className="text-gem-muted" />
        </div>
      )}
      <h3 className="text-base font-semibold text-gem-text mb-2">{title}</h3>
      <p className="text-sm text-gem-muted max-w-sm leading-relaxed">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
