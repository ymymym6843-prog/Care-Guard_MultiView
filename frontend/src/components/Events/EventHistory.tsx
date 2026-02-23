/**
 * DB 기반 이벤트 조회
 *
 * mode="alerts" : 알림 이벤트 (미확인 기본, 일괄 확인)
 * mode="history" : 이벤트 기록 (전체 이력, 내보내기 중심)
 */

import { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  CheckCircle,
  RefreshCcw,
  ChevronLeft,
  ChevronRight,
  Download,
  Camera,
  Bell,
  CheckCheck,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn, formatPersonId } from "@/lib/utils";
import { apiCall } from "@/lib/auth";
import { useMonitoringStore } from "@/store/monitoring";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

interface DBEvent {
  id: number;
  timestamp: string;
  alert_level: string;
  duration: number;
  camera_id: string | null;
  person_id: string | null;
  confidence: number;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
  room_id: number | null;
}

interface EventHistoryProps {
  mode?: "alerts" | "history";
}

const levelIcons: Record<string, typeof ShieldCheck> = {
  safe: ShieldCheck,
  warning: AlertTriangle,
  danger: ShieldAlert,
};

const levelColors: Record<string, string> = {
  safe: "text-safe",
  warning: "text-warning",
  danger: "text-danger",
};

/** Confidence color bar: high = danger, mid = warning, low = safe */
function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.min(value * 100, 100);
  const barColor =
    pct >= 80 ? "bg-danger" : pct >= 60 ? "bg-warning" : "bg-safe";
  return (
    <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden shrink-0">
      <div
        className={cn("h-full rounded-full transition-all", barColor)}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function EventHistory({ mode = "history" }: EventHistoryProps) {
  const { t, i18n } = useTranslation();
  const { selectedRoomId, cameras } = useMonitoringStore();
  const [events, setEvents] = useState<DBEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string | null>(null);
  const [ackFilter, setAckFilter] = useState<boolean | null>(
    mode === "alerts" ? false : null,
  );
  const pageSize = 20;

  const isAlerts = mode === "alerts";
  const cameraNameMap = new Map(cameras.map((c) => [c.id, c.name]));

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("size", String(pageSize));
      if (levelFilter) params.set("level", levelFilter);
      if (ackFilter !== null) params.set("acknowledged", String(ackFilter));
      if (selectedRoomId !== null) params.set("room_id", String(selectedRoomId));

      const res = await apiCall(`/api/events?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setEvents(data.items);
        setTotal(data.total);
        setPages(data.pages);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page, levelFilter, ackFilter, selectedRoomId]);

  useEffect(() => {
    setPage(1);
  }, [levelFilter, ackFilter, selectedRoomId]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handleAcknowledge = async (eventId: number) => {
    try {
      const res = await apiCall(`/api/events/${eventId}/acknowledge`, {
        method: "POST",
      });
      if (res.ok) {
        toast.success(t("events.acknowledged", "이벤트가 확인되었습니다."));
        fetchEvents();
      }
    } catch {
      toast.error(t("events.acknowledgeError", "확인 처리에 실패했습니다."));
    }
  };

  const handleBatchAcknowledge = async () => {
    try {
      const params = new URLSearchParams();
      if (selectedRoomId !== null) params.set("room_id", String(selectedRoomId));

      const res = await apiCall(`/api/events/batch-acknowledge?${params.toString()}`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(
          t("events.batchAcknowledged", {
            count: data.count,
            defaultValue: "{{count}}건 이벤트가 확인되었습니다.",
          }),
        );
        fetchEvents();
      }
    } catch {
      toast.error(t("events.acknowledgeError", "확인 처리에 실패했습니다."));
    }
  };

  const handleExport = async (format: "csv" | "xlsx") => {
    try {
      const params = new URLSearchParams();
      params.set("format", format);
      params.set("days", "365");
      if (selectedRoomId !== null) params.set("room_id", String(selectedRoomId));
      if (levelFilter) params.set("level", levelFilter);

      const res = await apiCall(`/api/events/export?${params.toString()}`);
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `events.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        toast.success(t("events.exportSuccess", { format: format.toUpperCase() }));
      }
    } catch {
      toast.error(t("events.exportError", "내보내기에 실패했습니다."));
    }
  };

  const formatTimestamp = (ts: string) => {
    const d = new Date(ts);
    return d.toLocaleString(i18n.language === "ko" ? "ko-KR" : "en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  };

  const selectedRoom = useMonitoringStore((s) =>
    s.rooms.find((r) => r.id === s.selectedRoomId),
  );

  // 미확인 이벤트 수 (알림 모드에서 표시)
  const unacknowledgedCount = isAlerts && ackFilter === false ? total : 0;

  const title = isAlerts
    ? t("events.alertsTitle", "알림 이벤트")
    : t("events.title", "이벤트 기록");

  const subtitle = selectedRoom
    ? isAlerts
      ? t("events.alertsSubtitleRoom", {
          room: selectedRoom.name,
          total,
          defaultValue: "{{room}} 미확인 알림 {{total}}건",
        })
      : t("events.subtitleRoom", { room: selectedRoom.name, total })
    : isAlerts
      ? t("events.alertsSubtitleAll", {
          total,
          defaultValue: "전체 공간 미확인 알림 {{total}}건",
        })
      : t("events.subtitleAll", { total });

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          {isAlerts && (
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-warning/10">
              <Bell className="h-5 w-5 text-warning" />
            </div>
          )}
          <div>
            <h2 className="text-xl font-semibold">{title}</h2>
            <p className="text-sm text-muted-foreground">{subtitle}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isAlerts && total > 0 && (
            <Button size="sm" variant="default" onClick={handleBatchAcknowledge}>
              <CheckCheck className="h-3.5 w-3.5 mr-1" />
              {t("events.batchAcknowledge", "모두 확인")}
            </Button>
          )}
          {!isAlerts && (
            <Button size="sm" variant="outline" onClick={() => handleExport("csv")}>
              <Download className="h-3.5 w-3.5 mr-1" />
              CSV
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={fetchEvents}>
            <RefreshCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* 필터 - 그룹 구분 (1-4) */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* 위험도 필터 그룹 */}
        <span className="text-xs font-medium text-muted-foreground">
          {t("events.filterLevel", "위험도")}:
        </span>
        {[
          { key: null, label: t("events.filterAll", "전체") },
          { key: "danger", label: t("dashboard.status.danger", "위험") },
          { key: "warning", label: t("dashboard.status.warning", "주의") },
        ].map((f) => (
          <Button
            key={f.key ?? "all"}
            size="sm"
            variant={levelFilter === f.key ? "default" : "outline"}
            onClick={() => setLevelFilter(f.key)}
            className="h-7 text-xs"
          >
            {f.label}
          </Button>
        ))}

        <div className="w-px h-5 bg-border mx-1" />

        {/* 상태 필터 그룹 */}
        <span className="text-xs font-medium text-muted-foreground">
          {t("events.filterStatus", "상태")}:
        </span>
        {[
          { key: null, label: t("events.ackAll", "전체") },
          { key: false, label: t("events.unacknowledged", "미확인") },
          { key: true, label: t("events.acknowledgedLabel", "확인됨") },
        ].map((f) => (
          <Button
            key={String(f.key)}
            size="sm"
            variant={ackFilter === f.key ? "default" : "outline"}
            onClick={() => setAckFilter(f.key)}
            className="h-7 text-xs"
          >
            {f.label}
            {isAlerts && f.key === false && unacknowledgedCount > 0 && (
              <Badge
                variant="destructive"
                className="ml-1 text-[9px] px-1 py-0 h-4 min-w-[18px] justify-center"
              >
                {unacknowledgedCount}
              </Badge>
            )}
          </Button>
        ))}
      </div>

      {/* 이벤트 목록 */}
      <Card>
        <CardContent className="p-0">
          <ScrollArea className="max-h-[calc(100vh-300px)]">
            {loading && events.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
                {t("common.loading", "로딩 중...")}
              </div>
            ) : events.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-muted-foreground text-sm">
                {isAlerts ? (
                  <>
                    <CheckCircle className="h-8 w-8 mb-2 opacity-30 text-safe" />
                    {t("events.noAlerts", "미확인 알림이 없습니다.")}
                  </>
                ) : (
                  <>
                    <ShieldCheck className="h-8 w-8 mb-2 opacity-30" />
                    {t("events.noEvents", "이벤트가 없습니다.")}
                  </>
                )}
              </div>
            ) : (
              <div className="divide-y divide-border">
                {events.map((event) => {
                  const Icon = levelIcons[event.alert_level] ?? ShieldCheck;
                  const color = levelColors[event.alert_level] ?? "text-muted-foreground";
                  const camName = event.camera_id
                    ? cameraNameMap.get(event.camera_id) || event.camera_id
                    : null;

                  return (
                    <div
                      key={event.id}
                      className={cn(
                        "flex items-center gap-3 px-4 py-3 text-sm hover:bg-muted/30 transition-colors",
                        event.alert_level === "danger" && !event.acknowledged && "bg-danger/5",
                      )}
                    >
                      <Icon className={cn("h-4 w-4 shrink-0", color)} />

                      <time className="text-xs text-muted-foreground font-mono tabular-nums shrink-0 w-32">
                        {formatTimestamp(event.timestamp)}
                      </time>

                      <Badge
                        variant={event.alert_level === "danger" ? "destructive" : "outline"}
                        className="text-[10px] px-1.5 py-0 h-5 shrink-0"
                      >
                        {event.alert_level === "danger"
                          ? t("dashboard.status.danger")
                          : t("dashboard.status.warning")}
                      </Badge>

                      {camName && (
                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-5 shrink-0">
                          <Camera className="h-2.5 w-2.5 mr-0.5" />
                          {camName}
                        </Badge>
                      )}

                      {/* 1-2: Person ID 친화적 표시 */}
                      {event.person_id && (
                        <span className="text-xs text-muted-foreground shrink-0">
                          {t("events.person")} {formatPersonId(event.person_id)}
                        </span>
                      )}

                      {/* 1-1: 신뢰도 레이블 + 값 + 1-3: 컬러바 */}
                      {event.confidence > 0 && (
                        <span className="flex items-center gap-1.5 shrink-0">
                          <span className="text-[10px] text-muted-foreground">
                            {t("events.confidence")}
                          </span>
                          <span className="text-xs font-mono text-muted-foreground">
                            {(event.confidence * 100).toFixed(0)}%
                          </span>
                          <ConfidenceBar value={event.confidence} />
                        </span>
                      )}

                      {/* 1-1: 응답 시간 레이블 */}
                      {event.duration > 0 && (
                        <span className="flex items-center gap-1 shrink-0">
                          <span className="text-[10px] text-muted-foreground">
                            {t("events.responseTime")}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {event.duration.toFixed(1)}s
                          </span>
                        </span>
                      )}

                      <div className="flex-1" />

                      {/* 1-5: 확인 상태 차별화 */}
                      {event.acknowledged ? (
                        <span className="flex items-center gap-1 text-[10px] text-muted-foreground shrink-0">
                          <CheckCircle className="h-3 w-3 text-safe" />
                          <span className="text-safe/70">
                            {event.acknowledged_by ?? t("events.acknowledgedLabel", "확인됨")}
                          </span>
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant={isAlerts ? "default" : "outline"}
                          className={cn(
                            "h-6 text-[10px] px-2 shrink-0",
                            isAlerts && "bg-warning hover:bg-warning/90 text-warning-foreground",
                          )}
                          onClick={() => handleAcknowledge(event.id)}
                        >
                          {t("events.acknowledge", "확인")}
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* 페이지네이션 */}
      {pages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground font-mono">
            {page} / {pages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
