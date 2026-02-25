import { useRef, useState, useCallback, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Camera,
  CameraOff,
  Maximize2,
  Minimize2,
  Eye,
  EyeOff,
  ShieldCheck,
  Play,
  Square,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { apiCall } from "@/lib/auth";
import {
  useMonitoringStore,
  type AlertLevel,
  type PrivacyMode,
  type BBoxData,
  type PoseData,
} from "@/store/monitoring";
import { WebRTCPlayer } from "./WebRTCPlayer";

const MJPEG_BASE_URL = "/api/stream/mjpeg";



// COCO 17-point skeleton connections
const COCO_SKELETON: [number, number][] = [
  [0, 1], [0, 2], [1, 3], [2, 4],       // head
  [5, 6],                                 // shoulders
  [5, 7], [7, 9],                         // left arm
  [6, 8], [8, 10],                        // right arm
  [5, 11], [6, 12],                       // torso
  [11, 12],                               // hips
  [11, 13], [13, 15],                     // left leg
  [12, 14], [14, 16],                     // right leg
];

// Person colors (match backend color scheme)
const PERSON_COLORS = [
  "#22c55e", // green
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#ec4899", // pink
  "#8b5cf6", // purple
  "#06b6d4", // cyan
  "#f97316", // orange
  "#14b8a6", // teal
];

interface VideoFeedProps {
  cameraId?: string;
  cameraName?: string;
  compact?: boolean;
  onClick?: () => void; // 하이브리드 레이아웃 카메라 클릭
  className?: string; // 추가 스타일링
  hideButtons?: boolean; // 다중 카메라 그리드 모드에서 버튼만 숨김 (이름/배지는 표시)
}

export function VideoFeed({ cameraId = "cam0", cameraName, compact = false, onClick, className, hideButtons = false }: VideoFeedProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { t } = useTranslation();
  const {
    isCameraActive: globalCameraActive,
    currentAlert,
    setCameraActive,
    privacyMode,
    setPrivacyMode,
    globalStreamMode,
    cameras,
  } = useMonitoringStore();

  // 다중 카메라: 카메라별 isActive 우선, 단일 카메라: 전역 isCameraActive 사용
  const perCameraActive = cameras.find((c) => c.id === cameraId)?.isActive;
  const isCameraActive = perCameraActive ?? globalCameraActive;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const MAX_RETRIES = 10;

  const handleStartCamera = useCallback(async () => {
    if (isLoading) return;
    setIsLoading(true);
    try {
      await apiCall("/api/stream/pipeline/resume", { method: "POST" });
      await apiCall(`/api/cameras/${cameraId}/start`, { method: "POST" });
      setCameraActive(true);
    } catch (e) {
      console.error("카메라 시작 실패:", e);
    } finally {
      setIsLoading(false);
    }
  }, [cameraId, isLoading, setCameraActive]);

  const handleStopCamera = useCallback(async () => {
    if (isLoading) return;
    setIsLoading(true);
    try {
      await apiCall(`/api/cameras/${cameraId}/stop`, { method: "POST" });
      // 파이프라인 pause 호출 안 함 — 다른 카메라가 활성 상태일 수 있음
      setCameraActive(false);
    } catch (e) {
      console.error("카메라 중지 실패:", e);
    } finally {
      setIsLoading(false);
    }
  }, [cameraId, isLoading, setCameraActive]);

  const privacyConfig = useMemo(() => ({
    skeleton: {
      icon: ShieldCheck,
      label: t("dashboard.video.privacy.skeleton"),
      description: t("dashboard.video.privacy.skeletonDesc"),
    },
    blur: {
      icon: EyeOff,
      label: t("dashboard.video.privacy.blur"),
      description: t("dashboard.video.privacy.blurDesc"),
    },
    full: {
      icon: Eye,
      label: t("dashboard.video.privacy.full"),
      description: t("dashboard.video.privacy.fullDesc"),
    },
  }), [t]);

  // 쿠키 기반 인증: same-origin <img> 태그는 쿠키를 자동 전송
  // 모든 카메라: /api/stream/mjpeg/{cameraId}
  const mjpegUrl = `${MJPEG_BASE_URL}/${cameraId}`;

  // Reset error when camera activates
  useEffect(() => {
    if (isCameraActive) {
      setStreamError(false);
      retryCountRef.current = 0;
    }
    return () => {
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [isCameraActive]);

  // MJPEG 스트림 에러 시 자동 재연결
  const handleStreamError = useCallback(() => {
    setStreamError(true);
    if (retryCountRef.current >= MAX_RETRIES) return;
    retryCountRef.current += 1;
    const delay = Math.min(2000 * retryCountRef.current, 10000);
    retryTimerRef.current = setTimeout(() => {
      setStreamError(false);
      if (imgRef.current) {
        imgRef.current.src = `${mjpegUrl}?retry=${Date.now()}`;
      }
    }, delay);
  }, [mjpegUrl]);


  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;

    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  }, []);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const cyclePrivacyMode = useCallback(() => {
    const modes: PrivacyMode[] = ["skeleton", "blur", "full"];
    const current: PrivacyMode = privacyMode ?? "skeleton";
    const currentIndex = modes.indexOf(current);
    const nextIndex = (currentIndex + 1) % modes.length;
    setPrivacyMode(modes[nextIndex] ?? "skeleton");
  }, [privacyMode, setPrivacyMode]);

  const PrivacyIcon = privacyConfig[privacyMode].icon;

  return (
    <Card
      ref={containerRef}
      onClick={onClick}
      className={cn(
        "border-2 transition-colors",
        currentAlert === "danger" && "border-danger animate-border-flash",
        currentAlert === "warning" && "border-warning",
        currentAlert === "safe" && "border-border",
        className,
      )}
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Camera className={cn("text-primary", compact ? "h-3 w-3" : "h-4 w-4")} aria-hidden="true" />
          <span className={compact ? "text-xs" : ""}>{cameraName || t("dashboard.video.title")}</span>
          {isCameraActive && (
            <Badge
              variant="default"
              className="bg-danger text-danger-foreground text-xs animate-pulse"
              aria-label={t("dashboard.video.live")}
            >
              LIVE
            </Badge>
          )}
        </CardTitle>
        {!hideButtons && (
          <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>

            {/* 카메라 시작/중지 */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant={isCameraActive ? "destructive" : "default"}
                  onClick={isCameraActive ? handleStopCamera : handleStartCamera}
                  disabled={isLoading}
                  aria-label={isCameraActive ? t("dashboard.video.stop") : t("dashboard.video.start")}
                >
                  {isCameraActive ? (
                    <Square className="h-4 w-4" />
                  ) : (
                    <Play className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{isCameraActive ? t("dashboard.video.stop") : t("dashboard.video.start")}</p>
              </TooltipContent>
            </Tooltip>

            {/* 프라이버시 모드 토글 */}
            {isCameraActive && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={cyclePrivacyMode}
                    aria-label={`${t("dashboard.settings.privacyMode")}: ${privacyConfig[privacyMode].label}`}
                  >
                    <PrivacyIcon className="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{privacyConfig[privacyMode].description}</p>
                </TooltipContent>
              </Tooltip>
            )}

            {/* 전체화면 */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={toggleFullscreen}
                  aria-label={isFullscreen ? t("dashboard.video.exitFullscreen") : t("dashboard.video.fullscreen")}
                >
                  {isFullscreen ? (
                    <Minimize2 className="h-4 w-4" />
                  ) : (
                    <Maximize2 className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>{isFullscreen ? t("dashboard.video.exitFullscreen") : t("dashboard.video.fullscreen")}</p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}
      </CardHeader>
      <CardContent className="p-3 pt-0">
        <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
          {/* WebRTC 모드 */}
          {isCameraActive && globalStreamMode === "webrtc" && (
            <WebRTCPlayer
              streamName="camera_default"
              fallbackUrl={mjpegUrl}
              className={cn(
                privacyMode === "blur" && "blur-lg",
              )}
            />
          )}

          {/* MJPEG 스트림 - raw 30fps (skeleton 모드에서는 숨김) */}
          {isCameraActive && globalStreamMode === "mjpeg" && privacyMode !== "skeleton" && (
            <img
              ref={imgRef}
              src={mjpegUrl}
              alt="실시간 카메라 피드"
              className={cn(
                "w-full h-full object-cover",
                privacyMode === "blur" && "blur-lg",
              )}
              onError={handleStreamError}
              onLoad={() => { retryCountRef.current = 0; setStreamError(false); }}
            />
          )}

          {/* Stream error fallback */}
          {streamError && globalStreamMode === "mjpeg" && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/80 text-muted-foreground">
              <p>{t("dashboard.video.streamDisconnected")}</p>
            </div>
          )}

          {/* AI 오버레이 Canvas (bbox + skeleton) */}
          {isCameraActive && globalStreamMode === "mjpeg" && (
            <OverlayCanvas privacyMode={privacyMode} cameraId={cameraId} />
          )}

          {/* 카메라 비활성 상태 */}
          {!isCameraActive && (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
              <CameraOff className="h-16 w-16 mb-4 opacity-30" aria-hidden="true" />
              <p className="text-lg font-medium">{t("dashboard.video.inactive")}</p>
              <p className="text-sm mt-1">{t("dashboard.video.inactiveDesc")}</p>
            </div>
          )}

          {/* 상태 오버레이 배지 */}
          {isCameraActive && (
            <div className="absolute top-3 left-3 flex items-center gap-2">
              <StatusBadge level={currentAlert} />
              <Badge
                variant="outline"
                className="text-xs bg-black/50 border-white/20 text-white"
              >
                {privacyConfig[privacyMode].label}
              </Badge>
            </div>
          )}

          {/* 연결 상태 표시 */}
          {isCameraActive && (
            <ConnectionIndicator />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * AI 결과 Canvas 오버레이
 * - full/blur 모드: MJPEG 위에 투명 오버레이 (bbox + skeleton + label)
 * - skeleton 모드: 검정 배경 + skeleton + bbox (raw 영상 숨김 = 프라이버시)
 */
function OverlayCanvas({ privacyMode, cameraId = "cam0" }: { privacyMode: PrivacyMode; cameraId?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);
  // privacyMode를 ref로 유지하여 rAF 루프 내에서 최신값 참조
  const privacyModeRef = useRef(privacyMode);
  privacyModeRef.current = privacyMode;
  const cameraIdRef = useRef(cameraId);
  cameraIdRef.current = cameraId;

  // requestAnimationFrame 기반 렌더링 루프 (60fps, Zustand store 직접 구독)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let lastDataHash = "";

    const render = () => {
      const store = useMonitoringStore.getState();
      const currentCamId = cameraIdRef.current;
      const mode = privacyModeRef.current;
      const overlay = store.settings.overlayEnabled;

      const bboxes = store.bboxes.filter(b => (b.cameraId ?? "cam0") === currentCamId);
      const poses = store.poseData.filter(p => (p.cameraId ?? "cam0") === currentCamId);

      // 데이터 변경 체크 (불필요한 재렌더 방지)
      const dataHash = `${mode}:${overlay}:${bboxes.length}:${poses.length}:${poses[0]?.landmarks?.[0]?.x ?? 0}`;
      if (dataHash === lastDataHash) {
        rafRef.current = requestAnimationFrame(render);
        return;
      }
      lastDataHash = dataHash;

      // Canvas 크기를 부모 컨테이너에 맞춤
      const parent = canvas.parentElement;
      if (parent) {
        const rect = parent.getBoundingClientRect();
        if (canvas.width !== rect.width || canvas.height !== rect.height) {
          canvas.width = rect.width;
          canvas.height = rect.height;
        }
      }

      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      if (mode === "skeleton") {
        ctx.fillStyle = "#000000";
        ctx.fillRect(0, 0, w, h);
      }

      if (overlay) {
        poses.forEach((pose, idx) => {
          const color = PERSON_COLORS[idx % PERSON_COLORS.length]!;
          drawSkeleton(ctx, pose, w, h, color);
        });

        bboxes.forEach((bbox, idx) => {
          const color = bbox.isFallen ? "#ef4444" : PERSON_COLORS[idx % PERSON_COLORS.length]!;
          drawBBox(ctx, bbox, w, h, color);
        });
      }

      rafRef.current = requestAnimationFrame(render);
    };

    rafRef.current = requestAnimationFrame(render);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);  // rAF 루프는 한 번만 시작, 내부에서 최신 상태 직접 참조

  // ResizeObserver로 Canvas 크기 반응형 유지
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas?.parentElement) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width;
          canvas.height = height;
        }
      }
    });

    observer.observe(canvas.parentElement);
    return () => observer.disconnect();
  }, [cameraId]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden="true"
    />
  );
}

/** COCO 17-point 스켈레톤 그리기 */
function drawSkeleton(
  ctx: CanvasRenderingContext2D,
  pose: PoseData,
  w: number,
  h: number,
  color: string,
) {
  const lm = pose.landmarks;
  if (!lm || lm.length < 17) return;

  // 연결선
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.globalAlpha = 0.8;

  for (const [i, j] of COCO_SKELETON) {
    const a = lm[i];
    const b = lm[j];
    if (!a || !b) continue;
    if (a.visibility < 0.3 || b.visibility < 0.3) continue;

    ctx.beginPath();
    ctx.moveTo(a.x * w, a.y * h);
    ctx.lineTo(b.x * w, b.y * h);
    ctx.stroke();
  }

  // 관절점
  ctx.globalAlpha = 1.0;
  for (let i = 0; i < Math.min(lm.length, 17); i++) {
    const p = lm[i];
    if (!p || p.visibility < 0.3) continue;

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(p.x * w, p.y * h, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.globalAlpha = 1.0;
}

/** 바운딩 박스 + 라벨 그리기 */
function drawBBox(
  ctx: CanvasRenderingContext2D,
  bbox: BBoxData,
  w: number,
  h: number,
  color: string,
) {
  const [x1, y1, x2, y2] = bbox.bbox;
  const px1 = x1 * w;
  const py1 = y1 * h;
  const pw = (x2 - x1) * w;
  const ph = (y2 - y1) * h;

  // 바운딩 박스
  ctx.strokeStyle = color;
  ctx.lineWidth = bbox.isFallen ? 3 : 2;
  ctx.strokeRect(px1, py1, pw, ph);

  // 라벨 배경
  const idNum = bbox.personId.replace("person_", "");
  const label = bbox.isFallen
    ? `ID:${idNum} FALL ${(bbox.confidence * 100).toFixed(0)}%`
    : `ID:${idNum} ${(bbox.confidence * 100).toFixed(0)}%`;

  ctx.font = "bold 12px sans-serif";
  const textMetrics = ctx.measureText(label);
  const textHeight = 16;
  const padding = 4;

  ctx.fillStyle = bbox.isFallen ? "rgba(239, 68, 68, 0.8)" : "rgba(0, 0, 0, 0.6)";
  ctx.fillRect(
    px1,
    py1 - textHeight - padding,
    textMetrics.width + padding * 2,
    textHeight + padding,
  );

  ctx.fillStyle = "#ffffff";
  ctx.fillText(label, px1 + padding, py1 - padding);
}

function StatusBadge({ level }: { level: AlertLevel }) {
  const { t } = useTranslation();
  return (
    <Badge
      className={cn(
        "text-sm px-3 py-1",
        level === "safe" && "bg-safe/80 text-safe-foreground",
        level === "warning" && "bg-warning/80 text-warning-foreground",
        level === "danger" &&
        "bg-danger/80 text-danger-foreground animate-danger-pulse",
      )}
      role={level === "danger" ? "alert" : undefined}
      aria-live={level !== "safe" ? "assertive" : undefined}
    >
      {level === "safe" && t("dashboard.video.status.safe")}
      {level === "warning" && t("dashboard.video.status.warning")}
      {level === "danger" && t("dashboard.video.status.danger")}
    </Badge>
  );
}

function ConnectionIndicator() {
  const { t } = useTranslation();
  const connectionStatus = useMonitoringStore((s) => s.connectionStatus);

  return (
    <div className="absolute bottom-3 right-3">
      <div
        className={cn(
          "h-2 w-2 rounded-full",
          connectionStatus === "connected" && "bg-safe",
          connectionStatus === "connecting" && "bg-warning animate-pulse",
          connectionStatus === "disconnected" && "bg-danger",
        )}
        aria-label={`${t("dashboard.status.label")}: ${connectionStatus === "connected" ? t("dashboard.video.connection.connected") : connectionStatus === "connecting" ? t("dashboard.video.connection.connecting") : t("dashboard.video.connection.disconnected")}`}
      />
    </div>
  );
}
