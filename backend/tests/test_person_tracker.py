"""
PersonTracker 단위 테스트
"""

import time
from dataclasses import dataclass

import pytest

from app.services.person_tracker import PersonTracker, _compute_iou


@dataclass
class MockPose:
    """테스트용 포즈 목업"""
    landmarks: list = None
    person_id: str = ""
    bbox: tuple = None

    def __post_init__(self):
        if self.landmarks is None:
            self.landmarks = []


class TestComputeIoU:
    """IoU 계산 테스트"""

    def test_identical_boxes_iou_is_one(self):
        box = (0.0, 0.0, 1.0, 1.0)
        assert _compute_iou(box, box) == pytest.approx(1.0)

    def test_non_overlapping_boxes_iou_is_zero(self):
        a = (0.0, 0.0, 0.5, 0.5)
        b = (0.6, 0.6, 1.0, 1.0)
        assert _compute_iou(a, b) == 0.0

    def test_partial_overlap(self):
        a = (0.0, 0.0, 0.5, 0.5)
        b = (0.25, 0.25, 0.75, 0.75)
        iou = _compute_iou(a, b)
        assert 0.0 < iou < 1.0

    def test_one_inside_other(self):
        a = (0.0, 0.0, 1.0, 1.0)
        b = (0.25, 0.25, 0.75, 0.75)
        iou = _compute_iou(a, b)
        assert 0.0 < iou < 1.0


class TestPersonTracker:
    """PersonTracker 테스트"""

    def test_initial_id_assignment(self):
        tracker = PersonTracker()
        poses = [
            MockPose(bbox=(0.1, 0.1, 0.3, 0.9)),
            MockPose(bbox=(0.5, 0.1, 0.8, 0.9)),
        ]
        assignments = tracker.update(poses)
        assert len(assignments) == 2
        assert assignments[0] != assignments[1]

    def test_id_persistence_across_frames(self):
        tracker = PersonTracker()

        # 프레임 1
        poses1 = [MockPose(bbox=(0.1, 0.1, 0.3, 0.9))]
        assignments1 = tracker.update(poses1)
        first_id = assignments1[0]

        # 프레임 2: 약간 이동
        poses2 = [MockPose(bbox=(0.12, 0.1, 0.32, 0.9))]
        assignments2 = tracker.update(poses2)

        assert assignments2[0] == first_id

    def test_new_person_gets_new_id(self):
        tracker = PersonTracker()

        # 프레임 1: 1명
        poses1 = [MockPose(bbox=(0.1, 0.1, 0.3, 0.9))]
        tracker.update(poses1)
        first_id = poses1[0].person_id

        # 프레임 2: 원래 1명 + 새 1명 (먼 위치)
        poses2 = [
            MockPose(bbox=(0.12, 0.1, 0.32, 0.9)),
            MockPose(bbox=(0.7, 0.1, 0.95, 0.9)),
        ]
        assignments2 = tracker.update(poses2)

        # 원래 인물 ID 유지
        assert assignments2[0] == first_id
        # 새 인물 다른 ID
        assert assignments2[1] != first_id

    def test_active_count(self):
        tracker = PersonTracker()
        assert tracker.active_count == 0

        poses = [
            MockPose(bbox=(0.1, 0.1, 0.3, 0.9)),
            MockPose(bbox=(0.5, 0.1, 0.8, 0.9)),
        ]
        tracker.update(poses)
        assert tracker.active_count == 2

    def test_lost_person_removed_after_timeout(self):
        tracker = PersonTracker(max_lost_seconds=0.1)

        # 프레임 1: 2명
        poses1 = [
            MockPose(bbox=(0.1, 0.1, 0.3, 0.9)),
            MockPose(bbox=(0.5, 0.1, 0.8, 0.9)),
        ]
        tracker.update(poses1)
        assert tracker.active_count == 2

        # 시간 경과 시뮬레이션
        time.sleep(0.15)

        # 프레임 2: 1명만 (두 번째만)
        poses2 = [MockPose(bbox=(0.52, 0.1, 0.82, 0.9))]
        tracker.update(poses2)
        # 첫 번째 인물은 사라짐 (timeout), 두 번째만 남음
        assert tracker.active_count == 1

    def test_person_id_assigned_to_pose(self):
        tracker = PersonTracker()
        poses = [MockPose(bbox=(0.1, 0.1, 0.3, 0.9))]
        tracker.update(poses)
        assert poses[0].person_id.startswith("person_")

    def test_reset_clears_all(self):
        tracker = PersonTracker()
        poses = [MockPose(bbox=(0.1, 0.1, 0.3, 0.9))]
        tracker.update(poses)
        assert tracker.active_count == 1

        tracker.reset()
        assert tracker.active_count == 0

    def test_no_bbox_fallback(self):
        """bbox가 None인 포즈도 처리 가능"""
        tracker = PersonTracker()
        poses = [MockPose(bbox=None)]
        assignments = tracker.update(poses)
        assert len(assignments) == 1
