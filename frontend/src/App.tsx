import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ClipboardList } from "lucide-react";
import { AuthProvider } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { TenderExplorer } from "./pages/TenderExplorer";
import { RiskAnalysis } from "./pages/RiskAnalysis";
import { BidderNetwork } from "./pages/BidderNetwork";
import { Dashboard } from "./pages/Dashboard";
import { About } from "./pages/About";
import { ComingSoon } from "./pages/ComingSoon";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public login — outside AppShell */}
          <Route path="/login" element={<Login />} />

          {/* Protected application shell */}
          <Route
            element={
              <ProtectedRoute>
                <AppShell />
              </ProtectedRoute>
            }
          >
            <Route index element={<Overview />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/tenders" element={<TenderExplorer />} />
            <Route
              path="/risk"
              element={
                <ProtectedRoute allowedRoles={["official", "reviewer", "admin"]}>
                  <RiskAnalysis />
                </ProtectedRoute>
              }
            />
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
    </AuthProvider>
  );
}
