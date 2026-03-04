import {
  Activity,
  Gauge,
  Users,
  AlertTriangle,
  CircleDot,
  Brain,
  BookOpen,
  Info,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMonitoringStore, type PersonMetrics } from "@/store/monitoring";
import { cn, formatPersonId } from "@/lib/utils";
import { useTranslation } from "react-i18next";

// 자세 색상: 낙상 여부에 따라 동적으로 결정
// lying은 낙상 시에만 빨간색, 평상시에는 중립 색상 (단순 누워있음 = 정상)
const getPostureColor = (posture: string, isFallen: boolean): string => {
  if (isFallen) return "text-danger";
  switch (posture) {
    case "standing": return "text-safe";
    case "sitting": return "text-blue-400";
    case "lying": return "text-amber-400";
    case "bending": return "text-warning";
    default: return "text-muted-foreground";
  }
};

const FALL_TYPE_COLORS: Record<string, string> = {
  normal: "text-safe",
  front_fall: "text-danger",
  back_fall: "text-danger",
  side_fall: "text-danger",
  pre_impact: "text-warning",
  unknown: "text-muted-foreground",
};

// 인물별 구분 색상 (바 + 아이콘)
const PERSON_COLORS = [
  "border-l-blue-400",
  "border-l-emerald-400",
  "border-l-violet-400",
  "border-l-amber-400",
  "border-l-rose-400",
  "border-l-cyan-400",
];

const PERSON_DOT_COLORS = [
  "text-blue-400",
  "text-emerald-400",
  "text-violet-400",
  "text-amber-400",
  "text-rose-400",
  "text-cyan-400",
];

