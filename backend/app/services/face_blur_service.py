"""
얼굴 블러(모자이크) 서비스

스냅샷 저장 시 개인정보 보호를 위해 얼굴 영역에 가우시안 블러를 적용합니다.
OpenCV의 Haar Cascade를 사용하며, 캐스케이드 파일 로드 실패 시
graceful degradation으로 원본 프레임을 반환합니다.
"""

import cv2
import numpy as np

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.face_blur")


class FaceBlurService:
    """얼굴 감지 및 블러 처리 서비스"""

    def __init__(self):
        self._cascade: cv2.CascadeClassifier | None = None
        self._available: bool = False
        self._init_cascade()

    def _init_cascade(self) -> None:
        """Haar Cascade 분류기 초기화"""
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
            self._cascade = cv2.CascadeClassifier(cascade_path)

            # 캐스케이드가 비어있으면 로드 실패
            if self._cascade.empty():
                logger.warning("Haar Cascade 파일 로드 실패: %s", cascade_path)
                self._cascade = None
                self._available = False
            else:
                self._available = True
                logger.info("얼굴 블러 서비스 초기화 완료")
        except Exception as e:
            logger.warning("얼굴 블러 서비스 초기화 실패: %s", e)
            self._cascade = None
            self._available = False

    @property
    def enabled(self) -> bool:
        """설정과 캐스케이드 가용 여부를 모두 확인"""
        return settings.FACE_BLUR_ENABLED and self._available

    @property
    def available(self) -> bool:
        """캐스케이드 분류기 가용 여부"""
        return self._available

    def blur_faces(self, frame: np.ndarray) -> np.ndarray:
        """프레임에서 얼굴을 감지하고 가우시안 블러를 적용

        Args:
            frame: BGR 형식의 OpenCV 이미지 (np.ndarray)

        Returns:
            얼굴 영역에 블러가 적용된 프레임.
            서비스가 비활성화되었거나 에러 발생 시 원본 프레임을 그대로 반환합니다.
        """
        if not self.enabled or self._cascade is None:
            return frame

        try:
            # 그레이스케일 변환 (Haar Cascade 입력)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # 얼굴 감지
            faces = self._cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30),
                flags=cv2.CASCADE_SCALE_IMAGE,
            )

            if len(faces) == 0:
                return frame

            # 결과 프레임 복사 (원본 보존)
            result = frame.copy()

            for (x, y, w, h) in faces:
                # 얼굴 영역에 가우시안 블러 적용
                face_region = result[y:y + h, x:x + w]
                # 커널 크기는 홀수여야 하며, 얼굴 크기에 비례
                ksize = max(w, h) // 3
                ksize = ksize + 1 if ksize % 2 == 0 else ksize
                ksize = max(ksize, 15)  # 최소 블러 강도
                blurred = cv2.GaussianBlur(face_region, (ksize, ksize), 30)
                result[y:y + h, x:x + w] = blurred

            logger.debug("얼굴 %d개 블러 처리 완료", len(faces))
            return result

        except Exception as e:
            # 에러 발생 시 원본 프레임 반환 (서비스 안정성 보장)
            logger.error("얼굴 블러 처리 실패: %s", e, exc_info=True)
            return frame


# 싱글턴
face_blur_service = FaceBlurService()
