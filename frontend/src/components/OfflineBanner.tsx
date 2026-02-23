import { useState, useEffect, useRef } from "react";
import { WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";

const HEALTH_CHECK_INTERVAL = 5000; // 5초마다 체크
const HEALTH_CHECK_TIMEOUT = 3000; // 3초 타임아웃

export function OfflineBanner() {
  const { t } = useTranslation();
  const [isDisconnected, setIsDisconnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT);

        const response = await fetch("/health", {
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        setIsDisconnected(!response.ok);
      } catch {
        setIsDisconnected(true);
      }
    };

    // 초기 체크
    checkBackendHealth();

    // 주기적 체크
    intervalRef.current = setInterval(checkBackendHealth, HEALTH_CHECK_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  if (!isDisconnected) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-destructive text-destructive-foreground px-4 py-2 text-center text-sm font-medium flex items-center justify-center gap-2">
      <WifiOff className="h-4 w-4" />
      {t("common.serverDisconnected", t("common.offline"))}
    </div>
  );
}
