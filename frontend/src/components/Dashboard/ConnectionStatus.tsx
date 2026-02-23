import { Wifi, WifiOff, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useMonitoringStore } from "@/store/monitoring";
import { useTranslation } from "react-i18next";

export function ConnectionStatus() {
  const { t } = useTranslation();
  const connectionStatus = useMonitoringStore((s) => s.connectionStatus);

  const config = {
    connected: {
      icon: Wifi,
      label: t("dashboard.connection.connected"),
      description: t("dashboard.connection.connectedDesc"),
      badgeClass: "bg-safe/20 text-safe border-safe/30",
      iconClass: "text-safe",
    },
    connecting: {
      icon: Loader2,
      label: t("dashboard.connection.connectingDesc", "자동 재연결 중..."),
      description: t("dashboard.connection.connectingDesc"),
      badgeClass: "bg-warning/20 text-warning border-warning/30",
      iconClass: "text-warning animate-spin",
    },
    disconnected: {
      icon: WifiOff,
      label: t("dashboard.connection.disconnected"),
      description: t("dashboard.connection.disconnectedDesc"),
      badgeClass: "bg-danger/20 text-danger border-danger/30",
      iconClass: "text-danger animate-danger-pulse",
    },
  };

  const { icon: Icon, label, description, badgeClass, iconClass } = config[connectionStatus];

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-center gap-2 cursor-help" role="status" aria-live="polite">
            <Icon className={cn("h-4 w-4", iconClass)} aria-hidden="true" />
            <Badge variant="outline" className={badgeClass}>
              {label}
            </Badge>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          {description}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
