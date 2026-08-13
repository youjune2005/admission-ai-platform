import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import InquiryPage from "./pages/Inquiry";
import InquiryDraft from "./pages/InquiryDraft";
import DocumentCreate from "./pages/DocumentCreate";
import DocumentWizard from "./pages/DocumentWizard";
import BudgetWizard from "./pages/BudgetWizard";
import OutreachPlanWizard from "./pages/OutreachPlanWizard";
import Archive from "./pages/Archive";
import Regulations from "./pages/Regulations";
import SettingsPage from "./pages/SettingsPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="inquiry" element={<InquiryPage />} />
          <Route path="inquiry/:id" element={<InquiryDraft />} />
          <Route path="documents/create" element={<DocumentCreate />} />
          <Route path="documents/create/wizard" element={<DocumentWizard />} />
          <Route path="documents/create/budget" element={<BudgetWizard />} />
          <Route
            path="documents/create/visit"
            element={<OutreachPlanWizard kind="visit" />}
          />
          <Route
            path="documents/create/fair"
            element={<OutreachPlanWizard kind="fair" />}
          />
          <Route path="archive" element={<Archive />} />
          <Route path="regulations" element={<Regulations />} />
          <Route path="settings" element={<SettingsPage />} />

          {/* 이전 경로 호환 */}
          <Route path="chat" element={<Navigate to="/inquiry" replace />} />
          <Route path="workflow" element={<Navigate to="/documents/create" replace />} />
          <Route path="documents" element={<Navigate to="/archive" replace />} />
          <Route path="analytics" element={<Navigate to="/regulations" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
