import { useEffect, useState, useCallback, useRef } from "react";
import {
  Search, Upload, ExternalLink, ChevronLeft, ChevronRight,
  FileSearch, AlertCircle, CheckCircle2, X,
} from "lucide-react";
import {
  fetchTenders, fetchFilterOptions, fetchTenderById, importTendersCsv,
  type TenderRecord, type TenderListResponse, type FilterOptions, type ImportResult,
} from "../lib/api";
import { cn } from "../lib/cn";

// --------------------------------------------------------------------------
// Constants
// --------------------------------------------------------------------------

const PAGE_SIZE = 25;

const SOURCE_LABELS: Record<string, { label: string; cls: string }> = {
  real_public_data: { label: "Verified public", cls: "badge-teal"  },
  synthetic:        { label: "Synthetic",        cls: "badge-amber" },
  synthetic_demo:   { label: "Synthetic demo",   cls: "badge-amber" },
  unknown:          { label: "Unknown",          cls: "badge-slate" },
};

function SourceBadge({ src }: { src: string }) {
  const s = SOURCE_LABELS[src] ?? { label: src, cls: "badge-slate" };
  return <span className={s.cls}>{s.label}</span>;
}

function Dash() {
  return <span className="text-gem-subtle">—</span>;
}

function val(v: string | null | undefined) {
  return v ? v : <Dash />;
}

// --------------------------------------------------------------------------
// Spinner
// --------------------------------------------------------------------------

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="w-6 h-6 border-2 border-gem-emerald border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

// --------------------------------------------------------------------------
// Error banner
// --------------------------------------------------------------------------

function ErrorBanner({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
      <AlertCircle size={15} className="shrink-0 mt-0.5 text-red-500" />
      <span className="flex-1">{message}</span>
      <button onClick={onClose} className="text-red-400 hover:text-red-600" aria-label="Dismiss">
        <X size={14} />
      </button>
    </div>
  );
}

// --------------------------------------------------------------------------
// Import result banner
// --------------------------------------------------------------------------

