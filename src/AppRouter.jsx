import React, { Suspense, useEffect } from "react";
import App from "./App.jsx";
import { PermissionGuideOverlay } from "./components/onboarding/PermissionGuideOverlay";
import BackgroundModelDownloadTray from "./components/onboarding/BackgroundModelDownloadTray.tsx";
import { useControlPanelWindowDrag } from "./hooks/useControlPanelWindowDrag";
import { useTheme } from "./hooks/useTheme";
import { isControlPanelWindow } from "./utils/windowContext.ts";

const ControlPanel = React.lazy(() => import("./components/ControlPanel.tsx"));

export default function AppRouter() {
  useTheme();
  const isControlPanel = isControlPanelWindow();
  useControlPanelWindowDrag(isControlPanel);

  useEffect(() => {
    // The local dictation app has no account or onboarding gate. Release the
    // global shortcut as soon as the renderer is ready.
    void window.electronAPI?.setOnboardingActive?.(false);
    if (isControlPanel) void window.electronAPI?.setOnboardingWindowMode?.("restore");
  }, [isControlPanel]);

  if (window.location.search.includes("permission-guide=true")) return <PermissionGuideOverlay />;
  if (!isControlPanel) return <App />;
  return (
    <Suspense fallback={<div className="p-6">Loading dictation…</div>}>
      <ControlPanel />
      <BackgroundModelDownloadTray />
    </Suspense>
  );
}
