import { SlidersHorizontal, Volume2, VolumeX, Bell, BellOff, AudioLines, Eye, EyeOff } from "lucide-react";
import { apiCall } from "@/lib/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { useMonitoringStore } from "@/store/monitoring";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { useTranslation } from "react-i18next";

export function SettingsCard() {
  const { t } = useTranslation();
  const { settings, updateSettings } = useMonitoringStore();
  const { isSubscribed, isSupported, isLoading, subscribe, unsubscribe } =
    usePushNotifications();

  return (
    <Card className="glass-card">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-primary" />
          {t("dashboard.settings.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* 주의 단계 시간 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm text-muted-foreground">
              {t("dashboard.settings.warningTime")}
            </Label>
            <span className="text-sm font-mono font-semibold">
              {settings.fallThresholdTime}{t("dashboard.units.seconds")}
            </span>
          </div>
          <Slider
            value={[settings.fallThresholdTime]}
            onValueChange={([v]) => {
              if (v !== undefined && v < settings.dangerThresholdTime) {
                updateSettings({ fallThresholdTime: v });
              }
            }}
            min={1}
            max={10}
            step={1}
          />
        </div>

        {/* 위험 단계 시간 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm text-muted-foreground">
              {t("dashboard.settings.dangerTime")}
            </Label>
            <span className="text-sm font-mono font-semibold">
              {settings.dangerThresholdTime}{t("dashboard.units.seconds")}
            </span>
          </div>
          <Slider
            value={[settings.dangerThresholdTime]}
            onValueChange={([v]) => {
              if (v !== undefined && v > settings.fallThresholdTime) {
                updateSettings({ dangerThresholdTime: v });
              }
            }}
            min={5}
            max={30}
            step={1}
          />
        </div>

        {/* 감도 */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm text-muted-foreground">{t("dashboard.settings.sensitivity")}</Label>
            <span className="text-sm font-mono font-semibold">
              {(settings.sensitivity * 100).toFixed(0)}%
            </span>
          </div>
          <Slider
            value={[settings.sensitivity]}
            onValueChange={([v]) => updateSettings({ sensitivity: v })}
            min={0.1}
            max={1.0}
            step={0.1}
          />
        </div>

        {/* 소리 알림 */}
        <div className="flex items-center justify-between">
          <Label className="text-sm text-muted-foreground flex items-center gap-2">
            {settings.soundEnabled ? (
              <Volume2 className="h-4 w-4" />
            ) : (
              <VolumeX className="h-4 w-4" />
            )}
            {t("dashboard.settings.soundEnabled")}
          </Label>
          <Switch
            checked={settings.soundEnabled}
            onCheckedChange={(checked) =>
              updateSettings({ soundEnabled: checked })
            }
          />
        </div>

        {/* 음성 안내 (TTS) */}
        <div className="flex items-center justify-between">
          <Label className="text-sm text-muted-foreground flex items-center gap-2">
            <AudioLines className="h-4 w-4" />
            {t("dashboard.settings.ttsEnabled")}
          </Label>
          <Switch
            checked={settings.ttsEnabled}
            onCheckedChange={(checked) =>
              updateSettings({ ttsEnabled: checked })
            }
          />
        </div>

        {/* 푸시 알림 */}
        {isSupported && (
          <div className="flex items-center justify-between">
            <Label className="text-sm text-muted-foreground flex items-center gap-2">
              {isSubscribed ? (
                <Bell className="h-4 w-4" />
              ) : (
                <BellOff className="h-4 w-4" />
              )}
              {t("dashboard.settings.pushEnabled")}
            </Label>
            <Switch
              checked={isSubscribed}
              disabled={isLoading}
              onCheckedChange={(checked) => {
                if (checked) {
                  subscribe();
                } else {
                  unsubscribe();
                }
              }}
            />
          </div>
        )}

        {/* 스켈레톤 오버레이 (발표용 토글) */}
        <div className="flex items-center justify-between">
          <Label className="text-sm text-muted-foreground flex items-center gap-2">
            {settings.overlayEnabled ? (
              <Eye className="h-4 w-4" />
            ) : (
              <EyeOff className="h-4 w-4" />
            )}
            {t("dashboard.settings.skeletonOverlay")}
          </Label>
          <Switch
            checked={settings.overlayEnabled}
            onCheckedChange={async (checked) => {
              updateSettings({ overlayEnabled: checked });
              // 백엔드 API 호출
              try {
                await apiCall("/api/settings/overlay", {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ enabled: checked }),
                });
              } catch (e) {
                console.error("오버레이 설정 동기화 실패:", e);
              }
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
