import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
  Film,
  Play,
  Square,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  User,
  ArrowDown,
  ArrowLeft,
  Loader2,
  Star,
  List,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { apiCall } from "@/lib/auth";
import { useMonitoringStore } from "@/store/monitoring";

interface DemoVideo {
  filename: string;
  path: string;
  category: string;
  size_mb: number;
}

interface DemoStatus {
  demo_mode: boolean;
  current_source: string;
  is_active: boolean;
  available: boolean;
}



export function DemoVideoCard() {
  const { t, i18n } = useTranslation();
  const [videos, setVideos] = useState<DemoVideo[]>([]);
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedPath, setSelectedPath] = useState("");
  const { setCameraActive, setCurrentAlert, setCurrentFallType, addEventLog, clearAlerts, settings } = useMonitoringStore();

  // 데모 시나리오 타임라인 정의 (초 단위)
  const scenarios: Record<string, { type: string; events: { time: number; action: () => void }[] }> = useMemo(() => ({
    "front_fall": {
      type: "front_fall",
      events: [
        { time: 2, action: () => { setCurrentAlert("warning"); toast.warning(t("dashboard.demo.alerts.warning")); } },
        {
          time: 4, action: () => {
            setCurrentAlert("danger");
            setCurrentFallType("front_fall");
            toast.error(t("dashboard.demo.alerts.danger") + " (Demo)");
            addEventLog("danger", "front_fall", t("dashboard.demo.alerts.danger") + " (Demo)", "person_demo");
            if (settings.ttsEnabled) {
              const msg = new SpeechSynthesisUtterance(t("dashboard.demo.alerts.ttsDanger"));
              msg.lang = i18n.language === "ko" ? "ko-KR" : "en-US";
              window.speechSynthesis.speak(msg);
            }
          }
        }
      ]
    },
    "pre_impact": {
      type: "pre_impact",
      events: [
        {
          time: 2, action: () => {
            setCurrentAlert("warning");
            setCurrentFallType("pre_impact");
            toast.warning(t("dashboard.demo.alerts.preImpact") + " (Demo)");
            addEventLog("warning", "pre_impact", t("dashboard.demo.alerts.preImpact") + " (Demo)", "person_demo");
          }
        }
      ]
    },
    "normal": {
      type: "normal",
      events: [
        { time: 1, action: () => { clearAlerts(); } }
      ]
    }
  }), [t, i18n, setCurrentAlert, setCurrentFallType, addEventLog, clearAlerts, settings]);

  // 비디오 시간 모니터링
  useEffect(() => {
    if (!status?.demo_mode || !selectedPath) return;

    // 현재 재생 중인 비디오 카테고리 찾기
    const currentVideo = videos.find(v => v.path === selectedPath);
    if (!currentVideo) return;

    // 카테고리에 맞는 시나리오 가져오기
    // 파일명이나 카테고리로 매핑 (여기서는 카테고리 기반)
    // 예: category가 "front_fall"이면 해당 시나리오 적용
    const scenario = scenarios[currentVideo.category];
    if (!scenario) return;

    // 비디오 엘리먼트 찾기 (VideoFeed 컴포넌트 내부에 있어서 직접 제어는 어려움)
    // 대안: VideoFeed에서 onTimeUpdate를 받을 수 없으므로,
    // DemoVideoCard 안에서 '가상 타이머'를 돌리거나,
    // 백엔드에서 스트리밍되는 영상이라 클라이언트 시간 동기화가 어려움.

    // **수정 전략**:
    // 1. 데모 영상 선택 시, '시작 시간'을 기록.
    // 2. setInterval로 경과 시간을 체크하여 이벤트 트리거.
    // 3. 영상이 루프되거나 멈추는 경우 오차가 있을 수 있지만, 데모 목적상 충분함.

    const startTime = Date.now();
    const processedEvents = new Set<number>();

    const timer = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;

      scenario.events.forEach((event, index) => {
        if (!processedEvents.has(index) && elapsed >= event.time) {
          event.action();
          processedEvents.add(index);
        }
      });
    }, 500);

    return () => clearInterval(timer);
  }, [status?.demo_mode, selectedPath, videos, scenarios]);


  const categoryConfig: Record<string, { label: string; icon: any; color: string }> = useMemo(() => ({
    front_fall: { label: t("dashboard.demo.categories.front_fall"), icon: ArrowDown, color: "text-red-500" },
    back_fall: { label: t("dashboard.demo.categories.back_fall"), icon: ArrowDown, color: "text-orange-500" },
    side_fall: { label: t("dashboard.demo.categories.side_fall"), icon: ArrowLeft, color: "text-yellow-500" },
    normal: { label: t("dashboard.demo.categories.normal"), icon: User, color: "text-green-500" },
    pre_impact: { label: t("dashboard.demo.categories.pre_impact"), icon: AlertTriangle, color: "text-purple-500" },
  }), [t]);

  // 데모 상태 확인
  const fetchStatus = useCallback(async () => {
    try {
      const res = await apiCall("/api/demo");
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch {
      // 데모 API 없으면 무시
    }
  }, []);

  // 데모 영상 목록 로드
  const fetchVideos = useCallback(async () => {
    try {
      const res = await apiCall("/api/demo/videos");
      if (res.ok) {
        const data = await res.json();
        setVideos(data.videos || []);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (expanded && videos.length === 0) {
      fetchVideos();
    }
  }, [expanded, videos.length, fetchVideos]);

  // 영상 선택 및 재생
  const handleSelect = useCallback(
    async (path: string) => {
      setLoading(true);
      setSelectedPath(path);
      try {
        const res = await apiCall("/api/demo/select", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path }),
        });
        if (res.ok) {
          setCameraActive(true);
          await fetchStatus();
        }
      } catch (error) {
        console.error("데모 영상 선택 실패:", error);
      } finally {
        setLoading(false);
      }
    },
    [setCameraActive, fetchStatus],
  );

  // 데모 중지
  const handleStop = useCallback(async () => {
    try {
      await apiCall("/api/demo/stop", { method: "POST" });
      setCameraActive(false);
      setSelectedPath("");
      await fetchStatus();
    } catch (error) {
      console.error("데모 중지 실패:", error);
    }
  }, [setCameraActive, fetchStatus]);

  // 데모 비활성화면 렌더링 안함
  if (status && !status.available) return null;

  // 추천 영상 (정확도 최상위)
  const RECOMMENDED = new Set([
    "BY_hospital_back_C1.mp4",
    "FY_hospital_front_C1.mp4",
    "SY_hospital_side_C1.mp4",
    "N_normal_sideview_01.mp4",
  ]);

  // "기타"(unknown) 카테고리 제외 (AI 생성 영상으로 정확도 낮음)
  const filteredVideos = videos.filter(v => v.category !== "unknown");
  const displayVideos = showAll ? filteredVideos : filteredVideos.filter(v => RECOMMENDED.has(v.filename));

  // 카테고리별 그룹화
  const grouped = displayVideos.reduce(
    (acc, v) => {
      const cat = v.category;
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(v);
      return acc;
    },
    {} as Record<string, DemoVideo[]>,
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Film className="h-4 w-4 text-primary" />
            <span>{t("dashboard.demo.title")}</span>
            {status?.demo_mode && (
              <Badge variant="default" className="bg-purple-500 text-white text-xs">
                DEMO
              </Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-1">
            {status?.demo_mode && (
              <Button size="sm" variant="destructive" onClick={handleStop}>
                <Square className="h-3 w-3 mr-1" />
                {t("dashboard.demo.stop")}
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-3 pt-0">
          {videos.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-2">
              {t("dashboard.demo.envWarning")}
            </p>
          ) : (
            <>
              {Object.entries(grouped).map(([category, catVideos]) => {
                const config = categoryConfig[category as keyof typeof categoryConfig] || categoryConfig["unknown"];
                if (!config) return null;
                const Icon = config.icon;
                return (
                  <div key={category} className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <Icon className={cn("h-3 w-3", config.color)} />
                      <span className="text-xs font-medium text-muted-foreground">
                        {config.label}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 gap-1">
                      {catVideos.map((v) => {
                        const isPlaying =
                          status?.demo_mode && status.current_source === v.path;
                        const isLoading = loading && selectedPath === v.path;
                        return (
                          <button
                            key={v.path}
                            onClick={() => handleSelect(v.path)}
                            disabled={isLoading}
                            className={cn(
                              "flex items-center justify-between px-2.5 py-1.5 rounded-md text-xs",
                              "border transition-colors hover:bg-accent",
                              isPlaying
                                ? "border-primary bg-primary/10"
                                : "border-border",
                            )}
                          >
                            <span className="truncate max-w-[160px]">
                              {v.filename}
                            </span>
                            <span className="flex items-center gap-1.5 text-muted-foreground shrink-0">
                              <span>{v.size_mb}MB</span>
                              {isLoading ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : isPlaying ? (
                                <Badge
                                  variant="default"
                                  className="bg-primary text-[10px] px-1 py-0"
                                >
                                  {t("dashboard.demo.playing")}
                                </Badge>
                              ) : (
                                <Play className="h-3 w-3" />
                              )}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <button
                onClick={() => setShowAll(!showAll)}
                className="flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors w-full justify-center pt-1"
              >
                {showAll ? (
                  <><Star className="h-3 w-3" />{t("dashboard.demo.showRecommended")}</>
                ) : (
                  <><List className="h-3 w-3" />{t("dashboard.demo.showAll")} ({filteredVideos.length})</>
                )}
              </button>
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}
