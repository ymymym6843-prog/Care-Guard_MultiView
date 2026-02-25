import { useState, useEffect, useRef } from "react";
import { WifiOff } from "lucide-react";
import { useTranslation } from "react-i18next";

const HEALTH_CHECK_INTERVAL = 15000; // 15초마다 체크 (파이프라인 부하 고려)
const HEALTH_CHECK_TIMEOUT = 8000;  // 8초 타임아웃 (YOLO 처리 중 지연 허용)
const DISCONNECT_THRESHOLD = 3;     // 3회 연속 실패 시에만 배너 표시

export function OfflineBanner() {
  const { t } = useTranslation();
  const [isDisconnected, setIsDisconnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const failCountRef = useRef(0);

  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT);

        const response = await fetch("/health", {
          signal: controller.signal,
        });
        clearTimeout(timeoutId);

        if (response.ok) {
          failCountRef.current = 0;
          setIsDisconnected(false);
        } else {
          failCountRef.current += 1;
          if (failCountRef.current >= DISCONNECT_THRESHOLD) {
            setIsDisconnected(true);
          }
        }
      } catch {
        failCountRef.current += 1;
        if (failCountRef.current >= DISCONNECT_THRESHOLD) {
          setIsDisconnected(true);
        }
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
