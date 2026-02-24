/**
 * WebSocket 연결 훅
 *
 * 쿠키 기반 인증으로 자동 전송됩니다 (same-origin).
 * 지수 백오프 재연결, 하트비트, 메시지 파싱을 처리합니다.
 */

import { useEffect, useRef, useCallback } from "react";
import { useMonitoringStore, type AlertLevel, type PersonMetrics, type BBoxData, type PoseData } from "@/store/monitoring";
import i18n from "@/i18n";

export type WSMessageType =
  | "pose_data"
  | "alert_update"
  | "metrics_update"
  | "connection_status"
  | "ping";

export interface WSMessage {
  type: WSMessageType;
  data: Record<string, unknown>;
}

const WS_BASE_URL = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/monitoring`;
const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

function _fallTypeLabel(fallType: string): string {
  const t = i18n.t;
  switch (fallType) {
    case "front_fall": return t("dashboard.eventLog.fallTypeLabels.front_fall", "[전방]");
    case "back_fall": return t("dashboard.eventLog.fallTypeLabels.back_fall", "[후방]");
    case "side_fall": return t("dashboard.eventLog.fallTypeLabels.side_fall", "[측면]");
    case "pre_impact": return t("dashboard.eventLog.fallTypeLabels.pre_impact", "[충격전]");
    default: return "";
  }
}

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const mountedRef = useRef(true);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg: WSMessage = JSON.parse(event.data);

      switch (msg.type) {
        case "metrics_update": {
          const d = msg.data;
          const metricsCameraId = (d.camera_id as string) ?? "cam0";
          const cameraFps = (d.fps as number) ?? 0;

          useMonitoringStore.getState().setMetrics({
            personCount: (d.person_count as number) ?? 0,
            fps: cameraFps,
            fallConfidence: (d.fall_confidence as number) ?? 0,
            headY: (d.head_y as number) ?? 0,
            hipY: (d.hip_y as number) ?? 0,
            angle: (d.angle as number) ?? 0,
            walkingAidUsers: (d.walking_aid_users as number) ?? 0,
          });
          // 카메라별 FPS 개별 저장 (다중 카메라 집계용)
          useMonitoringStore.getState().setPerCameraFps(metricsCameraId, cameraFps);
          // 백엔드 카메라 상태 동기화
          if (d.is_camera_active !== undefined) {
            useMonitoringStore.getState().setCameraActive(d.is_camera_active as boolean);
          }
          const alertLevel = d.alert_level as string;
          if (alertLevel) {
            const store = useMonitoringStore.getState();
            // 카메라별 알림 수준 추적 → 전체 최고 수준 사용
            store.setPerCameraAlert(metricsCameraId, alertLevel as "safe" | "warning" | "danger");
            const alertRank = { safe: 0, warning: 1, danger: 2 } as Record<string, number>;
            const allAlerts = Object.values(store.perCameraAlert);
            // 방금 설정한 값도 포함
            allAlerts.push(alertLevel as AlertLevel);
            const globalAlert = (allAlerts.reduce((max, a) =>
              (alertRank[a] ?? 0) > (alertRank[max] ?? 0) ? a : max, "safe" as AlertLevel)) as "safe" | "warning" | "danger";
            // acknowledge 후 서버가 safe를 보내기 전까지 danger 재설정 방지
            if (globalAlert === "danger" && store.isAcknowledged) {
              // suppress — 서버 acknowledge 확인 대기
            } else {
              if (globalAlert !== "danger" && store.isAcknowledged) {
                store.setIsAcknowledged(false);
              }
              store.setCurrentAlert(globalAlert);
            }
          }
          const duration = d.alert_duration as number;
          if (duration !== undefined) {
            useMonitoringStore.getState().setAlertDuration(Math.round(duration));
          }
          // 다중 인원 데이터 파싱 — 카메라별 병합 (bboxes와 동일 패턴)
          if (Array.isArray(d.persons)) {
            const cameraId = (d.camera_id as string) ?? "cam0";
            const persons: PersonMetrics[] = (d.persons as Record<string, unknown>[]).map((p) => {
              const walkingAid = p.walking_aid as Record<string, unknown> | undefined;
              return {
                personId: (p.person_id as string) ?? "",
                fallConfidence: (p.fall_confidence as number) ?? 0,
                isFallen: (p.is_fallen as boolean) ?? false,
                headY: (p.head_y as number) ?? 0,
                hipY: (p.hip_y as number) ?? 0,
                angle: (p.angle as number) ?? 0,
                fallDuration: (p.fall_duration as number) ?? 0,
                posture: (p.posture as string) ?? "unknown",
                fallType: (p.fall_type as string) ?? "normal",
                ruleScore: (p.rule_score as number) ?? 0,
                mlScore: (p.ml_score as number) ?? 0,
                walkingAid: walkingAid ? {
                  type: (walkingAid.type as string) ?? "none",
                  established: (walkingAid.established as boolean) ?? false,
                  missing: (walkingAid.missing as boolean) ?? false,
                } : null,
              };
            });
            // 해당 카메라의 인원만 교체, 다른 카메라 인원 데이터는 유지
            const store = useMonitoringStore.getState();
            const otherPersons = store.personMetrics.filter(
              (p) => !p.personId.startsWith(`${cameraId}_`)
            );
            store.setPersonMetrics([...otherPersons, ...persons]);
          }
          // bbox 데이터 (Canvas 오버레이용) - 카메라별 병합
          if (Array.isArray(d.bboxes)) {
            const cameraId = (d.camera_id as string) ?? "cam0";
            const newBboxes: BBoxData[] = (d.bboxes as Record<string, unknown>[]).map((b) => ({
              personId: (b.person_id as string) ?? "",
              bbox: b.bbox as [number, number, number, number],
              isFallen: (b.is_fallen as boolean) ?? false,
              confidence: (b.confidence as number) ?? 0,
              cameraId: (b.camera_id as string) ?? cameraId,
            }));
            const store = useMonitoringStore.getState();
            // 해당 카메라의 bbox만 교체, 다른 카메라 데이터는 유지
            const otherBboxes = store.bboxes.filter(b => b.cameraId !== cameraId);
            store.setBBoxes([...otherBboxes, ...newBboxes]);
          }
          break;
        }
        case "alert_update": {
          const d = msg.data;
          const alertCameraId = (d.camera_id as string) ?? undefined;

          // 공간 필터링: 선택된 공간의 카메라가 아니면 무시
          const store0 = useMonitoringStore.getState();
          if (store0.roomCameraIds !== null && alertCameraId && !store0.roomCameraIds.includes(alertCameraId)) {
            break;
          }

          // 보행도구 분실 알림 처리
          if (d.walking_aid_missing) {
            const store = useMonitoringStore.getState();
            const pid = (d.person_id as string) ?? undefined;
            store.addEventLog(
              "warning",
              i18n.t("dashboard.eventLog.walkingAidCategory", "보행도구"),
              i18n.t("dashboard.eventLog.walkingAidMissing", { person: pid ?? i18n.t("dashboard.eventLog.patient", "환자"), defaultValue: `주의: ${pid ?? "환자"} 보행도구 미감지` }),
              pid,
              undefined,
              alertCameraId,
            );
            break;
          }

          const level = d.alert_level as string;
          if (level) {
            const store = useMonitoringStore.getState();
            const prevAlert = store.currentAlert;

            const personId = (d.person_id as string) ?? undefined;
            const fallType = (d.fall_type as string) ?? "unknown";

            if (
              d.state === "acknowledged" ||
              level === "safe"
            ) {
              // 서버가 acknowledge를 확인했거나 safe로 전환
              store.setIsAcknowledged(false);
              store.setCurrentAlert(level as "safe" | "warning" | "danger");
              store.setCurrentFallType("unknown");
              store.addEventLog(
                "safe",
                i18n.t("dashboard.eventLog.ackCategory", "확인"),
                i18n.t("dashboard.eventLog.acknowledged", "알림이 확인되었습니다."),
                personId,
                undefined,
                alertCameraId,
              );
            } else if (level === "danger" && !store.isAcknowledged && prevAlert !== "danger") {
              store.setCurrentAlert("danger");
              store.setCurrentFallType(fallType);
              store.incrementAlertCount();
              // 하이브리드 레이아웃: 알람 발생 카메라 자동 포커스
              if (alertCameraId) {
                store.setAlertCameraId(alertCameraId);
              }
              const fallLabel = _fallTypeLabel(fallType);
              store.addEventLog(
                "danger",
                i18n.t("dashboard.eventLog.dangerCategory", "낙상 감지"),
                i18n.t("dashboard.eventLog.fallDetected", { person: personId ?? i18n.t("dashboard.eventLog.patient", "환자"), fallType: fallLabel, defaultValue: `${personId ?? "환자"} ${fallLabel} 낙상이 감지되었습니다!` }),
                personId,
                fallType,
                alertCameraId,
              );
            } else if (level === "warning" && prevAlert === "safe") {
              const isActualFall = ["front_fall", "back_fall", "side_fall"].includes(fallType);
              store.setCurrentAlert("warning");
              store.setCurrentFallType(fallType);
              // 하이브리드 레이아웃: WARNING도 카메라 포커스 (실제 낙상 시)
              if (isActualFall && alertCameraId) {
                store.setAlertCameraId(alertCameraId);
              }
              store.addEventLog(
                "warning",
                isActualFall ? i18n.t("dashboard.eventLog.alertCategory", "경고") : i18n.t("dashboard.eventLog.warningCategory", "주의"),
                isActualFall
                  ? i18n.t("dashboard.eventLog.fallDetected", { person: personId ?? i18n.t("dashboard.eventLog.patient", "환자"), fallType: _fallTypeLabel(fallType), defaultValue: `${personId ?? "환자"} ${_fallTypeLabel(fallType)} 낙상이 감지되었습니다!` })
                  : i18n.t("dashboard.eventLog.abnormalPosture", { person: personId ?? i18n.t("dashboard.eventLog.patient", "환자"), defaultValue: `${personId ?? "환자"} 이상 자세가 감지되었습니다.` }),
                personId,
                fallType,
                alertCameraId,
              );
            } else if (!store.isAcknowledged) {
              store.setCurrentAlert(level as "safe" | "warning" | "danger");
            }
          }
          break;
        }
        case "pose_data": {
          // 포즈 데이터 → Canvas 스켈레톤 렌더링용 (카메라별 병합)
          const poses = msg.data.poses as Record<string, unknown>[] | undefined;
          const poseCameraId = (msg.data.camera_id as string) ?? "cam0";
          if (Array.isArray(poses)) {
            const newPoseData: PoseData[] = poses.map((p) => ({
              personId: (p.person_id as string) ?? "",
              landmarks: (p.landmarks as PoseData["landmarks"]) ?? [],
              cameraId: (p.camera_id as string) ?? poseCameraId,
            }));
            const store = useMonitoringStore.getState();
            const otherPoses = store.poseData.filter(p => p.cameraId !== poseCameraId);
            store.setPoseData([...otherPoses, ...newPoseData]);
          }
          break;
        }
        case "ping":
          wsRef.current?.send(JSON.stringify({ type: "pong" }));
          break;
        case "connection_status":
          break;
      }
    } catch {
      // 파싱 오류 무시
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    const state = wsRef.current?.readyState;
    if (state === WebSocket.OPEN || state === WebSocket.CONNECTING) return;

    useMonitoringStore.getState().setConnectionStatus("connecting");
    // 쿠키 기반 인증: same-origin WebSocket은 쿠키가 자동 전송됨
    const ws = new WebSocket(WS_BASE_URL);

    ws.onopen = () => {
      useMonitoringStore.getState().setConnectionStatus("connected");
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
    };

    ws.onmessage = handleMessage;

    ws.onclose = () => {
      useMonitoringStore.getState().setConnectionStatus("disconnected");
      wsRef.current = null;
      if (mountedRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(
            reconnectDelayRef.current * 2,
            MAX_RECONNECT_DELAY,
          );
          connect();
        }, reconnectDelayRef.current);
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [handleMessage]);

  const sendAcknowledge = useCallback((personId?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({ type: "acknowledge", person_id: personId ?? null }),
      );
    }
  }, []);

  // Store sendAcknowledge in zustand so Header can access it
  useEffect(() => {
    useMonitoringStore.getState().setWsSendAcknowledge(sendAcknowledge);
    return () => {
      useMonitoringStore.getState().setWsSendAcknowledge(null);
    };
  }, [sendAcknowledge]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { sendAcknowledge };
}
