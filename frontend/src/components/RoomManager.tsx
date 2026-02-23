/**
 * 공간 관리 컴포넌트 (admin 전용)
 *
 * 공간 CRUD + 카메라 배정 UI.
 */

import { useState, useEffect, useCallback } from "react";
import {
  Building2,
  Plus,
  RefreshCcw,
  Pencil,
  Trash2,
  Camera,
  Check,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { apiCall } from "@/lib/auth";
import { useTranslation } from "react-i18next";
import { useMonitoringStore, type CameraInfo } from "@/store/monitoring";

interface RoomData {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
  camera_count: number;
  created_at: string;
}

interface RoomCameras {
  [roomId: number]: string[];
}

export function RoomManager() {
  const { t } = useTranslation();
  const cameras = useMonitoringStore((s) => s.cameras);
  const setRooms = useMonitoringStore((s) => s.setRooms);

  const [rooms, setLocalRooms] = useState<RoomData[]>([]);
  const [roomCameras, setRoomCameras] = useState<RoomCameras>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Add form
  const [showAddForm, setShowAddForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [addLoading, setAddLoading] = useState(false);

  // Edit state
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");

  // Camera assign state
  const [assigningId, setAssigningId] = useState<number | null>(null);
  const [selectedCameras, setSelectedCameras] = useState<string[]>([]);

  const fetchRooms = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiCall("/api/rooms");
      if (res.ok) {
        const data = await res.json();
        const items: RoomData[] = data.items ?? [];
        setLocalRooms(items);
        setError("");

        // Update global store
        setRooms(
          items.map((r) => ({
            id: r.id,
            name: r.name,
            description: r.description,
            isActive: r.is_active,
            cameraCount: r.camera_count,
          })),
        );

        // Fetch cameras for each room
        const camMap: RoomCameras = {};
        await Promise.all(
          items.map(async (room) => {
            try {
              const camRes = await apiCall(`/api/rooms/${room.id}/cameras`);
              if (camRes.ok) {
                const camData = await camRes.json();
                camMap[room.id] = camData.camera_ids ?? [];
              }
            } catch {
              camMap[room.id] = [];
            }
          }),
        );
        setRoomCameras(camMap);
      } else {
        setError(t("roomManager.loadError", "공간 목록을 불러올 수 없습니다"));
      }
    } catch {
      setError(t("roomManager.connectionError", "서버 연결 실패"));
    } finally {
      setLoading(false);
    }
  }, [setRooms, t]);

  useEffect(() => {
    fetchRooms();
  }, [fetchRooms]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setAddLoading(true);
    try {
      const res = await apiCall("/api/rooms", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() }),
      });
      if (res.ok) {
        setNewName("");
        setNewDesc("");
        setShowAddForm(false);
        fetchRooms();
      }
    } catch {
      // ignore
    } finally {
      setAddLoading(false);
    }
  };

  const handleEdit = async (roomId: number) => {
    try {
      const res = await apiCall(`/api/rooms/${roomId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: editName.trim(), description: editDesc.trim() }),
      });
      if (res.ok) {
        setEditingId(null);
        fetchRooms();
      }
    } catch {
      // ignore
    }
  };

  const handleDelete = async (roomId: number) => {
    try {
      await apiCall(`/api/rooms/${roomId}`, { method: "DELETE" });
      fetchRooms();
    } catch {
      // ignore
    }
  };

  const startAssign = (roomId: number) => {
    setAssigningId(roomId);
    setSelectedCameras(roomCameras[roomId] ?? []);
  };

  const toggleCamera = (camId: string) => {
    setSelectedCameras((prev) =>
      prev.includes(camId) ? prev.filter((c) => c !== camId) : [...prev, camId],
    );
  };

  const handleAssign = async () => {
    if (assigningId === null) return;
    try {
      const res = await apiCall(`/api/rooms/${assigningId}/cameras`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_ids: selectedCameras }),
      });
      if (res.ok) {
        setAssigningId(null);
        fetchRooms();
      }
    } catch {
      // ignore
    }
  };

  // Get all camera IDs already assigned to other rooms
  const getAssignedCameras = (excludeRoomId: number): Set<string> => {
    const assigned = new Set<string>();
    for (const [rid, cams] of Object.entries(roomCameras)) {
      if (Number(rid) !== excludeRoomId) {
        cams.forEach((c: string) => assigned.add(c));
      }
    }
    return assigned;
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Building2 className="h-4 w-4 text-primary" />
            {t("roomManager.title", "공간 관리")}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={fetchRooms}>
              <RefreshCcw className="h-4 w-4" />
            </Button>
            <Button size="sm" onClick={() => setShowAddForm(!showAddForm)}>
              <Plus className="h-4 w-4 mr-1" />
              {t("roomManager.addRoom", "공간 추가")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-danger mb-3">{error}</p>}

          {/* Add form */}
          {showAddForm && (
            <form
              onSubmit={handleAdd}
              className="mb-4 p-4 rounded-lg border bg-muted/30 space-y-3"
            >
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label htmlFor="room-name" className="text-xs font-medium">
                    {t("roomManager.name", "공간 이름")}
                  </label>
                  <input
                    id="room-name"
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    required
                    maxLength={100}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                    placeholder={t("roomManager.namePlaceholder", "예: 대기실 A")}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="room-desc" className="text-xs font-medium">
                    {t("roomManager.description", "설명")}
                  </label>
                  <input
                    id="room-desc"
                    type="text"
                    value={newDesc}
                    onChange={(e) => setNewDesc(e.target.value)}
                    maxLength={200}
                    className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm"
                    placeholder={t("roomManager.descPlaceholder", "예: 1층 대기실")}
                  />
                </div>
              </div>
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={addLoading}>
                  {addLoading
                    ? t("common.loading", "로딩...")
                    : t("roomManager.add", "추가")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowAddForm(false)}
                >
                  {t("common.cancel", "취소")}
                </Button>
              </div>
            </form>
          )}

          {/* Room list */}
          {loading ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {t("common.loading", "로딩...")}
            </p>
          ) : rooms.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              {t("roomManager.noRooms", "등록된 공간이 없습니다. 공간을 추가해주세요.")}
            </p>
          ) : (
            <div className="divide-y divide-border">
              {rooms.map((room) => (
                <div key={room.id} className="py-3">
                  {editingId === room.id ? (
                    /* Edit mode */
                    <div className="space-y-2">
                      <div className="grid grid-cols-2 gap-2">
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="flex h-8 w-full rounded-md border border-input bg-background px-2 py-1 text-sm"
                          autoFocus
                        />
                        <input
                          type="text"
                          value={editDesc}
                          onChange={(e) => setEditDesc(e.target.value)}
                          className="flex h-8 w-full rounded-md border border-input bg-background px-2 py-1 text-sm"
                        />
                      </div>
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEdit(room.id)}
                          className="h-7 px-2"
                        >
                          <Check className="h-3.5 w-3.5 text-safe" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setEditingId(null)}
                          className="h-7 px-2"
                        >
                          <X className="h-3.5 w-3.5 text-danger" />
                        </Button>
                      </div>
                    </div>
                  ) : assigningId === room.id ? (
                    /* Camera assign mode */
                    <div className="space-y-2">
                      <div className="flex items-center gap-2 mb-1">
                        <Camera className="h-4 w-4 text-primary" />
                        <span className="text-sm font-medium">
                          {room.name} - {t("roomManager.assignCameras", "카메라 배정")}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {cameras.length === 0 ? (
                          <p className="text-xs text-muted-foreground">
                            {t("roomManager.noCameras", "감지된 카메라가 없습니다")}
                          </p>
                        ) : (
                          cameras.map((cam: CameraInfo) => {
                            const assignedElsewhere = getAssignedCameras(room.id).has(cam.id);
                            const isSelected = selectedCameras.includes(cam.id);
                            return (
                              <button
                                key={cam.id}
                                type="button"
                                onClick={() => !assignedElsewhere && toggleCamera(cam.id)}
                                disabled={assignedElsewhere}
                                className={`
                                  px-3 py-1.5 rounded-md text-xs border transition-colors
                                  ${isSelected
                                    ? "bg-primary text-primary-foreground border-primary"
                                    : assignedElsewhere
                                      ? "bg-muted text-muted-foreground border-muted cursor-not-allowed opacity-50"
                                      : "bg-background hover:bg-muted border-input cursor-pointer"
                                  }
                                `}
                              >
                                {cam.name || cam.id}
                                {cam.isActive && (
                                  <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-green-400" />
                                )}
                                {assignedElsewhere && (
                                  <span className="ml-1 text-[10px] opacity-70">
                                    ({t("roomManager.assigned", "배정됨")})
                                  </span>
                                )}
                              </button>
                            );
                          })
                        )}
                      </div>
                      <div className="flex gap-1 mt-1">
                        <Button
                          size="sm"
                          variant="default"
                          onClick={handleAssign}
                          className="h-7 px-3 text-xs"
                        >
                          <Check className="h-3.5 w-3.5 mr-1" />
                          {t("common.save", "저장")}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setAssigningId(null)}
                          className="h-7 px-3 text-xs"
                        >
                          {t("common.cancel", "취소")}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    /* Normal display */
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                          <Building2 className="h-4 w-4 text-primary" />
                        </div>
                        <div>
                          <p className="text-sm font-medium">{room.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {room.description || t("roomManager.noDescription", "설명 없음")}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {/* Camera list badges */}
                        <div className="flex gap-1">
                          {(roomCameras[room.id] ?? []).map((camId) => (
                            <Badge key={camId} variant="secondary" className="text-[10px] px-1.5">
                              {camId}
                            </Badge>
                          ))}
                          {room.camera_count === 0 && (
                            <span className="text-xs text-muted-foreground">
                              {t("roomManager.noCameraAssigned", "미배정")}
                            </span>
                          )}
                        </div>
                        {/* Action buttons */}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => startAssign(room.id)}
                          title={t("roomManager.assignCameras", "카메라 배정")}
                        >
                          <Camera className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0"
                          onClick={() => {
                            setEditingId(room.id);
                            setEditName(room.name);
                            setEditDesc(room.description);
                          }}
                          title={t("roomManager.edit", "수정")}
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-danger hover:text-danger"
                          onClick={() => handleDelete(room.id)}
                          title={t("common.delete", "삭제")}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