function ImportResultBanner({ result, onClose }: { result: ImportResult; onClose: () => void }) {
  return (
    <div className={cn(
      "p-3 rounded-lg border text-sm",
      result.inserted > 0
        ? "bg-gem-emerald-soft border-emerald-200 text-gem-emerald-text"
        : "bg-amber-50 border-amber-200 text-amber-700",
    )}>
      <div className="flex items-start gap-2">
        <CheckCircle2 size={15} className="shrink-0 mt-0.5" />
        <div className="flex-1">
          <span className="font-medium">Import complete — </span>
          {result.inserted} inserted · {result.skipped_duplicate} duplicate(s) skipped
          · {result.rejected} rejected
          {result.errors.length > 0 && (
            <ul className="mt-1 text-xs space-y-0.5 text-amber-600">
              {result.errors.slice(0, 5).map((e, i) => <li key={i}>• {e}</li>)}
              {result.errors.length > 5 && (
                <li>… and {result.errors.length - 5} more</li>
              )}
            </ul>
          )}
        </div>
        <button onClick={onClose} aria-label="Dismiss"><X size={14} /></button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Detail drawer
// --------------------------------------------------------------------------

function DetailDrawer({ tender, onClose }: { tender: TenderRecord; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="relative z-50 w-full max-w-md bg-white border-l border-gem-border flex flex-col overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gem-border">
          <h2 className="text-sm font-semibold text-gem-text truncate pr-4">
            {tender.item_name ?? tender.tender_id}
          </h2>
          <button
            onClick={onClose}
            className="text-gem-muted hover:text-gem-text"
            aria-label="Close detail panel"
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-5 text-sm">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            {(
              [
                ["Tender ID",   tender.tender_id],
                ["Department",  tender.department],
                ["Status",      tender.status],
                ["Quantity",    tender.quantity?.toString()],
                ["Start date",  tender.start_date],
                ["End date",    tender.end_date],
                ["Source doc",  tender.source_document],
                ["Imported at", tender.created_at],
              ] as [string, string | null | undefined][]
            ).map(([label, value]) => (
              <div key={label}>
                <p className="text-xs text-gem-muted mb-0.5">{label}</p>
                <p className="text-gem-text break-words">{val(value)}</p>
              </div>
            ))}
          </div>

          <div>
            <p className="text-xs text-gem-muted mb-1">Source type</p>
            <SourceBadge src={tender.source_type} />
          </div>

          {tender.official_url && (
            <a
              href={tender.official_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1.5 text-xs text-gem-emerald hover:text-gem-emerald-hover transition-colors"
            >
              Official source <ExternalLink size={11} />
            </a>
          )}
        </div>
      </aside>
    </div>
  );
}

// --------------------------------------------------------------------------
// Import panel
// --------------------------------------------------------------------------

function ImportPanel({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [override, setOverride] = useState("use_csv");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const ovr = override === "use_csv" ? undefined : override;
      const res = await importTendersCsv(file, ovr);
      setResult(res);
      if (res.inserted > 0) onImported();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-gem-muted">
        Upload a CSV with tender records. Only{" "}
        <code className="text-gem-emerald text-xs bg-gem-emerald-soft px-1 rounded">tender_id</code> is required.
        All other columns are optional.
      </p>

      <details className="text-xs text-gem-muted">
        <summary className="cursor-pointer hover:text-gem-text mb-1">
          Expected schema
        </summary>
        <code className="block mt-1 p-2 rounded bg-slate-50 border border-gem-border text-gem-muted leading-relaxed">
          tender_id, item_name, department, start_date, end_date,<br />
          status, quantity, official_url, source_type, source_document
        </code>
        <p className="mt-1">
          Source type values:{" "}
          <code>real_public_data</code> · <code>synthetic</code> · <code>unknown</code>
        </p>
      </details>

      {/* Drop zone */}
      <div
        className={cn(
          "border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors",
          file
            ? "border-gem-emerald bg-gem-emerald-soft"
            : "border-gem-border hover:border-emerald-300",
        )}
        onClick={() => inputRef.current?.click()}
        role="button"
        aria-label="Select CSV file"
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={e => setFile(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <p className="text-sm text-gem-emerald font-medium">{file.name}</p>
        ) : (
          <>
            <Upload size={20} className="mx-auto mb-2 text-gem-muted" />
            <p className="text-sm text-gem-muted">Click to select a CSV file</p>
          </>
        )}
      </div>

      {/* Source type override */}
      <div>
        <label htmlFor="source-override" className="block text-xs text-gem-muted mb-1">
          Confirm source type for this file
        </label>
        <select
          id="source-override"
          value={override}
          onChange={e => setOverride(e.target.value)}
          className="select"
        >
          <option value="use_csv">Use value from CSV column</option>
          <option value="real_public_data">real_public_data — verified official records only</option>
          <option value="synthetic">synthetic — demo / test data</option>
          <option value="unknown">unknown — unverified source</option>
        </select>
        <p className="mt-1 text-xs text-gem-subtle">
          Never classify synthetic data as real_public_data.
        </p>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
      {result && (
        <ImportResultBanner result={result} onClose={() => setResult(null)} />
      )}

      <button
        disabled={!file || loading}
        onClick={handleImport}
        className="btn-primary w-full"
      >
        {loading ? "Importing…" : "Import into database"}
      </button>
    </div>
  );
}

// --------------------------------------------------------------------------
// Filter select helper
// --------------------------------------------------------------------------

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <div className="flex flex-col gap-1 min-w-36">
      <label htmlFor={id} className="text-xs text-gem-muted">{label}</label>
      <select
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="select"
      >
        <option value="">All</option>
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

// --------------------------------------------------------------------------
// Pagination bar
// --------------------------------------------------------------------------

function Pagination({
  page,
  pages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between text-xs text-gem-muted pt-3 border-t border-gem-border">
      <span>{total === 0 ? "No results" : `${from}–${to} of ${total}`}</span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Previous page"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="px-2">{page} / {pages}</span>
        <button
          onClick={() => onPage(page + 1)}
          disabled={page >= pages}
          className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
          aria-label="Next page"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Main page
// --------------------------------------------------------------------------

export function TenderExplorer() {
  const [tab, setTab] = useState<"browse" | "import">("browse");

  // Data
  const [data, setData] = useState<TenderListResponse | null>(null);
  const [filters, setFilters] = useState<FilterOptions | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [search, setSearch] = useState("");
  const [dept, setDept] = useState("");
  const [status, setStatus] = useState("");
  const [srcType, setSrcType] = useState("");

  // Detail drawer
  const [selected, setSelected] = useState<TenderRecord | null>(null);

  const load = useCallback(
    async (p = 1) => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetchTenders({
          search: search || undefined,
          department: dept || undefined,
          status: status || undefined,
          source_type: srcType || undefined,
          page: p,
          page_size: PAGE_SIZE,
        });
        setData(res);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to load tenders");
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [search, dept, status, srcType],
  );

  const loadFilters = useCallback(async () => {
    try {
      setFilters(await fetchFilterOptions());
    } catch {
      /* non-fatal — filters just stay empty */
    }
  }, []);

  // Initial load
  useEffect(() => {
    load(1);
    loadFilters();
  }, [load, loadFilters]);

  const handleRowClick = async (t: TenderRecord) => {
    try {
      const full = await fetchTenderById(t.tender_id);
      setSelected(full);
    } catch {
      setSelected(t); // fall back to row data
    }
  };

  const handleImported = () => {
    load(1);
    loadFilters();
    setTab("browse");
  };

  return (
    <div className="max-w-6xl mx-auto space-y-5">

      {/* Tab switcher */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-lg w-fit border border-gem-border">
        {(["browse", "import"] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-1.5 rounded-md text-sm font-medium transition-colors",
              tab === t ? "bg-white text-gem-text shadow-card" : "text-gem-muted hover:text-gem-text",
            )}
          >
            {t === "browse" ? "📋 Browse" : "⬆ Import"}
          </button>
        ))}
      </div>

      {/* Import tab */}
      {tab === "import" ? (
        <div className="card max-w-xl">
          <h3 className="text-sm font-semibold text-gem-text mb-4">Import Tenders</h3>
          <ImportPanel onImported={handleImported} />
        </div>
      ) : (
        <>
          {/* Search + filters */}
          <div className="card space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              {/* Search */}
              <div className="flex flex-col gap-1 flex-1 min-w-48">
                <label htmlFor="tender-search" className="text-xs text-gem-muted">Search</label>
                <div className="relative">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gem-subtle" />
                  <input
                    id="tender-search"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && load(1)}
                    placeholder="Tender ID or item name…"
                    className="input pl-8"
                  />
                </div>
              </div>

              {/* Department filter */}
              <FilterSelect
                id="filter-dept"
                label="Department"
                value={dept}
                onChange={setDept}
                options={filters?.departments ?? []}
              />

              {/* Status filter */}
              <FilterSelect
                id="filter-status"
                label="Status"
                value={status}
                onChange={setStatus}
                options={filters?.statuses ?? []}
              />

              {/* Source type filter */}
              <FilterSelect
                id="filter-source"
                label="Source type"
                value={srcType}
                onChange={setSrcType}
                options={filters?.source_types ?? []}
              />

              <button
                onClick={() => load(1)}
                className="btn-primary self-end"
              >
                Search
              </button>
            </div>

            {error && (
              <ErrorBanner message={error} onClose={() => setError(null)} />
            )}
          </div>

          {/* Results */}
          <div className="card">
            {loading ? (
              <Spinner />
            ) : data === null ? (
              <div className="flex flex-col items-center py-12 text-center">
                <FileSearch size={28} className="text-gem-muted mb-3" />
                <p className="text-sm text-gem-muted">
                  Could not load tenders. Check that the API server is running.
                </p>
              </div>
            ) : data.total === 0 ? (
              <div className="flex flex-col items-center py-12 text-center">
                <FileSearch size={28} className="text-gem-muted mb-3" />
                <p className="text-sm text-gem-text mb-1">No tender records found</p>
                <p className="text-xs text-gem-muted max-w-xs">
                  {search || dept || status || srcType
                    ? "No results match the current filters. Try adjusting your search."
                    : "The database is empty. Use the Import tab to load tender records."}
                </p>
              </div>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gem-border text-left">
                        {["Tender ID","Item","Department","Status","Start","End","Source"].map(h => (
                          <th key={h} className="pb-2 pr-4 text-xs font-medium text-gem-muted uppercase tracking-wide whitespace-nowrap">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map(t => (
                        <tr
                          key={t.tender_id}
                          onClick={() => handleRowClick(t)}
                          className="border-b border-gem-border hover:bg-slate-50 cursor-pointer transition-colors"
                        >
                          <td className="py-2.5 pr-4 font-mono text-xs text-gem-emerald whitespace-nowrap">{t.tender_id}</td>
                          <td className="py-2.5 pr-4 text-gem-text max-w-48 truncate">{t.item_name ?? <Dash />}</td>
                          <td className="py-2.5 pr-4 text-gem-muted whitespace-nowrap">{t.department ?? <Dash />}</td>
                          <td className="py-2.5 pr-4 text-gem-muted whitespace-nowrap">{t.status ?? <Dash />}</td>
                          <td className="py-2.5 pr-4 text-gem-subtle text-xs whitespace-nowrap">{t.start_date ?? <Dash />}</td>
                          <td className="py-2.5 pr-4 text-gem-subtle text-xs whitespace-nowrap">{t.end_date ?? <Dash />}</td>
                          <td className="py-2.5 pr-4 whitespace-nowrap"><SourceBadge src={t.source_type} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <Pagination
                  page={data.page}
                  pages={data.pages}
                  total={data.total}
                  pageSize={PAGE_SIZE}
                  onPage={p => load(p)}
                />
              </>
            )}
          </div>
        </>
      )}

      {/* Detail drawer */}
      {selected && (
        <DetailDrawer tender={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
