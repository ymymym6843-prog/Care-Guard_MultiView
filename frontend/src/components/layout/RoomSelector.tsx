/**
 * 공간(Room) 선택 드롭다운
 *
 * 사이드바 상단에 배치되어 공간을 전환합니다.
 */

import { Building2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useMonitoringStore } from "@/store/monitoring";
import { useTranslation } from "react-i18next";

interface RoomSelectorProps {
  collapsed: boolean;
}

export function RoomSelector({ collapsed }: RoomSelectorProps) {
  const { t } = useTranslation();
  const { rooms, selectedRoomId, setSelectedRoomId } = useMonitoringStore();

  if (rooms.length === 0) return null;

  const handleChange = (value: string) => {
    setSelectedRoomId(value === "all" ? null : Number(value));
  };

  const currentValue = selectedRoomId === null ? "all" : String(selectedRoomId);
  const selectedRoom = rooms.find((r) => r.id === selectedRoomId);
  const label = selectedRoom ? selectedRoom.name : t("room.allRooms", "전체 공간");

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            className="flex items-center justify-center w-full h-10 rounded-md hover:bg-sidebar-accent transition-colors"
            onClick={() => {
              // 접힌 상태: 순환 전환
              const currentIdx = rooms.findIndex((r) => r.id === selectedRoomId);
              if (currentIdx === -1 || currentIdx >= rooms.length - 1) {
                setSelectedRoomId(null);
              } else {
                setSelectedRoomId(rooms[currentIdx + 1]?.id ?? null);
              }
            }}
          >
            <Building2 className="h-5 w-5 text-muted-foreground" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">
          <p>{label}</p>
        </TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div className="px-2 mb-2">
      <Select value={currentValue} onValueChange={handleChange}>
        <SelectTrigger className="w-full h-9 text-sm">
          <Building2 className="h-4 w-4 mr-2 shrink-0 text-muted-foreground" />
          <SelectValue placeholder={t("room.selectRoom", "공간 선택")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("room.allRooms", "전체 공간")}</SelectItem>
          {rooms
            .filter((r) => r.isActive)
            .map((room) => (
              <SelectItem key={room.id} value={String(room.id)}>
                {room.name}
                {room.cameraCount > 0 && (
                  <span className="text-muted-foreground ml-1">
                    ({room.cameraCount})
                  </span>
                )}
              </SelectItem>
            ))}
        </SelectContent>
      </Select>
    </div>
  );
}
