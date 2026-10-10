import { ShieldAlert } from "lucide-react";
import { EmptyState } from "../components/ui/EmptyState";

export function RiskAnalysis() {
  return (
    <div className="max-w-5xl mx-auto">
      <div className="card">
        <EmptyState
          icon={ShieldAlert}
          title="Risk Analysis"
          description="Detection engine findings, review-priority scores, and evidence detail. This module is being migrated from Streamlit — API integration coming in the next step."
        />
      </div>
    </div>
  );
}
