import { ShieldAlert } from "lucide-react";

export function About() {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-gem-text">Purpose</h2>
        <p className="text-sm text-gem-muted leading-relaxed">
          GeM Astra is a procurement analytics platform that helps authorised reviewers detect
          potentially suspicious bidding patterns in Government e-Marketplace (GeM) tenders.
          It applies statistical and graph-based signals — such as cover bidding, bid rotation,
          and price convergence — to surface tenders that may warrant closer human scrutiny.
        </p>
      </div>

      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-gem-text">What it is not</h2>
        <ul className="space-y-2 text-sm text-gem-muted">
          {[
            "GeM Astra is not a judicial or legal determination system.",
            "A risk flag is not evidence of collusion or fraud.",
            "The tool does not automatically blacklist suppliers or issue compliance decisions.",
            "All findings must be reviewed by qualified procurement officers or legal authorities.",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2">
              <ShieldAlert size={12} className="text-amber-500 mt-1 shrink-0" />
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-gem-text">Human review requirement</h2>
        <p className="text-sm text-gem-muted leading-relaxed">
          Every risk indicator produced by this tool is an analytical signal that requires
          expert human judgement before any conclusion is drawn or action taken.
          No automated output from GeM Astra should be used as the sole basis for
          regulatory, legal, or administrative decisions.
        </p>
      </div>

      <p className="text-xs text-gem-subtle text-center">
        GeM Astra v0.1 — Hackathon prototype. Not for production use without further validation.
      </p>
    </div>
  );
}
