import {
  ShieldCheck,
  AlertTriangle,
  ShieldAlert,
  Users,
  Clock,
  UserRound,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatPersonId } from "@/lib/utils";
import { useMonitoringStore, type AlertLevel } from "@/store/monitoring";
import { useTranslation } from "react-i18next";
import { Camera } from "lucide-react";

const alertConfigStatic: Record<
  AlertLevel,
  {
    icon: typeof ShieldCheck;
    bgClass: string;
    textClass: string;
    borderClass: string;
  }
> = {
  safe: {
    icon: ShieldCheck,
    bgClass: "bg-safe/10",
    textClass: "text-safe",
    borderClass: "border-safe/30",
  },
  warning: {
    icon: AlertTriangle,
    bgClass: "bg-warning/10",
    textClass: "text-warning",
    borderClass: "border-warning/30",
  },
  danger: {
    icon: ShieldAlert,
    bgClass: "bg-danger/10",
    textClass: "text-danger",
    borderClass: "border-danger/30 animate-border-flash",
  },
};

export function StatusCard() {
  const { t } = useTranslation();
  const { currentAlert, currentFallType, metrics: _metrics, alertDuration, isCameraActive, personMetrics, roomCameraIds, cameras } =
    useMonitoringStore();

  const alertConfig: Record<AlertLevel, { icon: typeof ShieldCheck; label: string; description: string; bgClass: string; textClass: string; borderClass: string }> = {
    safe: {
      ...alertConfigStatic.safe,
      label: t("dashboard.status.safe"),
      description: t("dashboard.status.safeDesc"),
    },
    warning: {
      ...alertConfigStatic.warning,
      label: t("dashboard.status.warning"),
      description: t("dashboard.status.warningDesc"),
    },
    danger: {
      ...alertConfigStatic.danger,
      label: t("dashboard.status.danger"),
      description: t("dashboard.status.dangerDesc"),
    },
  };

  const config = alertConfig[currentAlert];
  const Icon = config.icon;

  const getFallTypeLabel = (fallType: string) => {
    const key = `dashboard.metrics.fallTypes.${fallType}` as const;
    return fallType && fallType !== "normal" && fallType !== "unknown" ? t(key) : "";
  };

  const getPostureLabel = (posture: string) => {
    const key = `dashboard.metrics.postures.${posture}` as const;
    return t(key);
  };

  // 공간별 필터링: 선택된 공간의 카메라 인원만 대상
  const filteredPersons = roomCameraIds === null
    ? personMetrics
    : personMetrics.filter((p) =>
        roomCameraIds.some((c) => p.personId.startsWith(`${c}_`))
      );

  // 가장 위험한 인물 찾기
  const dangerPerson = filteredPersons.length > 0
    ? filteredPersons.reduce((max, p) =>
      p.fallConfidence > max.fallConfidence ? p : max,
    )
    : null;

  // 인물 수준 위험 감지: 글로벌 알림과 무관하게 즉시 표시
  const showTriggerPerson = dangerPerson != null && (
    dangerPerson.isFallen ||
    dangerPerson.fallConfidence > 0.3 ||
    currentAlert !== "safe"
  );

  // 인물 수준 위험도에 따른 동적 스타일
  const effectiveAlert: AlertLevel = dangerPerson?.isFallen
    ? "danger"
    : dangerPerson && dangerPerson.fallConfidence > 0.5
      ? "warning"
      : currentAlert;
  const triggerConfig = alertConfig[effectiveAlert];

  const fallTypeLabel = getFallTypeLabel(currentFallType) || getFallTypeLabel(dangerPerson?.fallType ?? "");

  // 알림 발생 카메라 이름 추출
  const cameraNameMap = new Map(cameras.map((c) => [c.id, c.name]));
  const dangerCamId = dangerPerson?.personId.split("_person")[0] ?? null;
  const dangerCamName = dangerCamId ? (cameraNameMap.get(dangerCamId) || dangerCamId) : null;

  return (
    <Card
      className={cn(
        "glass-card border-none transition-all duration-500 overflow-hidden relative",
        currentAlert === "danger" && "ring-2 ring-danger animate-danger-pulse bg-danger/10",
        currentAlert === "warning" && "ring-1 ring-warning bg-warning/5",
        currentAlert === "safe" && "bg-safe/5"
      )}
    >
      {/* 배경 장식 */}
      <div className={cn(
        "absolute -right-10 -top-10 w-40 h-40 rounded-full blur-3xl opacity-20 pointer-events-none",
        config.bgClass.replace("/10", "/30")
      )} />
      <CardContent className="p-5">
        {/* 상태 아이콘 + 텍스트 */}
        <div
          className="flex items-center gap-4 mb-3"
          role="status"
          aria-live="assertive"
          aria-atomic="true"
        >
          <div
            className={cn("p-3 rounded-xl", config.bgClass)}
            aria-hidden="true"
          >
            <Icon className={cn("h-8 w-8", config.textClass)} />
          </div>
          <div className="flex-1">
            <p
              className={cn(
                "text-3xl font-extrabold leading-none",
                config.textClass,
              )}
            >
              {config.label}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {config.description}
            </p>
            {currentAlert === "danger" && (
              <p className="text-xs font-semibold text-danger mt-1 animate-pulse">
                {t("dashboard.status.dangerAction")}
              </p>
            )}
          </div>
        </div>

        {/* 트리거 인물 정보 (인물 수준 위험 감지 시 즉시 표시) */}
        {showTriggerPerson && dangerPerson ? (
          <div className={cn(
            "mb-3 p-3 rounded-lg border",
            effectiveAlert === "danger"
              ? "bg-danger/5 border-danger/20"
              : effectiveAlert === "warning"
                ? "bg-warning/5 border-warning/20"
                : "bg-muted/50 border-muted-foreground/20",
          )}>
            <div className="flex items-center gap-2 mb-1.5">
              <UserRound className={cn("h-4 w-4", triggerConfig.textClass)} />
              <span className={cn("text-sm font-bold", triggerConfig.textClass)}>
                {t("events.person", "인원")} {formatPersonId(dangerPerson.personId)}
              </span>
              {dangerCamName && (
                <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4">
                  <Camera className="h-2.5 w-2.5 mr-0.5" />
                  {dangerCamName}
                </Badge>
              )}
              {fallTypeLabel && (
                <Badge
                  variant="outline"
                  className={cn("text-[10px] px-1.5 py-0", triggerConfig.textClass, triggerConfig.borderClass)}
                >
                  {fallTypeLabel}
                </Badge>
              )}
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t("dashboard.metrics.posture")}</span>
                <span className="font-medium">
                  {getPostureLabel(dangerPerson.posture)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t("dashboard.metrics.confidence")}</span>
                <span className={cn(
                  "font-mono font-bold",
                  dangerPerson.fallConfidence > 0.5 ? "text-danger" : "text-warning",
                )}>
                  {(dangerPerson.fallConfidence * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t("dashboard.metrics.angle")}</span>
                <span className="font-mono">{dangerPerson.angle.toFixed(0)}°</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t("dashboard.metrics.duration")}</span>
                <span className="font-mono">
                  {dangerPerson.fallDuration > 0 ? `${dangerPerson.fallDuration.toFixed(1)}s` : "-"}
                </span>
              </div>
            </div>
          </div>
        ) : null}

        {/* 보조 정보 */}
        <div className="grid grid-cols-2 gap-3" aria-live="polite">
          <div className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-muted-foreground">{t("dashboard.status.totalPersons")}:</span>
            <span className="font-semibold">{filteredPersons.length}{t("dashboard.units.people")}</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Clock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <span className="text-muted-foreground">{t("dashboard.units.duration")}:</span>
            <span className="font-semibold font-mono">
              {alertDuration > 0 ? `${alertDuration}${t("dashboard.units.seconds")}` : "-"}
            </span>
          </div>
        </div>

        {/* 카메라 상태 */}
        {!isCameraActive && (
          <p className="text-xs text-muted-foreground mt-3 text-center">
            {t("dashboard.video.cameraInactive")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
