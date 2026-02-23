"""
포즈 감지 서비스 (Consumer)

MediaPipe PoseLandmarker Tasks API를 사용하여 카메라 프레임에서 포즈를 추출합니다.
camera_service의 frame_queue에서 프레임을 소비합니다.

mediapipe >= 0.10.30 (Tasks API) 대응
"""

import asyncio
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from app.services.camera_service import camera_service
from app.core.logging_config import get_logger

logger = get_logger("app.services.pose")

# 모델 다운로드 설정
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_MODEL_FILENAME = "pose_landmarker_full.task"
_MODEL_PATH = _MODEL_DIR / _MODEL_FILENAME
_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
)


def _ensure_model() -> str:
    """모델 파일이 없으면 다운로드"""
    if _MODEL_PATH.exists():
        return str(_MODEL_PATH)

    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("포즈 모델 다운로드 중: %s", _MODEL_URL)
    urllib.request.urlretrieve(_MODEL_URL, str(_MODEL_PATH))
    logger.info("포즈 모델 다운로드 완료: %s", _MODEL_PATH)
    return str(_MODEL_PATH)


@dataclass
class PoseLandmarks:
    """랜드마크 좌표 (17점 COCO 또는 33점 MediaPipe)"""
    landmarks: list[dict] = field(default_factory=list)  # [{x, y, z, visibility}, ...]
    timestamp: float = 0.0
    person_id: str = "person_0"
    bbox: tuple[float, float, float, float] | None = None  # (x_min, y_min, x_max, y_max)
    keypoint_format: str = "mediapipe_33"  # "coco_17" 또는 "mediapipe_33"


@dataclass
class PoseResult:
    """포즈 감지 결과"""
    poses: list[PoseLandmarks] = field(default_factory=list)
    frame: np.ndarray | None = None
    skeleton_frame: np.ndarray | None = None
    fps: float = 0.0
    timestamp: float = 0.0


# 인물별 색상 (초록, 주황, 보라, 파랑, 노랑)
_PERSON_COLORS = [
    ((0, 255, 128), (0, 200, 255)),    # 초록 라인, 노랑 포인트
    ((0, 165, 255), (0, 100, 255)),    # 주황 라인, 빨강 포인트
    ((255, 0, 200), (255, 100, 255)),  # 보라 라인, 핑크 포인트
    ((255, 200, 0), (255, 255, 0)),    # 파랑 라인, 밝은 파랑 포인트
    ((0, 255, 255), (100, 255, 255)),  # 노랑 라인, 밝은 노랑 포인트
]


