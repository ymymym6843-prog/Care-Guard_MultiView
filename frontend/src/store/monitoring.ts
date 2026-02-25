import { create } from "zustand";

export type AlertLevel = "safe" | "warning" | "danger";
export type ConnectionStatus = "connected" | "disconnected" | "connecting";
export type PrivacyMode = "skeleton" | "blur" | "full";

export interface EventLogEntry {
  id: string;
  timestamp: Date;
  level: AlertLevel;
  category: string;
  message: string;
  personId?: string;
  fallType?: string;
  cameraId?: string;
}

export interface RoomInfo {
  id: number;
  name: string;
  description: string;
  isActive: boolean;
  cameraCount: number;
}

export interface DetectionMetrics {
  personCount: number;
  fps: number;
  fallConfidence: number;
  headY: number;
  hipY: number;
  angle: number;
  walkingAidUsers: number;
}

export interface BBoxData {
  personId: string;
  bbox: [number, number, number, number]; // normalized x1, y1, x2, y2
  isFallen: boolean;
  confidence: number;
  cameraId?: string;
}

export interface PoseLandmark {
  x: number;
  y: number;
  z: number;
  visibility: number;
}

export interface PoseData {
  personId: string;
  landmarks: PoseLandmark[];
  cameraId?: string;
}

export interface CameraInfo {
  id: string;
  name: string;
  source: string;
  isActive: boolean;
  resolution: string;
  fps: number;
  demoMode: boolean;
}

export interface PersonMetrics {
  personId: string;
  fallConfidence: number;
  isFallen: boolean;
  headY: number;
  hipY: number;
  angle: number;
  fallDuration: number;
  posture: string;
  fallType: string;
  ruleScore: number;
  mlScore: number;
  walkingAid: {
    type: string;
    established: boolean;
    missing: boolean;
  } | null;
}

interface MonitoringState {
  // 연결 상태
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;

  // 알림 상태
  currentAlert: AlertLevel;
  currentFallType: string; // 낙상 유형 (pre_impact, front_fall, back_fall, side_fall, unknown)
  alertCount: number;
  alertDuration: number;
  setCurrentAlert: (level: AlertLevel) => void;
  setCurrentFallType: (fallType: string) => void;
  incrementAlertCount: () => void;
  clearAlerts: () => void;
  setAlertDuration: (duration: number) => void;
  isAcknowledged: boolean;
  setIsAcknowledged: (v: boolean) => void;

  // WebSocket acknowledge 콜백 (Header 등에서 접근 가능)
  wsSendAcknowledge: ((personId?: string) => void) | null;
  setWsSendAcknowledge: (fn: ((personId?: string) => void) | null) => void;

  // 감지 메트릭
  metrics: DetectionMetrics;
  setMetrics: (metrics: Partial<DetectionMetrics>) => void;

  // 카메라별 FPS (다중 카메라 시 개별 FPS 저장)
  perCameraFps: Record<string, number>;
  setPerCameraFps: (cameraId: string, fps: number) => void;

  // 카메라별 알림 수준 (다중 카메라 시 최고 수준 계산용)
  perCameraAlert: Record<string, AlertLevel>;
  setPerCameraAlert: (cameraId: string, level: AlertLevel) => void;
  clearPerCameraAlert: () => void;

  // 다중 인원 메트릭
  personMetrics: PersonMetrics[];
  setPersonMetrics: (persons: PersonMetrics[]) => void;

  // AI 오버레이 (Canvas 렌더링용)
  bboxes: BBoxData[];
  setBBoxes: (bboxes: BBoxData[]) => void;
  poseData: PoseData[];
  setPoseData: (poses: PoseData[]) => void;

  // 이벤트 로그
  eventLog: EventLogEntry[];
  addEventLog: (
    level: AlertLevel,
    category: string,
    message: string,
    personId?: string,
    fallType?: string,
    cameraId?: string,
  ) => void;
  clearEventLog: () => void;

  // 카메라
  isCameraActive: boolean;
  setCameraActive: (active: boolean) => void;
  selectedCamera: string;
  setSelectedCamera: (camera: string) => void;

  // 프라이버시 모드
  privacyMode: PrivacyMode;
  setPrivacyMode: (mode: PrivacyMode) => void;

  // 전역 스트림 모드 (모든 카메라 공유)
  globalStreamMode: "mjpeg" | "webrtc";
  setGlobalStreamMode: (mode: "mjpeg" | "webrtc") => void;

  // 다중 카메라
  multiCameraEnabled: boolean;
  setMultiCameraEnabled: (enabled: boolean) => void;
  cameras: CameraInfo[];
  setCameras: (cameras: CameraInfo[]) => void;

  // 하이브리드 레이아웃: 포커스 카메라
  focusedCamera: string | null; // 확대할 카메라 ID
  setFocusedCamera: (cameraId: string | null) => void;
  alertCameraId: string | null; // 알람 발생 카메라 ID
  setAlertCameraId: (cameraId: string | null) => void;

  // 공간(Room) 관리
  rooms: RoomInfo[];
  setRooms: (rooms: RoomInfo[]) => void;
  selectedRoomId: number | null; // null = 전체 공간
  setSelectedRoomId: (roomId: number | null) => void;
  roomCameraIds: string[] | null; // null = 전체, [] = 해당 공간 카메라 없음
  setRoomCameraIds: (ids: string[] | null) => void;

