import { useEffect, useRef } from "react";
import { ShieldAlert } from "lucide-react";
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

interface DangerAlertDialogProps {
  onAcknowledge?: () => void;
}

export function DangerAlertDialog({ onAcknowledge }: DangerAlertDialogProps) {
  const { t, i18n } = useTranslation();
  const { currentAlert, alertDuration } = useMonitoringStore();
  const acknowledgeButtonRef = useRef<HTMLButtonElement>(null);

  const isOpen = currentAlert === "danger";

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
            className="bg-danger hover:bg-danger/90 text-danger-foreground text-xl px-10 py-4 h-auto"
          >
            {t("dashboard.dangerAlert.acknowledge")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
