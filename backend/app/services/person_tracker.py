"""
IoU 기반 인물 추적기

프레임 간 바운딩박스 IoU 매칭으로 안정적 person_id를 할당합니다.
"""

import time
from dataclasses import dataclass, field

from app.core.logging_config import get_logger

logger = get_logger("app.services.person_tracker")


@dataclass
class TrackedPerson:
    """추적 중인 인물"""
    person_id: str
    bbox: tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    last_seen: float = field(default_factory=time.time)
    frames_tracked: int = 1


def _compute_iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """두 바운딩박스의 IoU 계산"""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0

    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - intersection

    return intersection / union if union > 0 else 0.0


class PersonTracker:
    """프레임 간 인물 추적기"""

    IOU_THRESHOLD = 0.3

    def __init__(self, max_lost_seconds: float = 2.0):
        self._tracked: dict[str, TrackedPerson] = {}
        self._next_id: int = 0
        self._max_lost_seconds = max_lost_seconds

    def _generate_id(self) -> str:
        pid = f"person_{self._next_id}"
        self._next_id += 1
        return pid

    def update(self, poses: list) -> dict[int, str]:
        """
        포즈 감지 결과를 기반으로 인물 추적 업데이트

        Args:
            poses: PoseLandmarks 리스트 (각각 .bbox 필드 필요)

        Returns:
            dict: pose 인덱스 → 안정적 person_id 매핑
        """
        now = time.time()

        # 사라진 인물 제거
        expired = [
            pid for pid, tp in self._tracked.items()
            if now - tp.last_seen > self._max_lost_seconds
        ]
        for pid in expired:
            logger.debug("인물 추적 종료: %s", pid)
            del self._tracked[pid]

        # 현재 프레임의 바운딩박스
        current_bboxes = []
        for pose in poses:
            bbox = getattr(pose, "bbox", None)
            if bbox is None:
                bbox = (0.0, 0.0, 1.0, 1.0)
            current_bboxes.append(bbox)

        # IoU 매트릭스 계산
        tracked_list = list(self._tracked.values())
        iou_pairs = []
        for t_idx, tp in enumerate(tracked_list):
            for c_idx, bbox in enumerate(current_bboxes):
                iou = _compute_iou(tp.bbox, bbox)
                if iou >= self.IOU_THRESHOLD:
                    iou_pairs.append((iou, t_idx, c_idx))

        # Greedy 매칭 (IoU 높은 순)
        iou_pairs.sort(key=lambda x: x[0], reverse=True)
        matched_tracked = set()
        matched_current = set()
        assignments: dict[int, str] = {}

        for iou, t_idx, c_idx in iou_pairs:
            if t_idx in matched_tracked or c_idx in matched_current:
                continue
            tp = tracked_list[t_idx]
            tp.bbox = current_bboxes[c_idx]
            tp.last_seen = now
            tp.frames_tracked += 1
            assignments[c_idx] = tp.person_id
            matched_tracked.add(t_idx)
            matched_current.add(c_idx)

        # 미매칭 현재 감지 → 새 ID 부여
        for c_idx in range(len(current_bboxes)):
            if c_idx not in matched_current:
                pid = self._generate_id()
                self._tracked[pid] = TrackedPerson(
                    person_id=pid,
                    bbox=current_bboxes[c_idx],
                    last_seen=now,
                )
                assignments[c_idx] = pid
                logger.debug("새 인물 감지: %s", pid)

        # 포즈에 안정적 person_id 반영
        for c_idx, pid in assignments.items():
            if c_idx < len(poses):
                poses[c_idx].person_id = pid

        return assignments

    @property
    def active_count(self) -> int:
        """현재 추적 중인 인물 수"""
        return len(self._tracked)

    @property
    def tracked_persons(self) -> dict[str, TrackedPerson]:
        """현재 추적 중인 인물 정보"""
        return dict(self._tracked)

    def reset(self):
        """추적 상태 초기화"""
        self._tracked.clear()
        self._next_id = 0


# 싱글톤 인스턴스
person_tracker = PersonTracker()
