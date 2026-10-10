import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { AppShell } from "./components/layout/AppShell";
import { Overview } from "./pages/Overview";
import { TenderExplorer } from "./pages/TenderExplorer";
import { RiskAnalysis } from "./pages/RiskAnalysis";
import { BidderNetwork } from "./pages/BidderNetwork";
import { About } from "./pages/About";
import { ComingSoon } from "./pages/ComingSoon";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Overview />} />
          <Route path="/tenders" element={<TenderExplorer />} />
          <Route path="/risk" element={<RiskAnalysis />} />
          <Route path="/network" element={<BidderNetwork />} />
          <Route
            path="/reports"
            element={
              <ComingSoon
                icon={ClipboardList}
                title="Investigation Reports"
                description="Document findings, attach evidence, and export structured reports for compliance teams. Planned for a future migration step."
              />
            }
          />
          <Route path="/about" element={<About />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
