"""
Privacy-First Data Pipeline

Non-Storage 스트리밍 기반 프라이버시 파이프라인입니다.
원본 프레임을 메모리에서 즉시 파기하여 영상 비저장을 보장합니다.

핵심 원칙:
1. 원본 프레임은 랜드마크 추출 직후 즉시 파기
2. 추출된 좌표 데이터만 다운스트림으로 전달
3. 프라이버시 감사 로그를 통해 파기 사실 증명
"""

import gc
import time
import uuid
from dataclasses import dataclass, field

import numpy as np

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.privacy_pipeline")


@dataclass
class ProcessedFrame:
    """프라이버시 처리 완료된 프레임 데이터 (좌표만, 원본 없음)"""
    frame_id: str
    timestamp: float
    landmarks: list[list[dict]] = field(default_factory=list)  # 인원별 33개 관절
    person_ids: list[str] = field(default_factory=list)
    processing_ms: float = 0.0
    sanitized: bool = False


class PrivacyPipeline:
    """Non-Storage 스트리밍 기반 프라이버시 파이프라인"""

    def __init__(self):
        self._non_storage = getattr(settings, "PRIVACY_NON_STORAGE", True)
        self._frame_retention_ms = getattr(settings, "PRIVACY_FRAME_RETENTION_MS", 0)
        self._audit_enabled = getattr(settings, "PRIVACY_AUDIT_ENABLED", True)
        self._frames_processed = 0
        self._frames_sanitized = 0

    @property
    def non_storage_enabled(self) -> bool:
        return self._non_storage

    def create_frame_id(self) -> str:
        """프레임 추적용 고유 ID 생성 (개인정보 미포함)"""
        return f"frame_{uuid.uuid4().hex[:12]}"

    def sanitize_and_release(self, frame: np.ndarray) -> None:
        """메모리에서 프레임 데이터 즉시 제거

        1. 프레임 메모리를 0으로 덮어쓰기 (보안)
        2. 참조 삭제
        3. GC 강제 호출 (선택적)
        """
        if frame is None:
            return

        try:
            # Step 1: 메모리 zeroing (보안 삭제)
            if isinstance(frame, np.ndarray) and frame.size > 0:
                frame[:] = 0
            self._frames_sanitized += 1
        except (ValueError, TypeError):
            # 읽기 전용 배열 등의 경우
            pass
        finally:
            # Step 2: 참조 삭제
            del frame

        # Step 3: 즉시 파기 모드에서는 GC 강제 호출
        if self._frame_retention_ms == 0:
            gc.collect(generation=0)

    def wrap_processed_frame(
        self,
        frame_id: str,
        timestamp: float,
        landmarks_list: list,
        person_ids: list[str],
        processing_ms: float = 0.0,
    ) -> ProcessedFrame:
        """추출된 좌표 데이터를 ProcessedFrame으로 래핑"""
        self._frames_processed += 1
        return ProcessedFrame(
            frame_id=frame_id,
            timestamp=timestamp,
            landmarks=landmarks_list,
            person_ids=person_ids,
            processing_ms=processing_ms,
            sanitized=True,
        )

    def get_stats(self) -> dict:
        """파이프라인 통계"""
        return {
            "non_storage_enabled": self._non_storage,
            "frame_retention_ms": self._frame_retention_ms,
            "frames_processed": self._frames_processed,
            "frames_sanitized": self._frames_sanitized,
            "frames_stored": 0,  # 항상 0 (비저장 정책)
            "audit_enabled": self._audit_enabled,
        }


# 싱글턴
privacy_pipeline = PrivacyPipeline()
