import {
  LayoutDashboard,
  Camera,
  AlertTriangle,
  History,
  BarChart3,
  FileText,
  Settings,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";
import { RoomSelector } from "./RoomSelector";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  activePath: string;
  userRole?: string;
}

const navItemsConfig = [
  { id: "dashboard", path: "/dashboard", i18nKey: "nav.dashboard", icon: LayoutDashboard, roles: ["admin", "user"] },
  { id: "cameras", path: "/cameras", i18nKey: "nav.cameras", icon: Camera, roles: ["admin", "user"] },
  { id: "alerts", path: "/alerts", i18nKey: "nav.alerts", icon: AlertTriangle, roles: ["admin", "user"] },
  { id: "history", path: "/history", i18nKey: "nav.history", icon: History, roles: ["admin", "user"] },
  { id: "stats", path: "/stats", i18nKey: "nav.stats", icon: BarChart3, roles: ["admin"] },
  { id: "reports", path: "/reports", i18nKey: "nav.reports", icon: FileText, roles: ["admin"] },
  { id: "settings", path: "/settings", i18nKey: "nav.settings", icon: Settings, roles: ["admin"] },
];

export function Sidebar({
  collapsed,
  onToggle,
  userRole = "admin", // Default to admin for now if undefined (or handle as 'user')
}: SidebarProps) {
  const { t } = useTranslation();

  // Filter items based on user role
  const filteredNavItems = navItemsConfig.filter(item =>
    !item.roles || item.roles.includes(userRole)
  );

  const renderLink = (item: { id: string; path: string; i18nKey: string; icon: any }) => {
    const Icon = item.icon;
    const label = t(item.i18nKey);

    return (
      <NavLink
        key={item.id}
        to={item.path}
        className={({ isActive }) => cn(
          "flex items-center gap-3 h-10 px-4 py-2 rounded-full transition-all duration-300 text-sm font-medium hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
          isActive ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-sm" : "transparent",
          collapsed && "justify-center px-0"
        )}
      >
        <Icon className="h-5 w-5 shrink-0" />
        {!collapsed && <span className="truncate">{label}</span>}
      </NavLink>
    );
  };

  const renderTooltipLink = (item: any) => (
    <Tooltip key={item.id}>
      <TooltipTrigger asChild>
        {renderLink(item)}
      </TooltipTrigger>
      <TooltipContent side="right">
        <p>{t(item.i18nKey)}</p>
      </TooltipContent>
    </Tooltip>
  );

  return (
    <aside
      role="navigation"
      aria-label={t("sidebar.mainNav", "주요 탐색")}
      className={cn(
        "h-full glass-sidebar border-r flex flex-col transition-all duration-300 ease-in-out z-20 shadow-md",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* 공간 선택 */}
      <div className="pt-3">
        <RoomSelector collapsed={collapsed} />
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 py-4 space-y-1 px-2 flex flex-col">
        {filteredNavItems.map((item) =>
          collapsed ? renderTooltipLink(item) : renderLink(item)
        )}
      </nav>

      {/* 접기/펼치기 */}
      <div className="p-2 border-t border-sidebar-border">
        <Button
          variant="ghost"
          size="icon"
          className="w-full h-8"
          onClick={onToggle}
          aria-label={collapsed ? t("sidebar.expand", "사이드바 펼치기") : t("sidebar.collapse", "사이드바 접기")}
        >
          {collapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </Button>
      </div>
    </aside>
  );
}
