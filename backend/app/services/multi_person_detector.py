"""
YOLO11 다중 인원 감지기

YOLO11n-pose 모델과 ByteTrack을 사용하여 N명의 인원을 추적합니다.
ultralytics 미설치 시 graceful degradation으로 기존 MediaPipe 파이프라인을 유지합니다.
"""

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.core.logging_config import get_logger

logger = get_logger("app.services.multi_person_detector")

# YOLO 가용 여부 확인 (lazy import)
_YOLO_AVAILABLE: bool | None = None
_ultralytics = None


def _check_yolo_available() -> bool:
    global _YOLO_AVAILABLE, _ultralytics
    if _YOLO_AVAILABLE is not None:
        return _YOLO_AVAILABLE
    try:
        import ultralytics
        _ultralytics = ultralytics
        _YOLO_AVAILABLE = True
        logger.info("ultralytics %s 감지됨 - YOLO 모드 활성화", ultralytics.__version__)
    except ImportError:
        _YOLO_AVAILABLE = False
        logger.info("ultralytics 미설치 - MediaPipe-only 폴백 모드")
    return _YOLO_AVAILABLE


@dataclass
class DetectedPerson:
    """YOLO로 감지된 인원"""
    track_id: int
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) normalized
    confidence: float
    keypoints: np.ndarray | None = None  # (17, 3) COCO keypoints if pose model


@dataclass
class YOLODetectionResult:
    """YOLO 감지 결과"""
    persons: list[DetectedPerson] = field(default_factory=list)
    frame: np.ndarray | None = None
    inference_time_ms: float = 0.0


# ByteTrack 설정 파일 경로
_BYTETRACK_CONFIG = Path(__file__).resolve().parent.parent.parent / "bytetrack.yaml"

# YOLO 모델 경로
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
_YOLO_MODEL_NAME = "yolo11s-pose.pt"


