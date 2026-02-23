import { useEffect, useRef } from "react";
import { ShieldAlert, Camera, UserRound } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useMonitoringStore } from "@/store/monitoring";
import { useTranslation } from "react-i18next";
import { formatPersonId } from "@/lib/utils";

interface DangerAlertDialogProps {
  onAcknowledge?: () => void;
}

export function DangerAlertDialog({ onAcknowledge }: DangerAlertDialogProps) {
  const { t, i18n } = useTranslation();
  const { currentAlert, alertDuration, personMetrics, cameras } = useMonitoringStore();
  const acknowledgeButtonRef = useRef<HTMLButtonElement>(null);

  const isOpen = currentAlert === "danger";

  // 가장 위험한 인물 정보 추출
  const dangerPerson = personMetrics.length > 0
    ? personMetrics.reduce((max, p) => p.fallConfidence > max.fallConfidence ? p : max)
    : null;
  const cameraNameMap = new Map(cameras.map((c) => [c.id, c.name]));
  const dangerCamId = dangerPerson?.personId.split("_person")[0] ?? null;
  const dangerCamName = dangerCamId ? (cameraNameMap.get(dangerCamId) || dangerCamId) : null;

  // 모달 열릴 때 자동 포커스
  useEffect(() => {
    if (isOpen && acknowledgeButtonRef.current) {
      acknowledgeButtonRef.current.focus();
    }
  }, [isOpen]);

  const handleAcknowledge = () => {
    onAcknowledge?.();
  };

  return (
    <AlertDialog open={isOpen}>
      <AlertDialogContent
        className="border-2 border-danger bg-card max-w-md"
        role="alertdialog"
        aria-labelledby="danger-alert-title"
        aria-describedby="danger-alert-desc"
      >
        <AlertDialogHeader className="text-center">
          <div className="mx-auto mb-4" aria-hidden="true">
            <ShieldAlert className="h-20 w-20 text-danger animate-danger-pulse" />
          </div>
          <AlertDialogTitle
            id="danger-alert-title"
            className="text-4xl text-danger text-center"
          >
            {t("dashboard.dangerAlert.title")}
          </AlertDialogTitle>
          <AlertDialogDescription
            id="danger-alert-desc"
            className="text-center space-y-2 text-base"
          >
            <p>{t("dashboard.dangerAlert.checkPatient")}</p>
            <div className="mt-4 p-3 rounded-lg bg-danger/10 text-sm space-y-1">
              {dangerPerson && (
                <p className="flex items-center gap-1.5">
                  <UserRound className="h-3.5 w-3.5 text-danger" />
                  <span className="font-semibold">
                    {t("events.person", "인원")} {formatPersonId(dangerPerson.personId)}
                  </span>
                </p>
              )}
              {dangerCamName && (
                <p className="flex items-center gap-1.5">
                  <Camera className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-semibold">{dangerCamName}</span>
                </p>
              )}
              <p>
                <span className="text-muted-foreground">{t("dashboard.dangerAlert.duration")}:</span>{" "}
                <span className="font-semibold font-mono" aria-live="polite">
                  {alertDuration}{t("common.seconds")}
                </span>
              </p>
              <p>
                <span className="text-muted-foreground">{t("dashboard.dangerAlert.detectedAt")}:</span>{" "}
                <span className="font-semibold font-mono">
                  {new Date().toLocaleTimeString(i18n.language === "ko" ? "ko-KR" : "en-US", {
                    hour12: false,
                  })}
                </span>
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="sm:justify-center">
          <AlertDialogAction
            ref={acknowledgeButtonRef}
            onClick={handleAcknowledge}
            className="bg-danger hover:bg-danger/90 text-danger-foreground text-xl px-10 py-5 h-auto min-h-[56px]"
          >
            {t("dashboard.dangerAlert.acknowledge")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
