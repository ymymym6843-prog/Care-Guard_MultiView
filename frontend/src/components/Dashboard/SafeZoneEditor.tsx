/**
 * Safe-Zone 폴리곤 에디터
 *
 * Canvas 위에서 마우스 클릭으로 폴리곤을 그리고,
 * 드래그로 꼭짓점을 이동할 수 있습니다.
 */

import { useRef, useState, useCallback, useEffect } from "react";
import { Trash2, Save, Shield, Video, VideoOff, Camera } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiCall } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { useMonitoringStore } from "@/store/monitoring";

const MJPEG_BASE_URL = "/api/stream/mjpeg";

interface Point {
  x: number;
  y: number;
}

interface Zone {
  id?: number;
  name: string;
  zone_type: "safe" | "danger" | "exclusion";
  polygon: Point[];
  is_active: boolean;
}

const ZONE_COLORS = {
  safe: { fill: "rgba(34, 197, 94, 0.2)", stroke: "#22c55e" },
  danger: { fill: "rgba(239, 68, 68, 0.2)", stroke: "#ef4444" },
  exclusion: { fill: "rgba(156, 163, 175, 0.2)", stroke: "#9ca3af" },
};

export function SafeZoneEditor({ cameraId: externalCameraId, showCameraTabs = false }: { cameraId?: string; showCameraTabs?: boolean }) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [zones, setZones] = useState<Zone[]>([]);
  const [currentPoints, setCurrentPoints] = useState<Point[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [newZoneName, setNewZoneName] = useState("");
  const [newZoneType, setNewZoneType] = useState<"safe" | "danger" | "exclusion">("safe");
  const [streamReady, setStreamReady] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const isCameraActive = useMonitoringStore((s) => s.isCameraActive);
  const cameras = useMonitoringStore((s) => s.cameras);
  const [internalCamera, setInternalCamera] = useState("");

  // 카메라 탭 모드: 외부 cameraId가 없고 showCameraTabs이면 내부 선택 사용
  const useInternalTabs = showCameraTabs && !externalCameraId;
  const cameraId = externalCameraId ?? (internalCamera || (cameras.length > 0 ? cameras[0]!.id : "default"));

  // 카메라 목록이 로드되면 첫 번째 카메라 선택
  useEffect(() => {
    if (useInternalTabs && cameras.length > 0 && !internalCamera) {
      setInternalCamera(cameras[0]!.id);
    }
  }, [useInternalTabs, cameras, internalCamera]);

  // 해당 카메라가 활성 상태인지 확인 (카메라별 또는 전역)
  const perCameraActive = cameras.find((c) => c.id === cameraId)?.isActive;
  const cameraActive = perCameraActive ?? isCameraActive;

  // 카메라 활성/비활성 전환 시 스트림 리셋 + 재연결
  useEffect(() => {
    setStreamReady(false);
    if (cameraActive) {
      // key를 변경하여 <img> 강제 재마운트 (MJPEG 재연결)
      setStreamKey((k) => k + 1);
    }
  }, [cameraActive, cameraId]);

  // 기존 Zone 불러오기
  const fetchZones = useCallback(async () => {
    try {
      const res = await apiCall(`/api/zones/?camera_id=${cameraId}`);
      if (res.ok) {
        const data = await res.json();
        setZones(data);
      }
    } catch {
      // ignore
    }
  }, [cameraId]);

  useEffect(() => {
    fetchZones();
    // 카메라 변경 시 스트림 리셋 + 재연결
    setStreamReady(false);
    setStreamKey((k) => k + 1);
  }, [fetchZones, cameraId]);

  // Canvas 리사이징 (ResizeObserver)
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        canvas.width = width;
        canvas.height = height;
      }
    });

    resizeObserver.observe(container);
    return () => resizeObserver.disconnect();
  }, []);

  // Canvas 그리기
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // 배경 격자 (카메라 스트림 없을 때만)
    if (!streamReady) {
      const isDark = document.documentElement.classList.contains("dark");
      ctx.strokeStyle = isDark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.08)";
      ctx.lineWidth = 1;
      for (let i = 0; i < 10; i++) {
        ctx.beginPath();
        ctx.moveTo((w / 10) * i, 0);
        ctx.lineTo((w / 10) * i, h);
        ctx.stroke();
        ctx.beginPath();
        ctx.moveTo(0, (h / 10) * i);
        ctx.lineTo(w, (h / 10) * i);
        ctx.stroke();
      }
    }

    // 저장된 Zone 그리기
    for (const zone of zones) {
      if (zone.polygon.length < 3) continue;
      const colors = ZONE_COLORS[zone.zone_type] || ZONE_COLORS.safe;

      ctx.beginPath();
      const first = zone.polygon[0];
      if (!first) continue;
      ctx.moveTo(first.x * w, first.y * h);
      for (let i = 1; i < zone.polygon.length; i++) {
        const pt = zone.polygon[i];
        if (!pt) continue;
        ctx.lineTo(pt.x * w, pt.y * h);
      }
      ctx.closePath();
      ctx.fillStyle = colors.fill;
      ctx.fill();
      ctx.strokeStyle = colors.stroke;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Zone 이름 표시 (배경 포함, 카메라 위에서도 가독성 확보)
      const cx = zone.polygon.reduce((sum, p) => sum + p.x, 0) / zone.polygon.length;
      const cy = zone.polygon.reduce((sum, p) => sum + p.y, 0) / zone.polygon.length;
      ctx.font = "bold 12px sans-serif";
      ctx.textAlign = "center";
      const textMetrics = ctx.measureText(zone.name);
      const textW = textMetrics.width + 8;
      ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
      ctx.fillRect(cx * w - textW / 2, cy * h - 10, textW, 16);
      ctx.fillStyle = "#ffffff";
      ctx.fillText(zone.name, cx * w, cy * h + 2);
    }

    // 현재 그리는 중인 폴리곤
    if (currentPoints.length > 0) {
      const colors = ZONE_COLORS[newZoneType];
      const firstPt = currentPoints[0];
      if (!firstPt) return;
      ctx.beginPath();
      ctx.moveTo(firstPt.x * w, firstPt.y * h);
      for (let i = 1; i < currentPoints.length; i++) {
        const pt = currentPoints[i];
        if (!pt) continue;
        ctx.lineTo(pt.x * w, pt.y * h);
      }
      ctx.strokeStyle = colors.stroke;
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 5]);
      ctx.stroke();
      ctx.setLineDash([]);

      // 꼭짓점 표시
      for (const pt of currentPoints) {
        ctx.beginPath();
        ctx.arc(pt.x * w, pt.y * h, 5, 0, Math.PI * 2);
        ctx.fillStyle = colors.stroke;
        ctx.fill();
      }
    }
  }, [zones, currentPoints, newZoneType, streamReady]);

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!isDrawing) return;
      const canvas = canvasRef.current;
      if (!canvas) return;

      const rect = canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = (e.clientY - rect.top) / rect.height;

      setCurrentPoints((prev) => [...prev, { x, y }]);
    },
    [isDrawing],
  );

  const handleSaveZone = useCallback(async () => {
    if (currentPoints.length < 3) return;

    try {
      const res = await apiCall("/api/zones/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newZoneName || t("dashboard.safeZone.newZone"),
          camera_id: cameraId,
          zone_type: newZoneType,
          polygon: currentPoints,
        }),
      });

      if (res.ok) {
        setCurrentPoints([]);
        setIsDrawing(false);
        setNewZoneName("");
        fetchZones();
      }
    } catch {
      // ignore
    }
  }, [currentPoints, newZoneName, newZoneType, fetchZones, t]);

  const handleDeleteZone = useCallback(
    async (zoneId: number) => {
      try {
        await apiCall(`/api/zones/${zoneId}`, { method: "DELETE" });
        fetchZones();
      } catch {
        // ignore
      }
    },
    [fetchZones],
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Shield className="h-4 w-4 text-primary" />
          {t("dashboard.safeZone.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* 카메라 선택 탭 (showCameraTabs 모드) */}
        {useInternalTabs && cameras.length > 0 && (
          <div className="flex gap-2 border-b pb-2 overflow-x-auto">
            {cameras.map((cam) => (
              <Button
                key={cam.id}
                variant={cameraId === cam.id ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  setInternalCamera(cam.id);
                  setCurrentPoints([]);
                  setIsDrawing(false);
                }}
                className="whitespace-nowrap"
              >
                <Camera className="w-3 h-3 mr-1" />
                {cam.name}
                {cam.isActive && (
                  <span className="ml-1 h-1.5 w-1.5 rounded-full bg-green-400 inline-block" />
                )}
              </Button>
            ))}
          </div>
        )}

        {/* 캔버스 + 카메라 미리보기 */}
        <div ref={containerRef} className="relative w-full aspect-video bg-black rounded-lg overflow-hidden">
          {/* MJPEG 카메라 스트림 배경 (카메라 활성 시에만 연결) */}
          {cameraActive && (
            <img
              key={streamKey}
              src={`${MJPEG_BASE_URL}/${cameraId}`}
              alt="camera preview"
              className="absolute inset-0 w-full h-full object-cover"
              onLoad={() => setStreamReady(true)}
              onError={() => setStreamReady(false)}
            />
          )}
          {/* 카메라 비활성 안내 */}
          {!cameraActive && (
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-[5]">
              <VideoOff className="h-8 w-8 text-muted-foreground mb-2" />
              <span className="text-xs text-muted-foreground">카메라가 꺼져 있습니다</span>
            </div>
          )}
          {/* 스트림 로드 시 LIVE 뱃지 */}
          {streamReady && cameraActive && (
            <div className="absolute top-2 left-2 z-20 flex items-center gap-1 bg-black/60 rounded px-1.5 py-0.5 pointer-events-none">
              <Video className="h-3 w-3 text-green-400" />
              <span className="text-[10px] text-green-400 font-medium">LIVE</span>
            </div>
          )}
          {/* 투명 캔버스 오버레이 (항상 투명 — 배경은 컨테이너 bg-black) */}
          <canvas
            ref={canvasRef}
            onClick={handleCanvasClick}
            className={cn(
              "absolute inset-0 w-full h-full rounded-lg border z-10",
              isDrawing ? "cursor-crosshair border-primary" : "border-border",
            )}
          />
        </div>

        {/* 컨트롤 */}
        <div className="flex items-center gap-2 flex-wrap">
          {!isDrawing ? (
            <Button
              size="sm"
              onClick={() => {
                setIsDrawing(true);
                setCurrentPoints([]);
              }}
            >
              <Shield className="h-4 w-4 mr-1" />
              {t("dashboard.safeZone.addZone")}
            </Button>
          ) : (
            <div className="flex flex-col gap-2 w-full p-3 border rounded-md bg-muted/30">
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  type="text"
                  value={newZoneName}
                  onChange={(e) => setNewZoneName(e.target.value)}
                  className="h-8 px-2 text-sm border rounded-md bg-background flex-1 min-w-[120px]"
                  placeholder={t("dashboard.safeZone.zoneName")}
                />
                <select
                  value={newZoneType}
                  onChange={(e) => setNewZoneType(e.target.value as "safe" | "danger" | "exclusion")}
                  className="h-8 px-2 text-sm border rounded-md bg-background"
                >
                  <option value="safe">{t("dashboard.safeZone.safeZone")} (낙상 감지 제외)</option>
                  <option value="danger">{t("dashboard.safeZone.dangerZone")} (진입 경보)</option>
                  <option value="exclusion">{t("dashboard.safeZone.exclusionZone")} (감지 제외)</option>
                </select>
              </div>

              <div className="text-xs text-muted-foreground bg-background p-2 rounded border">
                <p className="font-semibold mb-1">사용 방법:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  <li>화면을 클릭하여 꼭짓점을 추가합니다. (최소 3개)</li>
                  <li><strong>저장</strong> 버튼을 눌러 영역을 확정합니다.</li>
                </ul>
              </div>

              <div className="flex justify-end gap-2 mt-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setIsDrawing(false);
                    setCurrentPoints([]);
                  }}
                >
                  {t("dashboard.safeZone.cancel")}
                </Button>
                <Button
                  size="sm"
                  onClick={handleSaveZone}
                  disabled={currentPoints.length < 3}
                >
                  <Save className="h-4 w-4 mr-1" />
                  {t("dashboard.safeZone.save")}
                </Button>
              </div>
              <div className="text-right text-xs text-muted-foreground">
                {currentPoints.length} {t("dashboard.safeZone.vertices")}
              </div>
            </div>
          )}
        </div>

        {/* 안내 문구 (그리기 전) */}
        {!isDrawing && zones.length === 0 && (
          <div className="text-sm text-muted-foreground text-center py-8 bg-muted/20 rounded-lg border border-dashed">
            <Shield className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p>등록된 안전 구역이 없습니다.</p>
            <p className="text-xs mt-1">"영역 추가" 버튼을 눌러 침대, 소파 등 낙상 오감지가 잦은 구역을 설정하세요.</p>
          </div>
        )}

        {/* Zone 목록 */}
        {zones.length > 0 && (
          <div className="space-y-1">
            {zones.map((zone) => (
              <div
                key={zone.id}
                className="flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-muted/50"
              >
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: ZONE_COLORS[zone.zone_type]?.stroke }}
                  />
                  <span className="text-sm">{zone.name}</span>
                  <Badge variant="outline" className="text-xs">
                    {zone.zone_type}
                  </Badge>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => zone.id && handleDeleteZone(zone.id)}
                  aria-label={t("dashboard.safeZone.deleteZone", { name: zone.name })}
                >
                  <Trash2 className="h-3 w-3 text-danger" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