class MultiPersonDetector:
    """YOLO11 기반 다중 인원 감지기 (싱글톤)"""

    def __init__(self):
        self._model = None
        self._enabled = False
        self._initialized = False
        self._device = "cpu"  # 초기화 시 결정
        # 카메라별 ByteTrack 트래커 상태 격리 (다중 카메라 시 track ID 안정화)
        self._camera_trackers: dict[str, list] = {}
        self._tracker_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """YOLO 사용 가능 여부"""
        if not self._initialized:
            self._initialized = True
            self._enabled = _check_yolo_available()
        return self._enabled

    @property
    def device(self) -> str:
        """현재 사용 중인 디바이스"""
        return self._device

    def _resolve_model_path(self, base_name: str) -> tuple[Path, str]:
        """환경에 따라 최적 모델 형식 자동 선택

        GPU → .pt (CUDA + FP16 최적)
        CPU → .onnx (onnxruntime 그래프 최적화, 같은 가중치라 정확도 동일)

        Returns:
            (model_path, format_label)
        """
        pt_path = _MODEL_DIR / base_name
        onnx_name = base_name.replace(".pt", ".onnx")
        onnx_path = _MODEL_DIR / onnx_name

        if self._device == "cuda":
            # GPU: .pt가 CUDA + FP16 최적
            if pt_path.exists():
                return pt_path, "pt(CUDA)"
            if onnx_path.exists():
                return onnx_path, "onnx(CUDA fallback)"
        else:
            # CPU: .onnx가 onnxruntime 그래프 최적화로 ~2배 빠름
            if onnx_path.exists():
                return onnx_path, "onnx(CPU optimized)"
            if pt_path.exists():
                return pt_path, "pt(CPU fallback)"

        return pt_path, "pt(default)"

    def _ensure_model(self):
        """모델 lazy-load + GPU/CPU 자동 최적화"""
        if self._model is not None:
            return

        if not self.enabled:
            return

        from ultralytics import YOLO  # type: ignore[attr-defined]
        from app.config import settings

        # 디바이스 결정 (한 번만)
        try:
            import torch
            if settings.YOLO_USE_GPU and torch.cuda.is_available():
                self._device = "cuda"
                logger.info("CUDA GPU 사용 가능: %s", torch.cuda.get_device_name(0))
            else:
                self._device = "cpu"
                if settings.YOLO_USE_GPU:
                    logger.warning("YOLO_USE_GPU=true이지만 CUDA 미설치 또는 GPU 없음")
        except ImportError:
            self._device = "cpu"

        # 환경에 따라 최적 모델 형식 자동 선택
        model_path, fmt_label = self._resolve_model_path(_YOLO_MODEL_NAME)

        if model_path.exists():
            self._model = YOLO(str(model_path))
            logger.info("YOLO 모델 로드: %s [%s]", model_path.name, fmt_label)
        else:
            # 자동 다운로드
            logger.info("YOLO 모델 다운로드 중...")
            _MODEL_DIR.mkdir(parents=True, exist_ok=True)
            self._model = YOLO("yolo11n-pose.pt")
            try:
                import shutil
                downloaded = Path("yolo11n-pose.pt")
                if downloaded.exists():
                    shutil.move(str(downloaded), str(_MODEL_DIR / _YOLO_MODEL_NAME))
            except Exception:
                pass

        # GPU + FP16 (half precision) 워밍업 - 첫 추론에서 GPU 메모리 할당
        if self._device == "cuda":
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            _ = self._model.predict(dummy, device=self._device, half=True, imgsz=480, verbose=False)
            logger.info("YOLO GPU 워밍업 완료 (device=%s, half=True, imgsz=480)", self._device)
        else:
            # CPU ONNX: onnxruntime 스레드 최적화 힌트
            import os
            cpu_count = os.cpu_count() or 4
            # onnxruntime이 CPU 코어를 효율적으로 사용하도록 설정
            os.environ.setdefault("OMP_NUM_THREADS", str(max(1, cpu_count // 2)))
            os.environ.setdefault("OMP_WAIT_POLICY", "ACTIVE")
            logger.info("YOLO CPU 로드 완료 [%s] (OMP_NUM_THREADS=%s)", fmt_label, os.environ.get("OMP_NUM_THREADS"))

    def reload_model(self, model_name: str) -> bool:
        """모델 교체 및 리로드 (환경에 따라 최적 형식 자동 선택)"""
        global _YOLO_MODEL_NAME
        try:
            # 환경에 따라 최적 형식 선택
            model_path, fmt_label = self._resolve_model_path(model_name)
            if not model_path.exists():
                logger.error("모델 파일이 존재하지 않습니다: %s", model_name)
                return False

            from ultralytics import YOLO  # type: ignore[attr-defined]
            logger.info("모델 교체 시작: %s -> %s [%s]", _YOLO_MODEL_NAME, model_path.name, fmt_label)

            # 기존 모델 해제
            self._model = None

            # 새 모델 로드
            _YOLO_MODEL_NAME = model_name
            self._model = YOLO(str(model_path))

            # 워밍업
            if self._device == "cuda":
                dummy = np.zeros((480, 640, 3), dtype=np.uint8)
                _ = self._model.predict(dummy, device=self._device, half=True, imgsz=480, verbose=False)

            logger.info("모델 교체 완료: %s [%s]", model_path.name, fmt_label)
            return True
        except Exception as e:
            logger.error("모델 교체 실패: %s", e)
            return False

    @property
    def current_model(self) -> str:
        return _YOLO_MODEL_NAME

    def detect(self, frame: np.ndarray, camera_id: str = "cam0") -> YOLODetectionResult:
        """프레임에서 인원 감지 + 추적

        Args:
            frame: BGR 이미지 (OpenCV)
            camera_id: 카메라 ID (카메라별 트래커 상태 격리)

        Returns:
            YOLODetectionResult: 감지된 인원 목록
        """
        if not self.enabled:
            return YOLODetectionResult(frame=frame)

        self._ensure_model()
        if self._model is None:
            return YOLODetectionResult(frame=frame)

        start = time.time()
        h, w = frame.shape[:2]

        # ByteTrack 추적기로 실행
        tracker_config = str(_BYTETRACK_CONFIG) if _BYTETRACK_CONFIG.exists() else "bytetrack.yaml"

        # 카메라별 트래커 상태 복원/저장 (다중 카메라 시 track ID 안정화)
        # 단일 YOLO 모델을 공유하되, ByteTrack 트래커는 카메라별 격리
        # 이전: 4카메라가 하나의 트래커를 공유 → 매 사이클 track ID 변경 → GRU 버퍼 리셋 → 낙상 놓침
        # 이후: 카메라별 트래커 분리 → track ID 안정 → GRU 30프레임 버퍼 유지 → 정확한 감지
        with self._tracker_lock:
            # 트래커 상태 복원
            if hasattr(self._model, "predictor") and self._model.predictor is not None:
                if camera_id in self._camera_trackers:
                    self._model.predictor.trackers = self._camera_trackers[camera_id]
                elif hasattr(self._model.predictor, "trackers"):
                    # 새 카메라: 기존 트래커 속성 삭제 → track()이 새 트래커 자동 생성
                    del self._model.predictor.trackers

            # GPU + FP16 + 고정 입력 크기 (속도 최적화)
            results = self._model.track(
                frame,
                persist=True,
                tracker=tracker_config,
                conf=0.5,
                iou=0.5,
                verbose=False,
                device=self._device,
                half=(self._device == "cuda"),  # GPU일 때만 FP16
                imgsz=480,  # 입력 크기 축소로 속도 향상
            )

            # 트래커 상태 저장
            if hasattr(self._model, "predictor") and self._model.predictor is not None:
                self._camera_trackers[camera_id] = self._model.predictor.trackers

        inference_ms = (time.time() - start) * 1000
        detection_result = YOLODetectionResult(
            frame=frame,
            inference_time_ms=inference_ms,
        )

        if not results or len(results) == 0:
            logger.debug("[YOLO] 감지 결과 없음 (%.1fms)", inference_ms)
            return detection_result

        result = results[0]
        if result.boxes is None:
            logger.debug("[YOLO] boxes=None (%.1fms)", inference_ms)
            return detection_result

        boxes = result.boxes
        for i in range(len(boxes)):
            # 바운딩 박스 (normalized)
            xyxy = boxes.xyxy[i].cpu().numpy()
            x1, y1, x2, y2 = xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h

            # 트랙 ID
            track_id = int(boxes.id[i].item()) if boxes.id is not None else i

            # 신뢰도
            conf = float(boxes.conf[i].item())

            # 키포인트 (pose 모델인 경우)
            kpts = None
            if result.keypoints is not None and i < len(result.keypoints):
                kpts = result.keypoints[i].data.cpu().numpy()  # type: ignore[union-attr]  # (1, 17, 3)
                if kpts.ndim == 3:
                    kpts = kpts[0]  # (17, 3)

            detection_result.persons.append(DetectedPerson(
                track_id=track_id,
                bbox=(x1, y1, x2, y2),
                confidence=conf,
                keypoints=kpts,
            ))

        logger.debug(
            "[YOLO] %d명 감지 (%.1fms) | %s",
            len(detection_result.persons),
            inference_ms,
            ", ".join(
                f"ID:{p.track_id}({p.confidence:.0%})"
                for p in detection_result.persons
            ),
        )

        return detection_result

    def close(self):
        """리소스 해제"""
        self._model = None


# 싱글톤
multi_person_detector = MultiPersonDetector()
