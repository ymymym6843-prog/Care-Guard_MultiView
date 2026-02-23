import { useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { useTranslation } from "react-i18next";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { DangerAlertDialog } from "../Alerts/DangerAlertDialog";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAlertSound } from "@/hooks/useAlertSound";
import { useAcknowledge } from "@/hooks/useAcknowledge";
import { useRooms } from "@/hooks/useRooms";

interface MainLayoutProps {
  onLogout: () => void;
  userRole?: string;
}

export function MainLayout({ onLogout, userRole }: MainLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem("sidebarCollapsed");
    return saved === "true";
  });
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();

  const { sendAcknowledge } = useWebSocket();
  useAlertSound();
  useRooms();
  const { acknowledge } = useAcknowledge(sendAcknowledge);

  const handleLogout = () => {
    onLogout();
    navigate("/login");
  };

  const currentPath = location.pathname.substring(1) || "dashboard";

  return (
    <TooltipProvider delayDuration={300}>
      <div className="h-screen flex flex-col overflow-hidden bg-background">
        <DangerAlertDialog onAcknowledge={acknowledge} />

        {/* Skip to main content (접근성) */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:bg-primary focus:text-primary-foreground focus:px-4 focus:py-2 focus:rounded-md"
        >
          {t("views.skipToContent", "본문으로 건너뛰기")}
        </a>

        <Header onLogout={handleLogout} />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar
            collapsed={sidebarCollapsed}
            onToggle={() => {
              const next = !sidebarCollapsed;
              setSidebarCollapsed(next);
              localStorage.setItem("sidebarCollapsed", String(next));
            }}
            activePath={currentPath}
            userRole={userRole}
          />
          <main id="main-content" className="flex-1 overflow-auto p-6" role="main">
            <Outlet />
          </main>
        </div>
      </div>
      <Toaster position="top-right" richColors />
    </TooltipProvider>
  );
}
