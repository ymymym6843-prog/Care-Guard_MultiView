/**
 * 이벤트 로그 훅
 *
 * REST API에서 이벤트 히스토리를 가져오고 실시간 업데이트와 병합합니다.
 */

import { useState, useCallback, useEffect } from "react";
import { apiCall } from "@/lib/auth";

interface EventItem {
  id: number;
  timestamp: string;
  alert_level: string;
  duration: number;
  camera_id: string;
  person_id: string | null;
  confidence: number;
  acknowledged: boolean;
  acknowledged_by: string | null;
  acknowledged_at: string | null;
}

interface EventsResponse {
  items: EventItem[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

const API_BASE = "/api/events";

export function useEventLog() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);

  const fetchEvents = useCallback(
    async (pageNum: number = 1, level?: string) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({
          page: pageNum.toString(),
          size: "20",
        });
        if (level) params.set("level", level);

        const res = await apiCall(`${API_BASE}?${params}`);
        if (!res.ok) return;

        const data: EventsResponse = await res.json();
        setEvents(data.items);
        setTotal(data.total);
        setPage(data.page);
      } catch {
        // 네트워크 오류
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const acknowledgeEvent = useCallback(async (eventId: number) => {
    try {
      const res = await apiCall(`${API_BASE}/${eventId}/acknowledge`, {
        method: "POST",
      });
      if (res.ok) {
        setEvents((prev) =>
          prev.map((e) =>
            e.id === eventId ? { ...e, acknowledged: true } : e,
          ),
        );
      }
    } catch {
      // 오류 처리
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  return {
    events,
    total,
    page,
    loading,
    fetchEvents,
    acknowledgeEvent,
    setPage,
  };
}