class PoseService:
    # MediaPipe 33점 랜드마크 연결 (스켈레톤 그리기용)
    POSE_CONNECTIONS = [
        (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),  # 상체
        (11, 23), (12, 24), (23, 24),                         # 몸통
        (23, 25), (25, 27), (24, 26), (26, 28),               # 하체
        (0, 1), (1, 2), (2, 3), (3, 7),                       # 얼굴 왼쪽
        (0, 4), (4, 5), (5, 6), (6, 8),                       # 얼굴 오른쪽
        (15, 17), (15, 19), (16, 18), (16, 20),               # 손
        (27, 29), (27, 31), (28, 30), (28, 32),               # 발
    ]
    # COCO 17점 연결 (YOLO Pose용)
    COCO_CONNECTIONS = [
        (0, 1), (0, 2), (1, 3), (2, 4),                       # 얼굴
        (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),              # 상체+팔
        (5, 11), (6, 12), (11, 12),                           # 몸통
        (11, 13), (13, 15), (12, 14), (14, 16),               # 하체
    ]

    def __init__(self):
        self._landmarker: "mp.tasks.vision.PoseLandmarker | None" = None  # type: ignore[type-arg]
        self._image_landmarker: "mp.tasks.vision.PoseLandmarker | None" = None  # type: ignore[type-arg]
        self._running = False
        self._fps: float = 0.0
        self._frame_count: int = 0

    def _ensure_landmarker(self):
        if self._landmarker is None:
            model_path = _ensure_model()

            BaseOptions = mp.tasks.BaseOptions
            PoseLandmarker = mp.tasks.vision.PoseLandmarker
            PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionRunningMode.VIDEO,
                num_poses=5,
                min_pose_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._landmarker = PoseLandmarker.create_from_options(options)
            logger.info("PoseLandmarker 초기화 완료 (Tasks API, num_poses=5)")

    def process_frame_sync(self, frame: np.ndarray) -> PoseResult:
        """프레임에서 포즈 감지 (동기, to_thread에서 호출)"""
        self._ensure_landmarker()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # 단조 증가 타임스탬프 (밀리초)
        self._frame_count += 1
        timestamp_ms = int(self._frame_count * (1000 / 30))  # ~30fps 기준

        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)  # type: ignore[union-attr]

        pose_result = PoseResult(timestamp=time.time())
        pose_result.frame = frame

        h, w = frame.shape[:2]
        skeleton = np.zeros((h, w, 3), dtype=np.uint8)

        if result.pose_landmarks:
            for person_idx, person_landmarks in enumerate(result.pose_landmarks):
                landmarks_data = []
                xs, ys = [], []
                for lm in person_landmarks:
                    landmarks_data.append({
                        "x": lm.x,
                        "y": lm.y,
                        "z": lm.z,
                        "visibility": lm.visibility if hasattr(lm, "visibility") else 1.0,
                    })
                    xs.append(lm.x)
                    ys.append(lm.y)

                # 바운딩 박스 계산
                bbox = (min(xs), min(ys), max(xs), max(ys))

                pose_lm = PoseLandmarks(
                    landmarks=landmarks_data,
                    timestamp=time.time(),
                    person_id=f"person_{person_idx}",
                    bbox=bbox,
                )
                pose_result.poses.append(pose_lm)

                # 인물별 색상으로 스켈레톤 그리기
                color_idx = person_idx % len(_PERSON_COLORS)
                line_color, point_color = _PERSON_COLORS[color_idx]
                self._draw_skeleton_colored(skeleton, landmarks_data, w, h, line_color, point_color)
                self._draw_skeleton_colored(frame, landmarks_data, w, h, line_color, point_color)

        pose_result.skeleton_frame = skeleton
        pose_result.fps = camera_service.fps

        # MJPEG에 포즈 오버레이된 프레임 반영
        camera_service.update_jpeg_from_processed(frame)

        return pose_result

    def _draw_skeleton_colored(
        self,
        img: np.ndarray,
        landmarks: list[dict],
        w: int,
        h: int,
        line_color: tuple[int, int, int],
        point_color: tuple[int, int, int],
    ):
        """인물별 색상으로 스켈레톤 그리기"""
        points = []
        for lm in landmarks:
            px = int(lm["x"] * w)
            py = int(lm["y"] * h)
            points.append((px, py))

        # 연결선 그리기
        for start_idx, end_idx in self.POSE_CONNECTIONS:
            if start_idx < len(points) and end_idx < len(points):
                s_vis = landmarks[start_idx].get("visibility", 0)
                e_vis = landmarks[end_idx].get("visibility", 0)
                if s_vis > 0.3 and e_vis > 0.3:
                    cv2.line(img, points[start_idx], points[end_idx], line_color, 2)

        # 관절점 그리기
        for i, (px, py) in enumerate(points):
            if landmarks[i].get("visibility", 0) > 0.3:
                cv2.circle(img, (px, py), 4, point_color, -1)

    def draw_coco_skeleton(
        self,
        img: np.ndarray,
        landmarks: list[dict],
        w: int,
        h: int,
        line_color: tuple[int, int, int],
        point_color: tuple[int, int, int],
    ):
        """COCO 17점 스켈레톤 그리기"""
        points = []
        for lm in landmarks:
            px = int(lm["x"] * w)
            py = int(lm["y"] * h)
            points.append((px, py))

        # COCO 연결선 그리기
        for start_idx, end_idx in self.COCO_CONNECTIONS:
            if start_idx < len(points) and end_idx < len(points):
                s_vis = landmarks[start_idx].get("visibility", 0)
                e_vis = landmarks[end_idx].get("visibility", 0)
                if s_vis > 0.3 and e_vis > 0.3:
                    cv2.line(img, points[start_idx], points[end_idx], line_color, 2)

        # 관절점 그리기
        for i, (px, py) in enumerate(points):
            if landmarks[i].get("visibility", 0) > 0.3:
                cv2.circle(img, (px, py), 4, point_color, -1)

    def _ensure_image_landmarker(self):
        """IMAGE 모드용 별도 landmarker (ROI 크롭 분석용)"""
        if self._image_landmarker is None:
            model_path = _ensure_model()

            BaseOptions = mp.tasks.BaseOptions
            PoseLandmarker = mp.tasks.vision.PoseLandmarker
            PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=VisionRunningMode.IMAGE,
                num_poses=1,
                min_pose_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._image_landmarker = PoseLandmarker.create_from_options(options)
            logger.info("PoseLandmarker (IMAGE mode) 초기화 완료")

    def process_roi_sync(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
        person_id: str = "person_0",
    ) -> PoseLandmarks | None:
        """ROI 크롭에서 MediaPipe 33점 추출 (YOLO 하이브리드 파이프라인용)

        Args:
            frame: 원본 BGR 프레임
            bbox: (x1, y1, x2, y2) normalized 좌표
            person_id: 추적 ID

        Returns:
            PoseLandmarks 또는 None (감지 실패 시)
        """
        self._ensure_image_landmarker()
        h, w = frame.shape[:2]

        # 바운딩 박스 좌표 → 픽셀 (패딩 포함)
        pad = 0.1  # 10% 패딩
        bx1 = max(0, int((bbox[0] - pad) * w))
        by1 = max(0, int((bbox[1] - pad) * h))
        bx2 = min(w, int((bbox[2] + pad) * w))
        by2 = min(h, int((bbox[3] + pad) * h))

        roi = frame[by1:by2, bx1:bx2]
        if roi.size == 0:
            return None

        rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = self._image_landmarker.detect(mp_image)  # type: ignore[union-attr]

        if not result.pose_landmarks or len(result.pose_landmarks) == 0:
            return None

        person_landmarks = result.pose_landmarks[0]
        roi_h, roi_w = roi.shape[:2]

        landmarks_data = []
        xs, ys = [], []
        for lm in person_landmarks:
            # ROI 상대 좌표 → 원본 프레임 절대 좌표 (normalized)
            abs_x = (bx1 + lm.x * roi_w) / w
            abs_y = (by1 + lm.y * roi_h) / h
            landmarks_data.append({
                "x": abs_x,
                "y": abs_y,
                "z": lm.z,
                "visibility": lm.visibility if hasattr(lm, "visibility") else 1.0,
            })
            xs.append(abs_x)
            ys.append(abs_y)

        return PoseLandmarks(
            landmarks=landmarks_data,
            timestamp=time.time(),
            person_id=person_id,
            bbox=(min(xs), min(ys), max(xs), max(ys)),
        )

    async def process_frame(self, frame: np.ndarray) -> PoseResult:
        """비동기 래퍼: 스레드 풀에서 포즈 감지 실행"""
        return await asyncio.to_thread(self.process_frame_sync, frame)

    def close(self):
        if self._landmarker:
            self._landmarker.close()
            self._landmarker = None
        if self._image_landmarker:
            self._image_landmarker.close()
            self._image_landmarker = None


# 싱글턴
pose_service = PoseService()
