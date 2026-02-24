import { useState, useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { checkAuth, devAutoLogin } from "@/lib/auth";
import { LoginPage } from "@/components/LoginPage";
import { RegisterPage } from "@/components/RegisterPage";
import { MainLayout } from "@/components/layout/MainLayout";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ConsentDialog } from "@/components/ConsentDialog";
import { DashboardView } from "@/components/Dashboard/DashboardView";
import { SafeZoneEditor } from "@/components/Dashboard/SafeZoneEditor";
import { EventHistory } from "@/components/Events/EventHistory";
import { SettingsCard } from "@/components/Dashboard/SettingsCard";
import { StatsView } from "@/components/Stats/StatsView";
import { ReportView } from "@/components/Reports/ReportView";
import { UserManagement } from "@/components/UserManagement";
import { ModelManager } from "@/components/Dashboard/ModelManager";
import { FalseReportManager } from "@/components/Dashboard/FalseReportManager";
import { RoomManager } from "@/components/RoomManager";
import { AdminRoute } from "@/components/AdminRoute";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";
import { toast } from "sonner";
import { useMonitoringStore } from "@/store/monitoring";
import LogoShowcase from "@/pages/LogoShowcase";
import SentioLogoShowcase from "@/pages/SentioLogoShowcase";
import {
  AUTH_CHECK_TIMEOUT_MS,
  SETUP_CHECK_TIMEOUT_MS,
  MAX_SETUP_CHECK_RETRIES,
  RETRY_DELAY_BASE_MS,
  RETRY_DELAY_MAX_MS,
} from "@/lib/constants";

interface User {
  username: string;
  role: string;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();

  const authenticated = !!user;

  // 서버에 쿠키 기반 인증 상태 확인
  useEffect(() => {
    if (authenticated) return;
    let cancelled = false;

    async function init() {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), AUTH_CHECK_TIMEOUT_MS);

      try {
        const userData = await checkAuth();
        clearTimeout(timeoutId);

        if (!cancelled) {
          if (userData) {
            setUser(userData);
            setAuthChecked(true);
            if (location.pathname === "/login" || location.pathname === "/") {
              navigate("/dashboard");
            }
            return;
          }
          setAuthChecked(true);
        }
      } catch (e) {
        console.error("Auth init failed:", e);
        if (!cancelled) {
          setAuthChecked(true);
          toast.error("인증 확인 실패. 네트워크 연결을 확인해주세요.");
        }
      }
    }

