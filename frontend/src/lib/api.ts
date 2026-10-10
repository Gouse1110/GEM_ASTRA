const BASE = "/api";

// --------------------------------------------------------------------------
// Types matching the backend Pydantic models exactly
// --------------------------------------------------------------------------

export interface TenderRecord {
  tender_id: string;
  item_name: string | null;
  department: string | null;
  start_date: string | null;
  end_date: string | null;
  status: string | null;
  quantity: number | null;
  official_url: string | null;
  source_type: string;
  source_document: string | null;
  created_at: string | null;
}

export interface TenderListResponse {
  items: TenderRecord[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface FilterOptions {
  departments: string[];
  statuses: string[];
  source_types: string[];
}

export interface ImportResult {
  inserted: number;
  skipped_duplicate: number;
  rejected: number;
  errors: string[];
}

export interface TenderListParams {
  search?: string;
  department?: string;
  status?: string;
  source_type?: string;
  page?: number;
  page_size?: number;
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// --------------------------------------------------------------------------
// Health
// --------------------------------------------------------------------------

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  return apiFetch("/health");
}

// --------------------------------------------------------------------------
// Tenders
// --------------------------------------------------------------------------

export async function fetchTenders(params: TenderListParams = {}): Promise<TenderListResponse> {
  const qs = new URLSearchParams();
  if (params.search)      qs.set("search", params.search);
  if (params.department)  qs.set("department", params.department);
  if (params.status)      qs.set("status", params.status);
  if (params.source_type) qs.set("source_type", params.source_type);
  if (params.page)        qs.set("page", String(params.page));
  if (params.page_size)   qs.set("page_size", String(params.page_size));
  const q = qs.toString();
  return apiFetch(`/tenders${q ? "?" + q : ""}`);
}

export async function fetchTenderCount(): Promise<number> {
  const res = await fetchTenders({ page: 1, page_size: 1 });
  return res.total;
}

// --------------------------------------------------------------------------
// Summary
// --------------------------------------------------------------------------

export interface SummaryData {
  tender_count: number;
  tender_source: string;
  bid_record_count: number | null;
  unique_bidder_count: number | null;
  bid_source: string;
  bid_source_label: string;
  active_findings_count: number | null;
  findings_source: string;
  findings_source_label: string;
}

export async function fetchSummary(): Promise<SummaryData> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000); // 8s timeout
  try {
    return await apiFetch("/summary", { signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchTenderById(tenderId: string): Promise<TenderRecord> {
  return apiFetch(`/tenders/${encodeURIComponent(tenderId)}`);
}

export async function fetchFilterOptions(): Promise<FilterOptions> {
  return apiFetch("/tenders/filters");
}

// --------------------------------------------------------------------------
// Bidder Network
// --------------------------------------------------------------------------

export interface BidderNode {
  bidder_id: string;
  tender_count: number;
  source_type: string;
}

export interface BidderEdge {
  bidder_a: string;
  bidder_b: string;
  shared_tender_count: number;
  shared_tender_ids: string[];
  source_type: string;
}

export interface NetworkData {
  nodes: BidderNode[];
  edges: BidderEdge[];
  source_label: string;
  disclaimer: string;
  total_bidders: number;
  total_edges: number;
}

export async function fetchNetwork(): Promise<NetworkData> {
  return apiFetch("/network");
}

// --------------------------------------------------------------------------
// Risk Analysis
// --------------------------------------------------------------------------

export interface RiskFinding {
  rule: string;
  rule_name: string;
  tender_ids: string[];
  bidder_ids: string[];
  evidence: Record<string, unknown>;
  threshold_or_criterion: string;
  explanation: string;
  source_type: string;
  data_limitations: string;
  insufficient_data: boolean;
}

export interface RiskSummary {
  score: number;
  score_band: string;
  score_explanation: string;
  total_bids_analysed: number;
  actionable_findings_count: number;
  rules_fired: string[];
  source_type: string;
  real_data_available: boolean;
  warnings: string[];
}

export interface RiskData {
  summary: RiskSummary;
  findings: RiskFinding[];
  source_label: string;
  disclaimer: string;
}

export async function fetchRiskAnalysis(): Promise<RiskData> {
  return apiFetch("/risk");
}

export async function importTendersCsv(
  file: File,
  sourceTypeOverride?: string,
): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file);
  const qs = sourceTypeOverride ? `?source_type_override=${encodeURIComponent(sourceTypeOverride)}` : "";
  return apiFetch(`/tenders/import${qs}`, { method: "POST", body: form });
}
