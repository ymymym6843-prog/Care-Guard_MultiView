import { Wifi, WifiOff, Bell, LogOut, Clock, Sun, Moon } from "lucide-react";
import { Logo } from "@/components/ui/Logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMonitoringStore } from "@/store/monitoring";
import { logout } from "@/lib/auth";
import { useEffect, useState } from "react";
import { useTheme } from "@/hooks/useTheme";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useTranslation } from "react-i18next";

interface HeaderProps {
  onLogout: () => void;
}

export function Header({ onLogout }: HeaderProps) {
  const { connectionStatus, alertCount, clearAlerts, addEventLog, wsSendAcknowledge } = useMonitoringStore();
  const [currentTime, setCurrentTime] = useState(new Date());
  const { theme, toggleTheme } = useTheme();
  const { t, i18n } = useTranslation();

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const isConnected = connectionStatus === "connected";

  const handleLogout = async () => {
    await logout();
    onLogout();
  };

  const handleAcknowledge = () => {
    if (alertCount > 0) {
      wsSendAcknowledge?.();
      addEventLog("safe", t("header.acknowledged", "확인"), t("header.acknowledgeMessage", "의료진이 낙상 알림을 확인했습니다."));
      clearAlerts();
    }
  };

  return (
    <header role="banner" aria-label={t("header.mainHeader", "메인 헤더")} className="h-16 bg-card border-b border-border px-6 flex items-center justify-between shrink-0">
      {/* 좌측: 로고 */}
      <Logo size="sm" orientation="horizontal" />

      {/* 우측: 상태 표시 */}
      <div className="flex items-center gap-4">
        {/* 연결 상태 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="flex items-center gap-2">
              {isConnected ? (
                <Wifi className="h-4 w-4 text-safe" />
              ) : (
                <WifiOff className="h-4 w-4 text-danger animate-danger-pulse" />
              )}
              <Badge
                variant={isConnected ? "default" : "destructive"}
                className={
                  isConnected
                    ? "bg-safe/20 text-safe border-safe/30 hover:bg-safe/30"
                    : ""
                }
              >
                {isConnected ? t("header.connected", "연결됨") : t("header.disconnected", "연결 끊김")}
              </Badge>
            </div>
          </TooltipTrigger>
          <TooltipContent>
            <p>
              {isConnected
                ? t("header.serverConnected", "백엔드 서버 정상 연결")
                : t("header.serverDisconnected", "백엔드 서버 연결 실패 - 재연결 시도 중")}
            </p>
          </TooltipContent>
        </Tooltip>

        {/* 시간 */}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Clock className="h-4 w-4" />
          <time className="font-mono tabular-nums">
            {currentTime.toLocaleTimeString(i18n.language === "ko" ? "ko-KR" : "en-US", { hour12: false })}
          </time>
        </div>

        {/* 언어 전환 */}
        <LanguageSwitcher />

        {/* 테마 토글 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={theme === "dark" ? t("header.switchToLight", "라이트 모드로 전환") : t("header.switchToDark", "다크 모드로 전환")}
              onClick={toggleTheme}
            >
              {theme === "dark" ? (
                <Sun className="h-5 w-5" />
              ) : (
                <Moon className="h-5 w-5" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{theme === "dark" ? t("header.lightMode", "라이트 모드") : t("header.darkMode", "다크 모드")}</p>
          </TooltipContent>
        </Tooltip>

        {/* 알림 (클릭 시 즉시 acknowledge) */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="relative"
              aria-label={alertCount > 0 ? t("header.unreadAlerts", { count: alertCount, defaultValue: `미확인 알림 ${alertCount}건` }) : t("header.noAlerts", "알림 없음")}
              onClick={handleAcknowledge}
            >
              <Bell className="h-5 w-5" />
              {alertCount > 0 && (
                <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-danger text-danger-foreground text-xs flex items-center justify-center font-bold animate-danger-pulse">
                  {alertCount}
                </span>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>
              {alertCount > 0
                ? t("header.clickToAcknowledge", "클릭하여 알림 확인 (비프음 중지)")
                : t("header.noAlerts", "알림 없음")}
            </p>
          </TooltipContent>
        </Tooltip>

        {/* 로그아웃 */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("auth.logout", "로그아웃")}
              onClick={handleLogout}
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>{t("auth.logout", "로그아웃")}</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