    init();
    return () => { cancelled = true; };
  }, [authenticated]);

  // 인증되지 않은 경우 setup 상태 확인 + 개발 모드 자동 로그인
  useEffect(() => {
    if (authenticated || !authChecked) return;
    let cancelled = false;
    let attempt = 0;

    async function checkSetup() {
      while (!cancelled && attempt < MAX_SETUP_CHECK_RETRIES) {
        attempt++;
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), SETUP_CHECK_TIMEOUT_MS);
          const res = await fetch("/api/auth/check-setup", {
            signal: controller.signal,
          });
          clearTimeout(timeout);
          const data = await res.json();
          if (cancelled) return;

          // 개발 모드 자동 로그인 시도
          if (data.dev_auto_login) {
            const autoUser = await devAutoLogin();
            if (!cancelled && autoUser) {
              console.log(`[DEV] 자동 로그인: ${autoUser.username} (${autoUser.role})`);
              setUser(autoUser);
              navigate("/dashboard");
              return;
            }
          }

          if (!cancelled) setNeedsSetup(data.needs_setup);
          return;
        } catch (error) {
          // Exponential backoff
          const delay = Math.min(
            RETRY_DELAY_BASE_MS * Math.pow(2, attempt - 1),
            RETRY_DELAY_MAX_MS
          );
          await new Promise((r) => setTimeout(r, delay));
        }
      }
      if (!cancelled) {
        setNeedsSetup(false);
        if (attempt >= MAX_SETUP_CHECK_RETRIES) {
          toast.error("서버 연결에 실패했습니다. 나중에 다시 시도해주세요.");
        }
      }
    }

    checkSetup();
    return () => { cancelled = true; };
  }, [authenticated, authChecked]);

  // 데모 시연용 키보드 단축키 (Shift + F1~F4)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!e.shiftKey) return;

      const {
        setCurrentAlert,
        setCurrentFallType,
        addEventLog,
        clearAlerts,
        settings
      } = useMonitoringStore.getState();

      // F1: 주의 (Warning)
      if (e.key === "F1") {
        e.preventDefault();
        setCurrentAlert("warning");
        setCurrentFallType("pre_impact");
        toast.warning("⚠️ 주의: 거동이 불안정한 환자가 감지되었습니다.");
        addEventLog("warning", "pre_impact", i18n.t("dashboard.eventLog.demoAbnormal", "이상 행동 감지 (Demo)"), "person_demo");
      }
      // F2: 경고 (Warning - 지속)
      else if (e.key === "F2") {
        e.preventDefault();
        setCurrentAlert("warning");
        setCurrentFallType("long_lie");
        toast.warning("🔔 경고: 위험 상태가 지속되고 있습니다.");
        addEventLog("warning", "long_lie", i18n.t("dashboard.eventLog.demoDangerPersist", "위험 상태 지속 (Demo)"), "person_demo");
      }
      // F3: 위험 (Danger - 낙상)
      else if (e.key === "F3") {
        e.preventDefault();
        setCurrentAlert("danger");
        setCurrentFallType("front_fall");
        toast.error("🚨 위험: 낙상이 감지되었습니다! 응급 조치 요망");
        addEventLog("danger", "front_fall", i18n.t("dashboard.eventLog.demoFallOccurred", "낙상 사고 발생 (Demo)"), "person_demo");

        // TTS
        if (settings.ttsEnabled) {
          const msg = new SpeechSynthesisUtterance("위험. 낙상 사고가 감지되었습니다.");
          msg.lang = "ko-KR";
          window.speechSynthesis.speak(msg);
        }
      }
      // F4: 정상 복구
      else if (e.key === "F4") {
        e.preventDefault();
        clearAlerts();
        toast.success("✅ 상태가 정상으로 복구되었습니다.");
        addEventLog("safe", "recovery", i18n.t("dashboard.eventLog.demoRecovered", "상태 복구됨 (Demo)"), "person_demo");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // 초기 로딩
  if (!authChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <p className="text-muted-foreground text-sm">인증 확인 중...</p>
      </div>
    );
  }

  return (
    <>
      <OfflineBanner />
      <Routes>
        {/* Design Showcase Route */}
        <Route path="/design/logo" element={<LogoShowcase />} />
        <Route path="/design/sentio" element={<SentioLogoShowcase />} />

        <Route path="/login" element={
          authenticated ? <Navigate to="/dashboard" replace /> : <LoginPage onLoginSuccess={async () => {
            const userData = await checkAuth();
            if (userData) {
              setUser(userData);
              navigate("/dashboard");
            }
          }} />
        } />
        <Route path="/register" element={
          authenticated ? <Navigate to="/dashboard" replace /> : (
            needsSetup ? <RegisterPage onRegisterSuccess={async () => {
              setNeedsSetup(false);
              const userData = await checkAuth();
              if (userData) {
                setUser(userData);
                navigate("/dashboard");
              }
            }} /> : <Navigate to="/login" replace />
          )
        } />

        {/* Protected Routes */}
        {authenticated ? (
          <Route path="/" element={
            <>
              <MainLayout onLogout={() => setUser(null)} userRole={user?.role} />
              <ConsentDialog />
            </>
          }>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<DashboardView />} />
            <Route path="cameras" element={
              <div className="space-y-6">
                <h2 className="text-xl font-semibold">{t("views.cameraManagement", "카메라 관리")}</h2>
                <SafeZoneEditor showCameraTabs />
              </div>
            } />
            <Route path="alerts" element={<EventHistory mode="alerts" />} />
            <Route path="history" element={<EventHistory mode="history" />} />
            <Route path="stats" element={<StatsView />} />
            <Route path="reports" element={<ReportView />} />

            {/* Admin Only Routes */}
            <Route element={<AdminRoute userRole={user?.role} />}>
              <Route path="settings" element={
                <div className="space-y-6">
                  <h2 className="text-xl font-semibold">{t("nav.settings", "설정")}</h2>
                  <RoomManager />
                  <SettingsCard />
                  <ModelManager />
                  <FalseReportManager />
                  <UserManagement />
                </div>
              } />
            </Route>

          </Route>
        ) : (
          <Route path="*" element={<Navigate to={needsSetup ? "/register" : "/login"} replace />} />
        )}
      </Routes>
    </>
  );
}

export default App;
