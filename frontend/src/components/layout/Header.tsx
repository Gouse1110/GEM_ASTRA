import { useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  FileSearch,
  ShieldAlert,
  Network,
  ClipboardList,
  Info,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

const PAGE_META: Record<string, { title: string; icon: LucideIcon; sub: string }> = {
  "/":        { title: "Overview",              icon: LayoutDashboard, sub: "Platform summary" },
  "/tenders": { title: "Tender Explorer",       icon: FileSearch,      sub: "Browse and import tender records" },
  "/risk":    { title: "Risk Analysis",         icon: ShieldAlert,     sub: "Detection findings and review priorities" },
  "/network": { title: "Bidder Network",        icon: Network,         sub: "Relationship graph explorer" },
  "/reports": { title: "Investigation Reports", icon: ClipboardList,   sub: "Document and export findings" },
  "/about":   { title: "About",                 icon: Info,            sub: "Purpose, limitations, and human-review requirement" },
};

export function Header({ actions }: { actions?: React.ReactNode }) {
  const { pathname } = useLocation();
  const meta = PAGE_META[pathname] ?? PAGE_META["/"];
  const Icon = meta.icon;

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-gem-border bg-gem-card sticky top-0 z-10 shadow-card">
      <div className="flex items-center gap-3">
        <Icon size={18} className="text-gem-emerald shrink-0" />
        <div>
          <h1 className="text-base font-semibold text-gem-text leading-tight">{meta.title}</h1>
          <p className="text-xs text-gem-muted leading-tight mt-0.5">{meta.sub}</p>
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
