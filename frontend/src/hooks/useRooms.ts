/**
 * 공간(Room) 목록 조회 및 선택 관리 훅
 */

import { useEffect, useCallback } from "react";
import { useMonitoringStore, type RoomInfo } from "@/store/monitoring";
import { apiCall } from "@/lib/auth";

export function useRooms() {
  const { setRooms, selectedRoomId, setSelectedRoomId, setRoomCameraIds } =
    useMonitoringStore();

  const fetchRooms = useCallback(async () => {
    try {
      const res = await apiCall("/api/rooms");
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.items)) {
        const rooms: RoomInfo[] = data.items.map(
          (r: Record<string, unknown>) => ({
            id: r.id as number,
            name: r.name as string,
            description: (r.description as string) ?? "",
            isActive: (r.is_active as boolean) ?? true,
            cameraCount: (r.camera_count as number) ?? 0,
          }),
        );
        setRooms(rooms);
      }
    } catch {
      // ignore
    }
  }, [setRooms]);

  // 선택된 공간 변경 시 카메라 목록 갱신
  const fetchRoomCameras = useCallback(
    async (roomId: number | null) => {
      if (roomId === null) {
        setRoomCameraIds(null);
        return;
      }
      try {
        const res = await apiCall(`/api/rooms/${roomId}/cameras`);
        if (!res.ok) return;
        const data = await res.json();
        setRoomCameraIds(data.camera_ids ?? []);
      } catch {
        setRoomCameraIds([]);
      }
    },
    [setRoomCameraIds],
  );

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  useEffect(() => {
    fetchRoomCameras(selectedRoomId);
  }, [selectedRoomId, fetchRoomCameras]);

  return { fetchRooms, selectedRoomId, setSelectedRoomId };
}
