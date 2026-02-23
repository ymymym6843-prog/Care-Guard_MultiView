/**
 * 개인정보 수집 동의 다이얼로그
 *
 * GDPR 준수를 위한 프라이버시 동의 화면
 */

import { useEffect, useState } from "react";
import { apiCall } from "@/lib/auth";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { useTranslation } from "react-i18next";

export function ConsentDialog() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const { t } = useTranslation();

  useEffect(() => {
    let cancelled = false;

    async function checkConsent() {
      try {
        const res = await apiCall("/api/auth/consent-status");
        if (!cancelled && res.ok) {
          const data = await res.json();
          setOpen(!data.consented);
        }
      } catch {
        // 네트워크 오류 시 다이얼로그 닫기
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    checkConsent();
    return () => { cancelled = true; };
  }, []);

  const handleConsent = async () => {
    try {
      const res = await apiCall("/api/auth/consent", { method: "POST" });
      if (res.ok) {
        setOpen(false);
      }
    } catch {
      // 실패 시 다이얼로그 유지
    }
  };

  if (loading) return null;

  return (
    <AlertDialog open={open} onOpenChange={() => {}}>
      <AlertDialogContent className="max-w-2xl">
        <AlertDialogHeader>
          <AlertDialogTitle>{t("consent.title")}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="text-left space-y-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">
                {t("consent.required")}
              </p>

              <div className="space-y-2">
                <div>
                  <span className="font-semibold text-foreground">{t("consent.collectedItems")}:</span>
                  <ul className="list-disc list-inside ml-2 mt-1">
                    <li>{t("consent.videoData")}</li>
                    <li>{t("consent.poseLandmarks")}</li>
                    <li>{t("consent.fallEvents")}</li>
                  </ul>
                </div>

                <div>
                  <span className="font-semibold text-foreground">{t("consent.purpose")}:</span>
                  <span className="block ml-2 mt-1">
                    {t("consent.purposeDesc")}
                  </span>
                </div>

                <div>
                  <span className="font-semibold text-foreground">{t("consent.retention")}:</span>
                  <ul className="list-disc list-inside ml-2 mt-1">
                    <li>{t("consent.eventRetention")}</li>
                    <li>{t("consent.snapshotRetention")}</li>
                  </ul>
                </div>

                <div>
                  <span className="font-semibold text-foreground">{t("consent.thirdParty")}:</span>
                  <span className="block ml-2 mt-1">
                    {t("consent.thirdPartyDesc")}
                  </span>
                </div>

                <span className="block text-xs text-muted-foreground mt-4">
                  {t("consent.legalNotice")}
                </span>
              </div>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogAction onClick={handleConsent}>
            {t("consent.agree")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
