/**
 * 알림 확인(Acknowledge) 훅
 */

import { useCallback } from "react";
import { useMonitoringStore } from "@/store/monitoring";

export function useAcknowledge(sendWsAcknowledge?: (personId?: string) => void) {
  const { clearAlerts, addEventLog } = useMonitoringStore();

  const acknowledge = useCallback(
    (personId?: string) => {
      // WebSocket으로 서버에 acknowledge 전송
      sendWsAcknowledge?.(personId);

      // 로컬 상태 업데이트
      addEventLog("safe", "확인", "의료진이 낙상 알림을 확인했습니다.");
      clearAlerts();
    },
    [sendWsAcknowledge, clearAlerts, addEventLog],
  );

  return { acknowledge };
}