function PersonCard({ person, index }: { person: PersonMetrics; index: number }) {
  const { t } = useTranslation();

  const getPostureLabel = (posture: string) => {
    const key = `dashboard.metrics.postures.${posture}` as const;
    return t(key);
  };

  const getFallTypeLabel = (fallType: string) => {
    const key = `dashboard.metrics.fallTypes.${fallType}` as const;
    return t(key);
  };

  const postureColor = getPostureColor(person.posture, person.isFallen);
  const fallTypeColor = FALL_TYPE_COLORS[person.fallType] ?? "text-muted-foreground";
  const borderColor = PERSON_COLORS[index % PERSON_COLORS.length];
  const dotColor = PERSON_DOT_COLORS[index % PERSON_DOT_COLORS.length];
  const isDanger = person.isFallen || person.fallConfidence > 0.5;
  const isWarning = !isDanger && person.fallConfidence > 0.3;

  return (
    <div
      className={cn(
        "rounded-lg border-l-4 p-3 transition-colors",
        borderColor,
        isDanger
          ? "bg-danger/5 border border-danger/15"
          : isWarning
            ? "bg-warning/5 border border-warning/15"
            : "bg-muted/30 border border-transparent",
      )}
    >
      {/* 헤더: ID + 상태 배지 */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <CircleDot className={cn("h-3.5 w-3.5", dotColor)} />
          <span className="text-sm font-bold">{t("events.person", "인원")} {formatPersonId(person.personId)}</span>
        </div>
        <div className="flex items-center gap-1.5">
          {person.isFallen && (
            <Badge variant="destructive" className="text-[10px] px-1.5 py-0 h-4">
              <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />
              {t("dashboard.metrics.fallen")}
            </Badge>
          )}
        </div>
      </div>

      {/* 상세 정보 2행 그리드 */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {/* 자세 */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">{t("dashboard.metrics.posture")}</span>
          <span className={cn("text-sm font-semibold", postureColor)}>
            {getPostureLabel(person.posture)}
          </span>
        </div>

        {/* 낙상 종류 */}
        <div className="flex justify-between items-center gap-2">
          <span className="text-xs text-muted-foreground">{t("dashboard.metrics.fallType")}</span>
          <Badge variant="outline" className={cn("text-xs px-2 py-0 h-5", fallTypeColor)}>
            {getFallTypeLabel(person.fallType)}
          </Badge>
        </div>

        {/* 낙상 확률 - 프로그레스 바 포함 */}
        <div className="col-span-2 mt-1">
          <div className="flex items-center justify-between mb-0.5">
            <span className="text-muted-foreground flex items-center gap-1">
              <Brain className="h-3 w-3" />
              {t("dashboard.metrics.fallProbability")}
            </span>
            <span className={cn(
              "font-mono font-bold text-xs",
              isDanger ? "text-danger" : isWarning ? "text-warning" : "text-safe",
            )}>
              {(person.fallConfidence * 100).toFixed(0)}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                isDanger ? "bg-danger" : isWarning ? "bg-warning" : "bg-safe",
              )}
              style={{ width: `${Math.min(person.fallConfidence * 100, 100)}%` }}
            />
          </div>
        </div>

        {/* 규칙/ML 점수 + 툴팁 */}
        <TooltipProvider delayDuration={300}>
          <div className="flex items-center justify-between">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground flex items-center gap-1 cursor-help">
                  <BookOpen className="h-3 w-3" />
                  {t("dashboard.metrics.rule")}
                  <Info className="h-2.5 w-2.5 opacity-50" />
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[200px] text-xs">
                {t("dashboard.metrics.ruleScoreTooltip")}
              </TooltipContent>
            </Tooltip>
            <span className="font-mono text-[11px]">
              {(person.ruleScore * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex items-center justify-between">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-muted-foreground flex items-center gap-1 cursor-help">
                  <Brain className="h-3 w-3" />
                  {t("dashboard.metrics.ml")}
                  <Info className="h-2.5 w-2.5 opacity-50" />
                </span>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-[200px] text-xs">
                {t("dashboard.metrics.mlScoreTooltip")}
              </TooltipContent>
            </Tooltip>
            <span className="font-mono text-[11px]">
              {(person.mlScore * 100).toFixed(0)}%
            </span>
          </div>
        </TooltipProvider>

        {/* 각도 + 지속시간 */}
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t("dashboard.metrics.angle")}</span>
          <span className={cn(
            "font-mono text-[11px]",
            person.angle > 45 && "text-warning",
          )}>
            {person.angle.toFixed(0)}°
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">{t("dashboard.metrics.duration")}</span>
          <span className="font-mono text-[11px]">
            {person.fallDuration > 0 ? `${person.fallDuration.toFixed(1)}s` : "-"}
          </span>
        </div>
      </div>
    </div>
  );
}

export function MetricsCard() {
  const { t } = useTranslation();
  const { personMetrics, roomCameraIds, perCameraFps, cameras, perCameraAlert } = useMonitoringStore();

  // 공간별 필터링: 선택된 공간의 카메라 인원만 표시
  const filteredPersons = roomCameraIds === null
    ? personMetrics
    : personMetrics.filter((p) =>
      roomCameraIds.some((c) => p.personId.startsWith(`${c}_`))
    );

  // 카메라별 그룹핑 (personId 형식: "cam0_person_1")
  const cameraGroups = new Map<string, PersonMetrics[]>();
  for (const person of filteredPersons) {
    const camId = person.personId.split("_person")[0] || "cam0";
    if (!cameraGroups.has(camId)) cameraGroups.set(camId, []);
    cameraGroups.get(camId)!.push(person);
  }
  // 카메라 이름 매핑
  const cameraNameMap = new Map(cameras.map((c) => [c.id, c.name]));

  // 카메라 ID 고정 순서: 활성 카메라 기준 + 공간 필터링 적용 (항상 같은 순서)
  const sortedCameraIds = cameras
    .filter((c) => c.isActive)
    .filter((c) => roomCameraIds === null || roomCameraIds.includes(c.id))
    .map((c) => c.id)
    .sort();

  // 공간별 FPS 집계: 해당 공간 카메라들의 평균 FPS
  const fpsEntries = roomCameraIds === null
    ? Object.values(perCameraFps)
    : roomCameraIds.map((c) => perCameraFps[c] ?? 0).filter((f) => f > 0);
  const avgFps = fpsEntries.length > 0
    ? fpsEntries.reduce((a, b) => a + b, 0) / fpsEntries.length
    : 0;


  return (
    <Card className="glass-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          {t("dashboard.metrics.realtime")}
          <div className="ml-auto flex items-center gap-2">
            {filteredPersons.length > 0 && (
              <Badge variant="secondary" className="text-xs">
                <Users className="h-3 w-3 mr-1" />
                {filteredPersons.length}{t("dashboard.units.people")}
              </Badge>
            )}
            <Badge variant="outline" className="text-xs font-mono">
              <Gauge className="h-3 w-3 mr-1" />
              {avgFps.toFixed(0)} FPS
            </Badge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0" aria-live="polite" aria-atomic="false">
        {/* 카메라별 고정 슬롯: 항상 같은 순서·같은 위치 */}
        {sortedCameraIds.length > 0 ? (
          <div className="divide-y divide-border/40">
            {sortedCameraIds.map((camId) => {
              const persons = cameraGroups.get(camId) || [];
              const alertLevel = perCameraAlert[camId] || "safe";
              const isMulti = sortedCameraIds.length > 1;
              return (
                <div
                  key={camId}
                  className={cn(
                    "px-4 py-3",
                    alertLevel === "danger" && "bg-danger/5",
                    alertLevel === "warning" && "bg-warning/5",
                  )}
                >
                  {/* 카메라 헤더 - 항상 표시 */}
                  {isMulti && (
                    <div className="flex items-center gap-2 mb-2">
                      <div className={cn(
                        "w-2 h-2 rounded-full",
                        alertLevel === "danger" ? "bg-danger animate-pulse" :
                          alertLevel === "warning" ? "bg-warning animate-pulse" :
                            "bg-safe",
                      )} />
                      <span className="text-xs font-semibold">
                        {cameraNameMap.get(camId) || camId}
                      </span>
                      {persons.length > 0 && (
                        <Badge variant="secondary" className="text-[10px] px-1 py-0 h-4">
                          {persons.length}{t("dashboard.units.people")}
                        </Badge>
                      )}
                      <span className="ml-auto text-[10px] font-mono text-muted-foreground">
                        {(perCameraFps[camId] ?? 0).toFixed(0)} fps
                      </span>
                    </div>
                  )}
                  {/* 인물 카드 또는 빈 상태 */}
                  {persons.length > 0 ? (
                    <div className="space-y-2">
                      {persons.map((person, idx) => (
                        <PersonCard key={person.personId} person={person} index={idx} />
                      ))}
                    </div>
                  ) : isMulti ? (
                    <div className="text-xs text-muted-foreground/40 py-1">
                      {t("dashboard.metrics.noPersons")}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-6 text-sm text-muted-foreground px-4">
            <Users className="h-8 w-8 mx-auto mb-2 opacity-30" />
            {t("dashboard.metrics.noPersons")}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
