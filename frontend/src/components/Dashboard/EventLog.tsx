import {
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { cn, formatPersonId } from "@/lib/utils";
import { useMonitoringStore, type AlertLevel } from "@/store/monitoring";
import { useTranslation } from "react-i18next";

const levelConfigStatic: Record<
  AlertLevel,
  { icon: typeof ShieldCheck; color: string }
> = {
  safe: { icon: ShieldCheck, color: "text-safe" },
  warning: { icon: AlertTriangle, color: "text-warning" },
  danger: { icon: ShieldAlert, color: "text-danger" },
};

export function EventLog() {
  const { t, i18n } = useTranslation();
  const { eventLog, clearEventLog, roomCameraIds } = useMonitoringStore();

  // 공간 필터링: roomCameraIds가 null이면 전체, 아니면 해당 카메라 이벤트만
  const filteredEventLog = roomCameraIds === null
    ? eventLog
    : eventLog.filter((e) => !e.cameraId || roomCameraIds.includes(e.cameraId));

  const levelConfig: Record<AlertLevel, { icon: typeof ShieldCheck; color: string; label: string }> = {
    safe: {
      ...levelConfigStatic.safe,
      label: t("dashboard.status.safe"),
    },
    warning: {
      ...levelConfigStatic.warning,
      label: t("dashboard.status.warning"),
    },
    danger: {
      ...levelConfigStatic.danger,
      label: t("dashboard.status.danger"),
    },
  };

  const getFallTypeShort = (fallType: string) => {
    const key = `dashboard.metrics.fallTypesShort.${fallType}` as const;
    return t(key);
  };

  return (
    <Card>
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium">{t("dashboard.eventLog.title")}</CardTitle>
        {filteredEventLog.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearEventLog}
            className="h-7 text-xs text-muted-foreground"
          >
            <Trash2 className="h-3 w-3 mr-1" />
            {t("dashboard.eventLog.clear")}
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-48">
          {filteredEventLog.length === 0 ? (
            <div className="flex items-center justify-center h-full py-8">
              <p className="text-sm text-muted-foreground">
                {t("dashboard.eventLog.noEvents")}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-border" aria-live="polite">
              {filteredEventLog.map((entry) => {
                const config = levelConfig[entry.level];
                const Icon = config.icon;
                const fallLabel = entry.fallType ? getFallTypeShort(entry.fallType) : null;
                return (
                  <div
                    key={entry.id}
                    className={cn(
                      "flex items-center gap-3 px-4 py-2.5 text-sm",
                      entry.level === "danger" && "bg-danger/5",
                    )}
                  >
                    <Icon
                      className={cn("h-4 w-4 shrink-0", config.color)}
                      aria-hidden="true"
                    />
                    <span className="sr-only">{config.label}</span>
                    <time className="text-xs text-muted-foreground font-mono tabular-nums shrink-0">
                      {entry.timestamp.toLocaleTimeString(i18n.language === "ko" ? "ko-KR" : "en-US", {
                        hour12: false,
                      })}
                    </time>
                    {entry.personId && (
                      <Badge
                        variant="outline"
                        className={cn(
                          "text-[10px] px-1.5 py-0 h-4 shrink-0",
                          entry.level === "danger" ? "text-danger border-danger/30"
                            : entry.level === "warning" ? "text-warning border-warning/30"
                              : "text-muted-foreground",
                        )}
                      >
                        {t("events.person", "인원")} {formatPersonId(entry.personId)}
                      </Badge>
                    )}
                    {fallLabel && (
                      <Badge
                        variant="secondary"
                        className="text-[10px] px-1 py-0 h-4 shrink-0"
                      >
                        {fallLabel}
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground shrink-0">
                      [{entry.category}]
                    </span>
                    <span className="truncate">{entry.message}</span>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