  // 감지 설정
  settings: {
    fallThresholdTime: number;
    dangerThresholdTime: number;
    sensitivity: number;
    soundEnabled: boolean;
    soundVolume: number;
    ttsEnabled: boolean;
    overlayEnabled: boolean; // 스켈레톤/bbox 오버레이 토글 (발표용)
  };
  updateSettings: (
    settings: Partial<MonitoringState["settings"]>,
  ) => void;
}

export const useMonitoringStore = create<MonitoringState>()((set) => ({
  // 연결 상태
  connectionStatus: "disconnected",
  setConnectionStatus: (status) => set({ connectionStatus: status }),

  // 알림 상태
  currentAlert: "safe",
  currentFallType: "unknown",
  alertCount: 0,
  alertDuration: 0,
  setCurrentAlert: (level) => set({ currentAlert: level }),
  setCurrentFallType: (fallType) => set({ currentFallType: fallType }),
  incrementAlertCount: () =>
    set((state) => ({ alertCount: state.alertCount + 1 })),
  clearAlerts: () => set({ alertCount: 0, currentAlert: "safe", currentFallType: "unknown", alertDuration: 0, isAcknowledged: true }),
  setAlertDuration: (duration) => set({ alertDuration: duration }),
  isAcknowledged: false,
  setIsAcknowledged: (v) => set({ isAcknowledged: v }),

  // WebSocket acknowledge 콜백
  wsSendAcknowledge: null,
  setWsSendAcknowledge: (fn) => set({ wsSendAcknowledge: fn }),

  // 감지 메트릭
  metrics: {
    personCount: 0,
    fps: 0,
    fallConfidence: 0,
    headY: 0,
    hipY: 0,
    angle: 0,
    walkingAidUsers: 0,
  },
  setMetrics: (metrics) =>
    set((state) => ({ metrics: { ...state.metrics, ...metrics } })),

  // 카메라별 FPS
  perCameraFps: {},
  setPerCameraFps: (cameraId, fps) =>
    set((state) => ({ perCameraFps: { ...state.perCameraFps, [cameraId]: fps } })),

  // 카메라별 알림 수준
  perCameraAlert: {},
  setPerCameraAlert: (cameraId, level) =>
    set((state) => ({ perCameraAlert: { ...state.perCameraAlert, [cameraId]: level } })),
  clearPerCameraAlert: () => set({ perCameraAlert: {} }),

  // 다중 인원 메트릭
  personMetrics: [],
  setPersonMetrics: (persons) => set({ personMetrics: persons }),

  // AI 오버레이 (Canvas 렌더링용)
  bboxes: [],
  setBBoxes: (bboxes) => set({ bboxes }),
  poseData: [],
  setPoseData: (poses) => set({ poseData: poses }),

  // 이벤트 로그
  eventLog: [],
  addEventLog: (level, category, message, personId?, fallType?, cameraId?) =>
    set((state) => ({
      eventLog: [
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          timestamp: new Date(),
          level,
          category,
          message,
          personId,
          fallType,
          cameraId,
        },
        ...state.eventLog,
      ].slice(0, 100),
    })),
  clearEventLog: () => set({ eventLog: [] }),

  // 카메라
  isCameraActive: false,
  setCameraActive: (active) => set({ isCameraActive: active }),
  selectedCamera: "",
  setSelectedCamera: (camera) => set({ selectedCamera: camera }),

  // 프라이버시 모드 (기본: skeleton - 한국 PIPA 준수)
  privacyMode: "skeleton",
  setPrivacyMode: (mode) => set({ privacyMode: mode }),

  // 전역 스트림 모드 (모든 카메라 공유)
  globalStreamMode: "mjpeg",
  setGlobalStreamMode: (mode) => set({ globalStreamMode: mode }),

  // 다중 카메라
  multiCameraEnabled: false,
  setMultiCameraEnabled: (enabled) => set({ multiCameraEnabled: enabled }),
  cameras: [],
  setCameras: (cameras) => set({ cameras }),

  // 하이브리드 레이아웃: 포커스 카메라
  focusedCamera: null,
  setFocusedCamera: (cameraId) => set({ focusedCamera: cameraId }),
  alertCameraId: null,
  setAlertCameraId: (cameraId) => set({ alertCameraId: cameraId }),

  // 공간(Room) 관리
  rooms: [],
  setRooms: (rooms) => set({ rooms }),
  selectedRoomId: null,
  setSelectedRoomId: (roomId) => set({ selectedRoomId: roomId }),
  roomCameraIds: null,
  setRoomCameraIds: (ids) => set({ roomCameraIds: ids }),

  // 감지 설정
  settings: {
    fallThresholdTime: 3,
    dangerThresholdTime: 10,
    sensitivity: 0.5,
    soundEnabled: true,
    soundVolume: 0.5,
    ttsEnabled: true,
    overlayEnabled: true, // 스켈레톤/bbox 오버레이 기본값 ON
  },
  updateSettings: (settings) =>
    set((state) => ({
      settings: { ...state.settings, ...settings },
    })),
}));
