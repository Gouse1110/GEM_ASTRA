import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  FileSearch,
  ShieldAlert,
  Network,
  ClipboardList,
  Info,
} from "lucide-react";
import { cn } from "../../lib/cn";
import { StatusBadge } from "../ui/StatusBadge";

const nav = [
  { to: "/",        label: "Overview",              icon: LayoutDashboard, status: null      },
  { to: "/tenders", label: "Tender Explorer",       icon: FileSearch,      status: null      },
  { to: "/risk",    label: "Risk Analysis",         icon: ShieldAlert,     status: null      },
  { to: "/network", label: "Bidder Network",        icon: Network,         status: null      },
  { to: "/reports", label: "Investigation Reports", icon: ClipboardList,   status: "planned" },
];

export function Sidebar() {
  return (
    <aside className="flex flex-col w-60 shrink-0 bg-gem-card border-r border-gem-border min-h-screen shadow-sidebar">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-gem-border">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gem-emerald-soft border border-emerald-200">
          <ShieldAlert size={16} className="text-gem-emerald" />
        </div>
        <div>
          <div className="text-sm font-semibold text-gem-text leading-tight">GeM Astra</div>
          <div className="text-[10px] text-gem-subtle uppercase tracking-widest leading-tight mt-0.5">
            Procurement Intelligence
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="px-3 mb-2 text-[10px] font-semibold text-gem-subtle uppercase tracking-widest">
          Modules
        </p>
        {nav.map(({ to, label, icon: Icon, status }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) => cn("nav-item", isActive && "active")}
          >
            <Icon size={15} className="shrink-0" />
            <span className="flex-1 truncate">{label}</span>
            {status === "planned" && (
              <StatusBadge label="Planned" variant="planned" />
            )}
          </NavLink>
        ))}
      </nav>

      {/* About + version */}
      <div className="px-3 pb-4 border-t border-gem-border pt-3">
        <NavLink
          to="/about"
          className={({ isActive }) => cn("nav-item", isActive && "active")}
        >
          <Info size={15} className="shrink-0" />
          <span>About</span>
        </NavLink>
        <p className="px-3 mt-3 text-[10px] text-gem-subtle">
          GeM Astra v0.1 · Prototype
        </p>
      </div>
    </aside>
  );
}
