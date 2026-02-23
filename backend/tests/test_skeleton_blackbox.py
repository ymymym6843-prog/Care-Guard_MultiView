"""
Skeleton Blackbox 단위 테스트

버퍼 기록, 덤프, 통계, 오버플로 처리를 검증합니다.
"""

import json
import time

import pytest

from app.services.skeleton_blackbox import (
    FrameRecord,
    PersonSnapshot,
    SkeletonBlackbox,
)


@pytest.fixture
def blackbox(tmp_path):
    """테스트용 블랙박스 (버퍼 2초 @10fps = 20프레임)"""
    bb = SkeletonBlackbox(buffer_seconds=2, fps=10)
    bb._incident_dir = tmp_path / "incidents"
    bb._incident_dir.mkdir()
    return bb


def _make_person(track_id="person_1", posture="standing", confidence=0.1):
    """테스트용 PersonSnapshot 생성"""
    landmarks = [[0.5, 0.3, 0.0, 0.99]] * 33
    return PersonSnapshot(
        track_id=track_id,
        landmarks=landmarks,
        posture=posture,
        confidence=confidence,
    )


class TestSkeletonBlackboxRecord:
    """버퍼 기록 테스트"""

    def test_record_single_frame(self, blackbox):
        person = _make_person()
        blackbox.record(time.time(), [person])
        stats = blackbox.get_buffer_stats()
        assert stats["frame_count"] == 1
        assert stats["person_count"] == 1

    def test_record_multiple_persons(self, blackbox):
        persons = [
            _make_person("person_1"),
            _make_person("person_2"),
            _make_person("person_3"),
        ]
        blackbox.record(time.time(), persons)
        stats = blackbox.get_buffer_stats()
        assert stats["frame_count"] == 1
        assert stats["person_count"] == 3

    def test_buffer_overflow(self, blackbox):
        """버퍼 용량(20프레임) 초과 시 오래된 데이터 삭제"""
        for i in range(30):
            blackbox.record(time.time() + i * 0.1, [_make_person()])
        stats = blackbox.get_buffer_stats()
        assert stats["frame_count"] == 20  # maxlen 제한

    def test_empty_buffer_stats(self, blackbox):
        stats = blackbox.get_buffer_stats()
        assert stats["frame_count"] == 0
        assert stats["time_range_sec"] == 0.0


class TestSkeletonBlackboxDump:
    """사건 덤프 테스트"""

    def test_dump_incident(self, blackbox):
        """정상 덤프"""
        now = time.time()
        for i in range(10):
            blackbox.record(now + i * 0.1, [_make_person(confidence=i * 0.1)])

        path = blackbox.dump_incident(
            event_id="test_danger",
            trigger_person="person_1",
            trigger_type="DANGER",
        )
        assert path is not None
        assert path.exists()
        assert path.suffix == ".json"

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["trigger_type"] == "DANGER"
        assert data["trigger_person"] == "person_1"
        assert data["total_frames"] == 10
        assert len(data["frames"]) == 10
        assert "privacy_notice" in data
        assert "system_trace_hash" in data

    def test_dump_empty_buffer(self, blackbox):
        """빈 버퍼 덤프 시 None 반환"""
        path = blackbox.dump_incident("test_empty")
        assert path is None

    def test_dump_preserves_landmarks(self, blackbox):
        """덤프 시 랜드마크 데이터 보존"""
        lms = [[0.1 * i, 0.2 * i, 0.0, 0.95] for i in range(33)]
        person = PersonSnapshot(
            track_id="person_1",
            landmarks=lms,
            posture="lying",
            confidence=0.9,
        )
        blackbox.record(time.time(), [person])

        path = blackbox.dump_incident("test_landmarks")
        data = json.loads(path.read_text(encoding="utf-8"))
        frame_person = data["frames"][0]["persons"][0]
        assert len(frame_person["landmarks"]) == 33
        assert frame_person["posture"] == "lying"
        assert frame_person["confidence"] == 0.9


class TestSkeletonBlackboxIncidentLookup:
    """사건 목록/상세 조회 테스트"""

    def test_list_incidents_empty(self, blackbox):
        incidents = blackbox.list_incidents()
        assert incidents == []

    def test_list_incidents_after_dump(self, blackbox):
        blackbox.record(time.time(), [_make_person()])
        blackbox.dump_incident("test_list")

        incidents = blackbox.list_incidents()
        assert len(incidents) == 1
        assert incidents[0]["trigger_type"] == "DANGER"

    def test_get_incident_not_found(self, blackbox):
        data = blackbox.get_incident("nonexistent")
        assert data is None

    def test_get_incident_success(self, blackbox):
        blackbox.record(time.time(), [_make_person()])
        path = blackbox.dump_incident("test_get")
        incident_id = path.stem

        data = blackbox.get_incident(incident_id)
        assert data is not None
        assert "frames" in data


class TestSkeletonBlackboxClear:
    """버퍼 초기화 테스트"""

    def test_clear(self, blackbox):
        blackbox.record(time.time(), [_make_person()])
        assert blackbox.get_buffer_stats()["frame_count"] == 1

        blackbox.clear()
        assert blackbox.get_buffer_stats()["frame_count"] == 0
