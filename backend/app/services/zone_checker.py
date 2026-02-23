"""
Safe-Zone 파이프라인 연동 서비스

DB에 저장된 zone 정보를 캐싱하고, 인물의 bbox 기준점이 어떤 zone에 속하는지 판별합니다.
- safe zone: 알림 억제 (is_fallen=False 처리)
- danger zone: 통과 (기본 동작)
- exclusion zone: 감지 자체 스킵
"""

import threading
import time
from typing import Optional

from sqlalchemy import select

from app.core.database import async_session
from app.core.logging_config import get_logger
from app.models.safe_zone import SafeZone

logger = get_logger("app.services.zone_checker")

# Zone 우선순위 (겹치면 높은 숫자 우선)
_ZONE_PRIORITY = {"safe": 1, "danger": 2, "exclusion": 3}

# 캐시 TTL (초)
_CACHE_TTL = 30.0


class ZoneChecker:
    """카메라별 Safe-Zone 캐시 + 인물 zone 판별"""

    def __init__(self):
        self._cache: dict[str, list[dict]] = {}  # camera_id -> [zone_dict, ...]
        self._cache_time: dict[str, float] = {}   # camera_id -> timestamp
        self._lock = threading.Lock()

    @staticmethod
    def _point_in_polygon(px: float, py: float, polygon: list[dict]) -> bool:
        """Ray-casting 알고리즘으로 점이 폴리곤 내부인지 판별 (O(n))

        Args:
            px, py: 테스트할 점 좌표 (정규화 0~1)
            polygon: [{"x": float, "y": float}, ...] 꼭짓점 리스트
        """
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]["x"], polygon[i]["y"]
            xj, yj = polygon[j]["x"], polygon[j]["y"]
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    async def load_zones(self, camera_id: str) -> list[dict]:
        """DB에서 활성 zone 로드 (TTL 캐시)"""
        now = time.monotonic()

        with self._lock:
            if camera_id in self._cache:
                if now - self._cache_time.get(camera_id, 0) < _CACHE_TTL:
                    return self._cache[camera_id]

        # 캐시 만료 또는 미존재 → DB 조회
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(SafeZone).where(
                        SafeZone.camera_id == camera_id,
                        SafeZone.is_active == True,  # noqa: E712
                    )
                )
                zones = result.scalars().all()

            zone_list = [
                {
                    "id": z.id,
                    "zone_type": z.zone_type,
                    "polygon": z.polygon,
                    "priority": _ZONE_PRIORITY.get(z.zone_type, 0),
                }
                for z in zones
            ]

            with self._lock:
                self._cache[camera_id] = zone_list
                self._cache_time[camera_id] = now

            if zone_list:
                logger.debug("[%s] zone 캐시 갱신: %d개 로드", camera_id, len(zone_list))

            return zone_list

        except Exception as e:
            logger.warning("zone 로드 실패 (camera_id=%s): %s", camera_id, e)
            # 실패해도 캐시에 빈 리스트 저장 (매 프레임 DB 재시도 방지)
            with self._lock:
                self._cache[camera_id] = []
                self._cache_time[camera_id] = now
            return []

    async def check_person_zone(self, camera_id: str, bbox: list | tuple) -> Optional[str]:
        """인물의 bbox로 zone 타입 판별

        Args:
            camera_id: 카메라 ID
            bbox: [x1, y1, x2, y2] (정규화 좌표 0~1)

        Returns:
            "safe" | "danger" | "exclusion" | None (매칭 zone 없음)
        """
        zones = await self.load_zones(camera_id)
        if not zones:
            return None

        # 기준점: bbox 하단 중앙 (발 위치)
        px = (bbox[0] + bbox[2]) / 2
        py = bbox[3]  # y2 = 하단

        # 모든 zone 검사, 우선순위 최대값 반환
        matched_zone: Optional[dict] = None

        for zone in zones:
            if self._point_in_polygon(px, py, zone["polygon"]):
                if matched_zone is None or zone["priority"] > matched_zone["priority"]:
                    matched_zone = zone

        return matched_zone["zone_type"] if matched_zone else None

    def invalidate_cache(self, camera_id: str | None = None) -> None:
        """캐시 무효화 (CRUD 시 호출)

        Args:
            camera_id: 특정 카메라만 무효화. None이면 전체 캐시 클리어.
        """
        with self._lock:
            if camera_id:
                self._cache.pop(camera_id, None)
                self._cache_time.pop(camera_id, None)
            else:
                self._cache.clear()
                self._cache_time.clear()
        logger.info("zone 캐시 무효화 (camera_id=%s)", camera_id or "전체")


# 싱글턴
zone_checker = ZoneChecker()
