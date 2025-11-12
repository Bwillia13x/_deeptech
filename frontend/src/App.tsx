import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "./components/theme/theme-provider";
import { AppToaster } from "./components/toaster";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Signals from "./pages/Signals";
import Snapshots from "./pages/Snapshots";
import SnapshotDetail from "./pages/SnapshotDetail";
import SignalForm from "./pages/SignalForm";
import Settings from "./pages/Settings";
import Discoveries from "./pages/Discoveries";
import AnalyticsDashboard from "./pages/AnalyticsDashboard";
import NotFound from "./pages/NotFound";
import Onboarding, { useOnboarding } from "./components/Onboarding";

export default function App() {
  const { showOnboarding, handleComplete, handleSkip } = useOnboarding();

  return (
    <ThemeProvider defaultTheme="system" storageKey="theme">
      <AppLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/analytics" element={<AnalyticsDashboard />} />
          <Route path="/discoveries" element={<Discoveries />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/signals/new" element={<SignalForm />} />
          <Route path="/signals/:id/edit" element={<SignalForm />} />
          <Route path="/snapshots" element={<Snapshots />} />
          <Route path="/snapshots/:id" element={<SnapshotDetail />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AppLayout>
      <AppToaster />
      {showOnboarding && <Onboarding onComplete={handleComplete} onSkip={handleSkip} />}
    </ThemeProvider>
  );
}
