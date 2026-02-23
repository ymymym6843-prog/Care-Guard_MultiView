"""
Privacy Pipeline 단위 테스트

프레임 비식별화, 메모리 파기, 통계를 검증합니다.
"""

import numpy as np
import pytest

from app.services.privacy_pipeline import PrivacyPipeline, ProcessedFrame


@pytest.fixture
def pipeline():
    return PrivacyPipeline()


class TestPrivacyPipelineSanitize:
    """프레임 메모리 파기 테스트"""

    def test_sanitize_zeros_memory(self, pipeline):
        """프레임 데이터가 0으로 덮어쓰이는지 확인"""
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        assert frame.sum() > 0

        pipeline.sanitize_and_release(frame)
        # frame 변수는 여전히 참조 가능 (Python GC 특성)
        # 하지만 내용은 0
        assert frame.sum() == 0

    def test_sanitize_none_frame(self, pipeline):
        """None 프레임은 무시"""
        pipeline.sanitize_and_release(None)  # 에러 없이 통과

    def test_sanitize_increments_counter(self, pipeline):
        """파기 카운터 증가"""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        pipeline.sanitize_and_release(frame)
        assert pipeline.get_stats()["frames_sanitized"] == 1

    def test_sanitize_readonly_frame(self, pipeline):
        """읽기 전용 배열도 에러 없이 처리"""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame.flags.writeable = False
        pipeline.sanitize_and_release(frame)  # ValueError 무시


class TestPrivacyPipelineProcessedFrame:
    """ProcessedFrame 래핑 테스트"""

    def test_wrap_processed_frame(self, pipeline):
        result = pipeline.wrap_processed_frame(
            frame_id="frame_abc123",
            timestamp=1234567890.0,
            landmarks_list=[[{"x": 0.5, "y": 0.3}]],
            person_ids=["person_1"],
            processing_ms=5.2,
        )
        assert isinstance(result, ProcessedFrame)
        assert result.frame_id == "frame_abc123"
        assert result.sanitized is True
        assert result.processing_ms == 5.2

    def test_frame_id_generation(self, pipeline):
        fid = pipeline.create_frame_id()
        assert fid.startswith("frame_")
        assert len(fid) == 18  # frame_ + 12 hex chars


class TestPrivacyPipelineStats:
    """통계 테스트"""

    def test_initial_stats(self, pipeline):
        stats = pipeline.get_stats()
        assert stats["frames_processed"] == 0
        assert stats["frames_sanitized"] == 0
        assert stats["frames_stored"] == 0  # 항상 0
        assert stats["non_storage_enabled"] is True

    def test_stats_after_processing(self, pipeline):
        pipeline.wrap_processed_frame("f1", 0.0, [], [])
        pipeline.wrap_processed_frame("f2", 0.0, [], [])
        stats = pipeline.get_stats()
        assert stats["frames_processed"] == 2
        assert stats["frames_stored"] == 0

    def test_non_storage_always_zero(self, pipeline):
        """저장된 프레임 수는 항상 0"""
        for i in range(100):
            pipeline.wrap_processed_frame(f"f{i}", 0.0, [], [])
            frame = np.zeros((100, 100, 3), dtype=np.uint8)
            pipeline.sanitize_and_release(frame)

        stats = pipeline.get_stats()
        assert stats["frames_stored"] == 0
        assert stats["frames_processed"] == 100
        assert stats["frames_sanitized"] == 100
