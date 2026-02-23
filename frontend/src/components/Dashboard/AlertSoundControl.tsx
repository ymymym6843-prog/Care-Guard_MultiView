import { Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMonitoringStore } from "@/store/monitoring";

export function AlertSoundControl() {
  const { settings, updateSettings } = useMonitoringStore();

  const toggleSound = () => {
    updateSettings({ soundEnabled: !settings.soundEnabled });
  };

  return (
    <div className="flex items-center gap-2">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            onClick={toggleSound}
            aria-label={settings.soundEnabled ? "알림 소리 끄기" : "알림 소리 켜기"}
          >
            {settings.soundEnabled ? (
              <Volume2 className="h-4 w-4" />
            ) : (
              <VolumeX className="h-4 w-4 text-muted-foreground" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{settings.soundEnabled ? "알림 소리 켜짐" : "알림 소리 꺼짐"}</p>
        </TooltipContent>
      </Tooltip>

      {settings.soundEnabled && (
        <Slider
          value={[settings.soundVolume * 100]}
          onValueChange={([v]) => updateSettings({ soundVolume: (v ?? 0) / 100 })}
          max={100}
          step={10}
          className="w-20"
          aria-label="알림 소리 볼륨"
        />
      )}
    </div>
  );
}
