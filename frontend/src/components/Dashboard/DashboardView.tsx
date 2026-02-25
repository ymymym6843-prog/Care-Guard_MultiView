import { useEffect, useCallback, useState } from "react";
import { StatusCard } from "./StatusCard";
import { MetricsCard } from "./MetricsCard";
import { VideoFeed } from "./VideoFeed";
import { EventLog } from "./EventLog";
import { SettingsCard } from "./SettingsCard";
import { DemoVideoCard } from "./DemoVideoCard";
import { SafeZoneEditor } from "./SafeZoneEditor";
import { useMonitoringStore } from "@/store/monitoring";
import { apiCall } from "@/lib/auth";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Settings, Camera } from "lucide-react";
import { CAMERA_STATUS_POLL_MS } from "@/lib/constants";

// Simple Input component if not exists
function SimpleInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        props.className
      )}
    />
  );
}

export function DashboardView() {
  const {
    multiCameraEnabled,
    cameras,
    setMultiCameraEnabled,
    setCameras,
    focusedCamera,
    setFocusedCamera,
    alertCameraId,
    setAlertCameraId,
    currentAlert,
    globalStreamMode,
    setGlobalStreamMode,
    roomCameraIds,
  } = useMonitoringStore();

  const [isSafeZoneOpen, setIsSafeZoneOpen] = useState(false);
  const [selectedSafeZoneCamera, setSelectedSafeZoneCamera] = useState<string>("");
  const [isCameraSettingsOpen, setIsCameraSettingsOpen] = useState(false);
  const [isLoadingGlobal, setIsLoadingGlobal] = useState(false);

  // 카메라 목록 조회
  const fetchCameras = useCallback(async () => {
    try {
      const res = await apiCall("/api/cameras");
      const data = await res.json();
      setMultiCameraEnabled(data.multi_camera_enabled ?? false);
      if (Array.isArray(data.cameras)) {
        setCameras(
          data.cameras.map((c: Record<string, unknown>) => ({
            id: (c.id as string) ?? "",
            name: (c.name as string) ?? "",
            source: (c.source as string) ?? "",
            isActive: (c.is_active as boolean) ?? true,
            resolution: (c.resolution as string) ?? "",
            fps: (c.fps as number) ?? 0,
            demoMode: (c.demo_mode as boolean) ?? false,
          })),
        );
      }
    } catch {
      // 실패 시 유지
    }
  }, [setMultiCameraEnabled, setCameras]);

  useEffect(() => {
    fetchCameras();
    const interval = setInterval(fetchCameras, CAMERA_STATUS_POLL_MS);
    return () => clearInterval(interval);
  }, [fetchCameras]);

  // Safe-zone 모달 열릴 때 첫 번째 카메라 선택
  useEffect(() => {
    if (isSafeZoneOpen && cameras.length > 0 && !selectedSafeZoneCamera) {
      setSelectedSafeZoneCamera(cameras[0]?.id ?? "");
    }
  }, [isSafeZoneOpen, cameras, selectedSafeZoneCamera]);

  // 알람 발생 시 자동 포커스
  useEffect(() => {
    if (currentAlert !== "safe" && alertCameraId && multiCameraEnabled) {
      setFocusedCamera(alertCameraId);
    } else if (currentAlert === "safe") {
      const timer = setTimeout(() => {
        setFocusedCamera(null);
        setAlertCameraId(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [currentAlert, alertCameraId, multiCameraEnabled, setFocusedCamera, setAlertCameraId]);

  const activeCameras = multiCameraEnabled
    ? cameras
        .filter((c) => c && c.isActive)
        .filter((c) => roomCameraIds === null || roomCameraIds.includes(c.id))
    : [];

  const showMultiCamera = multiCameraEnabled && (activeCameras.length > 1 || cameras.length > 1);
  const isFocusMode = showMultiCamera && focusedCamera;
  const mainCamera = activeCameras.find((c) => c.id === focusedCamera);
  const pipCameras = activeCameras.filter((c) => c.id !== focusedCamera);

  const handleCameraClick = (cameraId: string) => {
    if (focusedCamera === cameraId) {
      setFocusedCamera(null);
    } else {
      setFocusedCamera(cameraId);
    }
  };

  // 전역 카메라 시작/중지
  const handleGlobalStartStop = useCallback(async () => {
    if (isLoadingGlobal) return;
    setIsLoadingGlobal(true);

    const anyActive = cameras.some((cam) => cam?.isActive);

    try {
      if (anyActive) {
        // 모든 카메라 중지 (병렬, 개별 실패 허용)
        const stopResults = await Promise.allSettled(
          cameras.filter((cam) => cam.isActive).map((cam) =>
            apiCall(`/api/cameras/${cam.id}/stop`, { method: "POST" })
          )
        );
        const stopFailed = stopResults.filter((r) => r.status === "rejected").length;
        if (stopFailed > 0) console.warn(`${stopFailed}개 카메라 중지 실패`);
        await apiCall("/api/stream/pipeline/pause", { method: "POST" });
      } else {
        // 파이프라인 먼저 재개 후 모든 카메라 시작 (병렬, 개별 실패 허용)
        await apiCall("/api/stream/pipeline/resume", { method: "POST" });
        const startResults = await Promise.allSettled(
          cameras.map((cam) =>
            apiCall(`/api/cameras/${cam.id}/start`, { method: "POST" })
          )
        );
        const startFailed = startResults.filter((r) => r.status === "rejected").length;
        if (startFailed > 0) console.warn(`${startFailed}개 카메라 시작 실패`);
      }

      setTimeout(() => {
        fetchCameras();
        setIsLoadingGlobal(false);
      }, 1000);
    } catch (error) {
      console.error("전역 카메라 제어 실패:", error);
      setIsLoadingGlobal(false);
    }
  }, [cameras, fetchCameras, isLoadingGlobal]);

  // Safe-zone 편집 핸들러
  const handleEditSafeZone = () => {
    setIsSafeZoneOpen(true);
  };

  // 카메라 설정 업데이트 (활성/비활성, 이름)
  const handleUpdateCamera = async (cameraId: string, updates: Partial<{ isActive: boolean; name: string }>) => {
    // 낙관적 업데이트
    setCameras(cameras.map(c => c.id === cameraId ? { ...c, ...updates } : c));

    try {
      // 1. 활성 상태 변경 (Start/Stop)
      if (typeof updates.isActive === "boolean") {
        const endpoint = updates.isActive ? "start" : "stop";
        await apiCall(`/api/cameras/${cameraId}/${endpoint}`, { method: "POST" });
      }

      // 2. 이름 변경 (POST - PATCH 405 이슈 회피)
      if (updates.name !== undefined) {
        await apiCall(`/api/cameras/${cameraId}/update`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: updates.name }),
        });
      }
    } catch (e) {
      console.error("카메라 업데이트 실패:", e);
      fetchCameras(); // 실패 시 롤백
    }
  };

  return (
    <>
      <div className="grid grid-cols-12 gap-4">
        {/* 메인 비디오 영역 */}
        {showMultiCamera ? (
          <div className="col-span-12 lg:col-span-8">
            {/* 전역 컨트롤 패널 */}
            <div className="flex gap-2 mb-4 p-3 rounded-lg border bg-card items-center flex-wrap">
              <Button
                variant="default"
                size="sm"
                onClick={handleGlobalStartStop}
                disabled={isLoadingGlobal}
              >
                {isLoadingGlobal ? "처리 중..." : (cameras.some((cam) => cam.isActive) ? "모든 카메라 중지" : "모든 카메라 시작")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleEditSafeZone}
              >
                Safe-zone 편집
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsCameraSettingsOpen(true)}
              >
                <Settings className="w-4 h-4 mr-1" />
                카메라 설정
              </Button>
              <Select
                value={globalStreamMode}
                onValueChange={(v) => setGlobalStreamMode(v as "mjpeg" | "webrtc")}
              >
                <SelectTrigger className="w-[140px] h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mjpeg">MJPEG</SelectItem>
                  <SelectItem value="webrtc">WebRTC</SelectItem>
                </SelectContent>
              </Select>
              <div className="ml-auto text-xs text-muted-foreground">
                {activeCameras.length}개 카메라 활성
              </div>
            </div>

            {isFocusMode && mainCamera ? (
              pipCameras.length === 1 ? (
                /* 2대 PIP: 좌우 6:4 비율 (PIP 1개일 때 자연스러운 배치) */
                <div className="flex gap-3 transition-all duration-500 ease-in-out">
                  <div className="flex-[6] transition-all duration-500">
                    <VideoFeed
                      cameraId={mainCamera.id}
                      cameraName={mainCamera.name}
                      hideButtons={false}
                      onClick={() => handleCameraClick(mainCamera.id)}
                      className={cn(
                        "cursor-pointer hover:ring-2 hover:ring-primary transition-all",
                        currentAlert !== "safe" && alertCameraId === mainCamera.id && "ring-4 ring-danger animate-border-flash"
                      )}
                    />
                  </div>
                  <div className="flex-[4] transition-all duration-500">
                    <VideoFeed
                      cameraId={pipCameras[0].id}
                      cameraName={pipCameras[0].name}
                      compact={true}
                      hideButtons={true}
                      onClick={() => handleCameraClick(pipCameras[0].id)}
                      className="cursor-pointer hover:ring-2 hover:ring-primary transition-all h-full hover:scale-[1.02]"
                    />
                  </div>
                </div>
              ) : (
                /* 3대+ PIP: 메인 7 + 우측 세로 스택 3 */
                <div className="flex gap-3 transition-all duration-500 ease-in-out">
                  <div className="flex-[7] transition-all duration-500">
                    <VideoFeed
                      cameraId={mainCamera.id}
                      cameraName={mainCamera.name}
                      hideButtons={false}
                      onClick={() => handleCameraClick(mainCamera.id)}
                      className={cn(
                        "cursor-pointer hover:ring-2 hover:ring-primary transition-all",
                        currentAlert !== "safe" && alertCameraId === mainCamera.id && "ring-4 ring-danger animate-border-flash"
                      )}
                    />
                  </div>
                  <div className="flex-[3] flex flex-col gap-2 transition-all duration-500">
                    {pipCameras.map((cam) => (
                      <div
                        key={cam.id}
                        className="flex-1 min-h-0 transition-all duration-300 hover:scale-105"
                      >
                        <VideoFeed
                          cameraId={cam.id}
                          cameraName={cam.name}
                          compact={true}
                          hideButtons={true}
                          onClick={() => handleCameraClick(cam.id)}
                          className="cursor-pointer hover:ring-2 hover:ring-primary transition-all h-full"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )
            ) : (
              <div className={cn(
                "transition-all duration-500",
                activeCameras.length === 2 ? "space-y-3" : "grid grid-cols-2 gap-3"
              )}>
                {activeCameras.map((cam) => (
                  <div
                    key={cam.id}
                    className="transition-all duration-300 hover:scale-[1.02]"
                  >
                    <VideoFeed
                      cameraId={cam.id}
                      cameraName={cam.name}
                      compact={activeCameras.length >= 3}
                      onClick={() => handleCameraClick(cam.id)}
                      className={cn(
                        "cursor-pointer hover:ring-2 hover:ring-primary transition-all",
                        currentAlert !== "safe" && alertCameraId === cam.id && "ring-4 ring-warning animate-border-flash"
                      )}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* 단일 카메라 모드 - VideoFeed 자체 시작/중지 버튼 사용 */
          <div className="col-span-12 lg:col-span-8">
            <VideoFeed />
          </div>
        )}

        <div className="col-span-12 lg:col-span-4 space-y-4">
          <StatusCard />
          <MetricsCard />
          <SettingsCard />
          <DemoVideoCard />
        </div>

        <div className="col-span-12">
          <EventLog />
        </div>
      </div>

      {/* Safe-zone 편집 모달 */}
      <Dialog open={isSafeZoneOpen} onOpenChange={setIsSafeZoneOpen}>
        <DialogContent className="max-w-4xl w-full">
          <DialogHeader>
            <DialogTitle>Safe-zone 편집</DialogTitle>
          </DialogHeader>
          <div className="mt-4 space-y-4">
            {/* 카메라 선택 탭 */}
            <div className="flex gap-2 border-b pb-2 overflow-x-auto">
              {cameras.map((cam) => (
                <Button
                  key={cam.id}
                  variant={selectedSafeZoneCamera === cam.id ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSelectedSafeZoneCamera(cam.id)}
                  className="whitespace-nowrap"
                >
                  <Camera className="w-3 h-3 mr-1" />
                  {cam.name}
                </Button>
              ))}
            </div>

            <SafeZoneEditor cameraId={selectedSafeZoneCamera} />
          </div>
        </DialogContent>
      </Dialog>

      {/* 카메라 설정 모달 */}
      <Dialog open={isCameraSettingsOpen} onOpenChange={setIsCameraSettingsOpen}>
        <DialogContent className="max-w-2xl w-full">
          <DialogHeader>
            <DialogTitle>카메라 관리</DialogTitle>
          </DialogHeader>
          <div className="mt-4 space-y-4">
            <div className="border rounded-md">
              <div className="grid grid-cols-12 gap-4 p-3 bg-muted/50 font-medium text-sm">
                <div className="col-span-3">미리보기</div>
                <div className="col-span-2">상태</div>
                <div className="col-span-2">ID</div>
                <div className="col-span-3">이름 (역할)</div>
                <div className="col-span-2">해상도</div>
              </div>
              <div className="divide-y">
                {cameras.map((cam) => (
                  <div key={cam.id} className="grid grid-cols-12 gap-4 p-3 items-center text-sm">
                    {/* 미리보기 컬럼 */}
                    <div className="col-span-3">
                      {cam.isActive ? (
                        <div className="relative aspect-video bg-black rounded overflow-hidden border">
                          <img
                            src={`/api/stream/mjpeg/${cam.id}`}
                            alt={`Camera ${cam.id}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      ) : (
                        <div className="aspect-video bg-muted rounded border flex items-center justify-center text-xs text-muted-foreground">
                          OFF
                        </div>
                      )}
                    </div>

                    <div className="col-span-2 flex items-center gap-2">
                      <Switch
                        checked={cam.isActive}
                        onCheckedChange={(checked) => handleUpdateCamera(cam.id, { isActive: checked })}
                      />
                      <span className={cn("text-xs", cam.isActive ? "text-green-500" : "text-muted-foreground")}>
                        {cam.isActive ? "ON" : "OFF"}
                      </span>
                    </div>
                    <div className="col-span-2 font-mono text-xs text-muted-foreground truncate" title={cam.id}>
                      {cam.id}
                    </div>
                    <div className="col-span-3">
                      <SimpleInput
                        value={cam.name}
                        onChange={(e) => handleUpdateCamera(cam.id, { name: e.target.value })}
                        placeholder="카메라 이름"
                        className="h-8 text-xs"
                      />
                    </div>
                    <div className="col-span-2 text-xs text-muted-foreground">
                      {cam.resolution || "N/A"}
                    </div>
                  </div>
                ))}
                {cameras.length === 0 && (
                  <div className="p-4 text-center text-muted-foreground">
                    연결된 카메라가 없습니다.
                  </div>
                )}
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => setIsCameraSettingsOpen(false)}>닫기</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
