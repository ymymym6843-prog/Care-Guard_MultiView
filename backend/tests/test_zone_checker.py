"""
ZoneChecker 유닛 테스트

point-in-polygon, zone 우선순위, bbox 기준점 변환 등을 검증합니다.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.zone_checker import ZoneChecker


# === point_in_polygon 테스트 ===

class TestPointInPolygon:
    """Ray-casting 알고리즘 테스트"""

    def setup_method(self):
        self.checker = ZoneChecker()

    def test_inside_rectangle(self):
        """사각형 폴리곤 내부 점"""
        polygon = [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
        ]
        assert self.checker._point_in_polygon(0.5, 0.5, polygon) is True

    def test_outside_rectangle(self):
        """사각형 폴리곤 외부 점"""
        polygon = [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
        ]
        assert self.checker._point_in_polygon(0.1, 0.1, polygon) is False

    def test_inside_triangle(self):
        """삼각형 폴리곤 내부 점"""
        polygon = [
            {"x": 0.5, "y": 0.1},
            {"x": 0.9, "y": 0.9},
            {"x": 0.1, "y": 0.9},
        ]
        assert self.checker._point_in_polygon(0.5, 0.5, polygon) is True

    def test_outside_triangle(self):
        """삼각형 폴리곤 외부 점"""
        polygon = [
            {"x": 0.5, "y": 0.1},
            {"x": 0.9, "y": 0.9},
            {"x": 0.1, "y": 0.9},
        ]
        assert self.checker._point_in_polygon(0.1, 0.1, polygon) is False

    def test_point_far_right(self):
        """사각형 오른쪽 바깥 점"""
        polygon = [
            {"x": 0.0, "y": 0.0},
            {"x": 0.5, "y": 0.0},
            {"x": 0.5, "y": 0.5},
            {"x": 0.0, "y": 0.5},
        ]
        assert self.checker._point_in_polygon(0.9, 0.25, polygon) is False

    def test_small_polygon(self):
        """작은 폴리곤 내부/외부"""
        polygon = [
            {"x": 0.4, "y": 0.4},
            {"x": 0.6, "y": 0.4},
            {"x": 0.6, "y": 0.6},
            {"x": 0.4, "y": 0.6},
        ]
        assert self.checker._point_in_polygon(0.5, 0.5, polygon) is True
        assert self.checker._point_in_polygon(0.3, 0.5, polygon) is False


# === Zone 우선순위 테스트 ===

class TestZonePriority:
    """겹치는 zone에서 우선순위 검증"""

    def setup_method(self):
        self.checker = ZoneChecker()

    @pytest.mark.asyncio
    async def test_exclusion_over_safe(self):
        """exclusion이 safe보다 우선"""
        # 두 zone 모두 같은 영역을 커버
        zones = [
            {"id": 1, "zone_type": "safe", "polygon": [
                {"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0},
            ], "priority": 1},
            {"id": 2, "zone_type": "exclusion", "polygon": [
                {"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0},
            ], "priority": 3},
        ]
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=zones):
            result = await self.checker.check_person_zone("cam0", [0.3, 0.2, 0.7, 0.8])
        assert result == "exclusion"

    @pytest.mark.asyncio
    async def test_danger_over_safe(self):
        """danger가 safe보다 우선"""
        zones = [
            {"id": 1, "zone_type": "safe", "polygon": [
                {"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0},
            ], "priority": 1},
            {"id": 2, "zone_type": "danger", "polygon": [
                {"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0},
                {"x": 1.0, "y": 1.0}, {"x": 0.0, "y": 1.0},
            ], "priority": 2},
        ]
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=zones):
            result = await self.checker.check_person_zone("cam0", [0.3, 0.2, 0.7, 0.8])
        assert result == "danger"

    @pytest.mark.asyncio
    async def test_no_matching_zone(self):
        """어떤 zone에도 속하지 않으면 None"""
        zones = [
            {"id": 1, "zone_type": "safe", "polygon": [
                {"x": 0.0, "y": 0.0}, {"x": 0.2, "y": 0.0},
                {"x": 0.2, "y": 0.2}, {"x": 0.0, "y": 0.2},
            ], "priority": 1},
        ]
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=zones):
            result = await self.checker.check_person_zone("cam0", [0.5, 0.5, 0.8, 0.9])
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_zones(self):
        """zone이 없으면 None"""
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=[]):
            result = await self.checker.check_person_zone("cam0", [0.3, 0.2, 0.7, 0.8])
        assert result is None


# === BBox 기준점 테스트 ===

class TestBboxReferencePoint:
    """bbox → 기준점 (하단 중앙) 변환 테스트"""

    def setup_method(self):
        self.checker = ZoneChecker()

    @pytest.mark.asyncio
    async def test_bbox_bottom_center(self):
        """bbox [0.2, 0.1, 0.6, 0.9] → 기준점 (0.4, 0.9)"""
        # 하단 중앙 (0.4, 0.9)이 zone 안에 있는지 확인
        zone_covering_bottom = [
            {"id": 1, "zone_type": "safe", "polygon": [
                {"x": 0.3, "y": 0.8}, {"x": 0.5, "y": 0.8},
                {"x": 0.5, "y": 1.0}, {"x": 0.3, "y": 1.0},
            ], "priority": 1},
        ]
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=zone_covering_bottom):
            result = await self.checker.check_person_zone("cam0", [0.2, 0.1, 0.6, 0.9])
        assert result == "safe"

    @pytest.mark.asyncio
    async def test_bbox_top_not_in_zone(self):
        """bbox 상단만 zone에 걸치고 하단 중앙은 zone 밖이면 None"""
        zone_covering_top = [
            {"id": 1, "zone_type": "safe", "polygon": [
                {"x": 0.3, "y": 0.0}, {"x": 0.5, "y": 0.0},
                {"x": 0.5, "y": 0.2}, {"x": 0.3, "y": 0.2},
            ], "priority": 1},
        ]
        with patch.object(self.checker, "load_zones", new_callable=AsyncMock, return_value=zone_covering_top):
            # bbox 하단 중앙 = (0.4, 0.9) → zone 밖
            result = await self.checker.check_person_zone("cam0", [0.2, 0.1, 0.6, 0.9])
        assert result is None


# === 캐시 무효화 테스트 ===

class TestCacheInvalidation:
    """캐시 무효화 동작 검증"""

    def test_invalidate_all(self):
        """전체 캐시 클리어"""
        checker = ZoneChecker()
        checker._cache = {"cam0": [{"id": 1}], "cam1": [{"id": 2}]}
        checker._cache_time = {"cam0": 100.0, "cam1": 100.0}

        checker.invalidate_cache()

        assert checker._cache == {}
        assert checker._cache_time == {}

    def test_invalidate_specific_camera(self):
        """특정 카메라만 클리어"""
        checker = ZoneChecker()
        checker._cache = {"cam0": [{"id": 1}], "cam1": [{"id": 2}]}
        checker._cache_time = {"cam0": 100.0, "cam1": 100.0}

        checker.invalidate_cache("cam0")

        assert "cam0" not in checker._cache
        assert "cam1" in checker._cache
