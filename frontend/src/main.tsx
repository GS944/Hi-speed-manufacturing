import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "./index.css";
import { AuthProvider, useAuth } from "./lib/auth";
import { ToastProvider } from "./components/ui";
import Layout from "./components/Layout";
import Login, { Signup } from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Tracker from "./pages/Tracker";
import Orders from "./pages/Orders";
import Annexure from "./pages/Annexure";
import DataSheets from "./pages/DataSheets";
import TableView from "./pages/TableView";
import Insights from "./pages/Insights";
import SettingsPage from "./pages/Settings";

function Protected({ children }: { children: JSX.Element }) {
  const { username } = useAuth();
  const loc = useLocation();
  return username ? children : <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route element={<Protected><Layout /></Protected>}>
              <Route index element={<Dashboard />} />
              <Route path="track" element={<Tracker />} />
              <Route path="track/:orderNo" element={<Tracker />} />
              <Route path="orders" element={<Orders />} />
              <Route path="annexure" element={<Annexure />} />
              <Route path="annexure/:orderNo" element={<Annexure />} />
              <Route path="data" element={<DataSheets />} />
              <Route path="data/tables/:id" element={<TableView />} />
              <Route path="insights" element={<Insights />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
