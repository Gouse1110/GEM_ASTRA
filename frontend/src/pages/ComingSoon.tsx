import type { LucideIcon } from "lucide-react";
import { Construction } from "lucide-react";

interface ComingSoonProps {
  title: string;
  description: string;
  icon?: LucideIcon;
}

export function ComingSoon({ title, description, icon: Icon = Construction }: ComingSoonProps) {
  return (
    <div className="max-w-2xl mx-auto mt-12">
      <div className="card text-center py-16 px-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-slate-100 border border-gem-border mb-5">
          <Icon size={24} className="text-gem-muted" />
        </div>
        <h2 className="text-base font-semibold text-gem-text mb-2">{title}</h2>
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 mb-5">
          <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
          <span className="text-xs text-gem-muted font-medium">Planned feature</span>
        </div>
        <p className="text-sm text-gem-muted leading-relaxed max-w-sm mx-auto">{description}</p>
      </div>
    </div>
  );
}
