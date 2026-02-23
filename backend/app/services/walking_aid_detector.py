"""
보행도구 인식 서비스 (Walking Aid Detection)

YOLO11n fine-tuning 모델 + MediaPipe 휴리스틱 하이브리드.
모델 파일이 없어도 서버는 정상 기동됨 (graceful degradation).

Components:
- WalkingAidDetector: YOLO 기반 보행도구 감지
- MediaPipeWalkingAidHeuristic: MediaPipe 랜드마크 기반 휴리스틱 보완
- WalkingAidStateTracker: 인원별 보행도구 상태 관리
"""

import math
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.walking_aid_detector")

# Walking aid class names (must match training)
WALKING_AID_CLASSES = ["walker", "cane", "crutch", "wheelchair"]

# ONNX Runtime availability
_ORT_AVAILABLE: bool | None = None
_ort = None

# ultralytics availability for YOLO inference
_YOLO_AVAILABLE: bool | None = None


def _check_ort_available() -> bool:
    global _ORT_AVAILABLE, _ort
    if _ORT_AVAILABLE is not None:
        return _ORT_AVAILABLE
    try:
        import onnxruntime as ort
        _ort = ort
        _ORT_AVAILABLE = True
    except ImportError:
        _ORT_AVAILABLE = False
    return _ORT_AVAILABLE


def _check_yolo_available() -> bool:
    global _YOLO_AVAILABLE
    if _YOLO_AVAILABLE is not None:
        return _YOLO_AVAILABLE
    try:
        import ultralytics  # noqa: F401
        _YOLO_AVAILABLE = True
    except ImportError:
        _YOLO_AVAILABLE = False
    return _YOLO_AVAILABLE


# ──────────────────────────────────────────────
# 3-1. WalkingAidDetector (YOLO 기반)
# ──────────────────────────────────────────────

@dataclass
class WalkingAidDetection:
    """Single walking aid detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]  # normalized (x1, y1, x2, y2)
    center_xy: tuple[float, float]  # normalized center


class WalkingAidDetector:
    """YOLO11n 기반 보행도구 감지기 (싱글톤).

    모델 파일이 없으면 enabled=False로 빈 결과를 반환합니다.
    """

    def __init__(self):
        self._model = None
        self._enabled: bool | None = None
        self._model_path = Path(__file__).resolve().parent.parent.parent / settings.WALKING_AID_MODEL
        self._confidence = settings.WALKING_AID_CONFIDENCE

    @property
    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        self._ensure_model()
        return self._enabled or False

    def _ensure_model(self) -> None:
        """Lazy-load the ONNX or YOLO model."""
        if self._enabled is not None:
            return

        if not self._model_path.exists():
            self._enabled = False
            logger.warning(
                "Walking aid model not found: %s — walking aid detection disabled",
                self._model_path,
            )
            return

        suffix = self._model_path.suffix.lower()

        if suffix == ".onnx" and _check_ort_available() and _ort is not None:
            try:
                session = _ort.InferenceSession(
                    str(self._model_path),
                    providers=["CPUExecutionProvider"],
                )
                self._model = ("onnx", session)
                self._enabled = True
                logger.info("Walking aid ONNX model loaded: %s", self._model_path)
            except Exception as e:
                self._enabled = False
                logger.warning("Walking aid ONNX model load failed: %s", e)
        elif suffix == ".pt" and _check_yolo_available():
            try:
                from ultralytics import YOLO  # type: ignore[attr-defined]
                model = YOLO(str(self._model_path))
                self._model = ("yolo", model)
                self._enabled = True
                logger.info("Walking aid YOLO model loaded: %s", self._model_path)
            except Exception as e:
                self._enabled = False
                logger.warning("Walking aid YOLO model load failed: %s", e)
        else:
            self._enabled = False
            logger.warning(
                "Walking aid model format not supported or runtime not available: %s",
                self._model_path,
            )

    def detect(self, frame: np.ndarray) -> list[WalkingAidDetection]:
        """Detect walking aids in a frame.

        Args:
            frame: BGR image (OpenCV)

        Returns:
            List of WalkingAidDetection objects.
        """
        if not self.enabled or self._model is None:
            return []

        model_type, model = self._model
        h, w = frame.shape[:2]

        try:
            if model_type == "yolo":
                return self._detect_yolo(model, frame, w, h)
            elif model_type == "onnx":
                return self._detect_onnx(model, frame, w, h)
        except Exception as e:
            logger.warning("Walking aid detection error: %s", e)
        return []

    def _detect_yolo(self, model, frame: np.ndarray, w: int, h: int) -> list[WalkingAidDetection]:
        """Detect using ultralytics YOLO model."""
        results = model(frame, conf=self._confidence, verbose=False)
        detections = []

        if not results or len(results) == 0:
            return detections

        result = results[0]
        if result.boxes is None:
            return detections

        boxes = result.boxes
        for i in range(len(boxes)):
            xyxy = boxes.xyxy[i].cpu().numpy()
            x1, y1, x2, y2 = xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h
            conf = float(boxes.conf[i].item())
            cls_id = int(boxes.cls[i].item())

            if cls_id < 0 or cls_id >= len(WALKING_AID_CLASSES):
                continue

            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            detections.append(WalkingAidDetection(
                class_id=cls_id,
                class_name=WALKING_AID_CLASSES[cls_id],
                confidence=conf,
                bbox_xyxy=(x1, y1, x2, y2),
                center_xy=(cx, cy),
            ))

        return detections

    def _detect_onnx(self, session, frame: np.ndarray, w: int, h: int) -> list[WalkingAidDetection]:
        """Detect using ONNX Runtime session.

        Assumes standard YOLO ONNX output format:
        output[0] shape = (1, N, 4+num_classes) or (1, 4+num_classes, N)
        """
        import cv2

        # Preprocess: resize to 640x640, normalize
        input_size = 640
        img = cv2.resize(frame, (input_size, input_size))
        img = img[:, :, ::-1].astype(np.float32) / 255.0  # BGR -> RGB, normalize
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # Add batch dim

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: img})
        output = outputs[0]  # (1, ?, ?)

        if output.ndim == 3:
            output = output[0]  # Remove batch

        # Handle both (N, 4+nc) and (4+nc, N) formats
        nc = len(WALKING_AID_CLASSES)
        if output.shape[0] == (4 + nc):
            output = output.T  # -> (N, 4+nc)

        detections = []
        for row in output:
            cx_raw, cy_raw, bw, bh = row[0], row[1], row[2], row[3]
            class_scores = row[4:4 + nc]
            cls_id = int(np.argmax(class_scores))
            conf = float(class_scores[cls_id])

            if conf < self._confidence:
                continue

            # Convert from input_size coords to normalized
            x1 = (cx_raw - bw / 2) / input_size
            y1 = (cy_raw - bh / 2) / input_size
            x2 = (cx_raw + bw / 2) / input_size
            y2 = (cy_raw + bh / 2) / input_size
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            detections.append(WalkingAidDetection(
                class_id=cls_id,
                class_name=WALKING_AID_CLASSES[cls_id],
                confidence=conf,
                bbox_xyxy=(x1, y1, x2, y2),
                center_xy=(cx, cy),
            ))

        return detections

    def close(self):
        self._model = None
        self._enabled = None


# ──────────────────────────────────────────────
# 3-2. MediaPipeWalkingAidHeuristic
# ──────────────────────────────────────────────

@dataclass
class HeuristicResult:
    is_probable: bool
    confidence: float
    reason: str


class MediaPipeWalkingAidHeuristic:
    """MediaPipe 랜드마크에서 보행도구 사용 추정 (YOLO 보완).

    조건:
    - 양손(wrist) Y > 엉덩이(hip) Y (손이 엉덩이보다 아래)
    - 양손 X 간격 > 어깨 너비 * 0.8
    - 연속 프레임 유지

    추가 비용 0 (이미 추출된 MediaPipe 랜드마크 재활용).
    """

    # MediaPipe landmark indices
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12

    def __init__(self, consecutive_frames: int = 5):
        self._required_frames = consecutive_frames
        self._person_counts: dict[str, int] = {}  # person_id -> consecutive count

    def estimate(self, landmarks: list[dict], person_id: str = "default") -> HeuristicResult:
        """Estimate walking aid usage from MediaPipe landmarks.

        Args:
            landmarks: list of 33 landmarks, each {x, y, z, visibility}
            person_id: for per-person tracking

        Returns:
            HeuristicResult
        """
        if not settings.WALKING_AID_HEURISTIC_ENABLED:
            return HeuristicResult(is_probable=False, confidence=0.0, reason="heuristic_disabled")

        if not landmarks or len(landmarks) < 25:
            self._person_counts[person_id] = 0
            return HeuristicResult(is_probable=False, confidence=0.0, reason="insufficient_landmarks")

        try:
            lw = landmarks[self.LEFT_WRIST]
            rw = landmarks[self.RIGHT_WRIST]
            lh = landmarks[self.LEFT_HIP]
            rh = landmarks[self.RIGHT_HIP]
            ls = landmarks[self.LEFT_SHOULDER]
            rs = landmarks[self.RIGHT_SHOULDER]
        except (IndexError, KeyError):
            self._person_counts[person_id] = 0
            return HeuristicResult(is_probable=False, confidence=0.0, reason="landmark_access_error")

        # Extract coordinates
        def _get(lm, key):
            if isinstance(lm, dict):
                return lm.get(key, 0.0)
            # If it's a list/tuple [x, y, z, visibility]
            idx = {"x": 0, "y": 1, "z": 2, "visibility": 3}.get(key, 0)
            return lm[idx] if idx < len(lm) else 0.0

        lw_y, rw_y = _get(lw, "y"), _get(rw, "y")
        lh_y, rh_y = _get(lh, "y"), _get(rh, "y")
        lw_x, rw_x = _get(lw, "x"), _get(rw, "x")
        ls_x, rs_x = _get(ls, "x"), _get(rs, "x")

        # Check visibility
        min_vis = 0.5
        lw_vis = _get(lw, "visibility")
        rw_vis = _get(rw, "visibility")
        if lw_vis < min_vis or rw_vis < min_vis:
            self._person_counts[person_id] = 0
            return HeuristicResult(is_probable=False, confidence=0.0, reason="low_visibility")

        hip_y = (lh_y + rh_y) / 2
        shoulder_width = abs(ls_x - rs_x)
        wrist_spread = abs(lw_x - rw_x)

        # Condition 1: Both wrists below hips (Y increases downward in image coords)
        wrists_below_hips = lw_y > hip_y and rw_y > hip_y

        # Condition 2: Wrist spread > shoulder width * 0.8
        spread_wide = wrist_spread > shoulder_width * 0.8 if shoulder_width > 0.01 else False

        if wrists_below_hips and spread_wide:
            count = self._person_counts.get(person_id, 0) + 1
            self._person_counts[person_id] = count

            if count >= self._required_frames:
                conf = min(0.7, 0.4 + (count - self._required_frames) * 0.05)
                return HeuristicResult(
                    is_probable=True,
                    confidence=conf,
                    reason="wrists_below_hips_and_wide_spread",
                )
            else:
                return HeuristicResult(
                    is_probable=False,
                    confidence=0.2,
                    reason=f"building_confidence ({count}/{self._required_frames})",
                )
        else:
            self._person_counts[person_id] = 0
            return HeuristicResult(is_probable=False, confidence=0.0, reason="conditions_not_met")

    def reset_person(self, person_id: str) -> None:
        self._person_counts.pop(person_id, None)

    def cleanup(self, active_ids: set[str]) -> None:
        stale = set(self._person_counts.keys()) - active_ids
        for pid in stale:
            del self._person_counts[pid]


# ──────────────────────────────────────────────
# 3-3. WalkingAidStateTracker
# ──────────────────────────────────────────────

@dataclass
class WalkingAidState:
    """Per-person walking aid state."""
    aid_type: str | None = None  # "walker", "cane", "crutch", "wheelchair", or None
    detection_count: int = 0
    missing_count: int = 0
    established: bool = False
    last_seen_frame: int = 0
    is_missing: bool = False  # True when established aid goes missing
    type_votes: dict = field(default_factory=dict)  # class_name → count (다수결 투표)


class WalkingAidStateTracker:
    """인원별 보행도구 상태 관리.

    - YOLO 감지 + MediaPipe 휴리스틱으로 보행도구 확인
    - detection_count >= ESTABLISH_FRAMES → established
    - established + missing_count >= MISSING_FRAMES → aid_missing 이벤트
    """

    def __init__(self):
        self._states: dict[str, WalkingAidState] = {}
        self._establish_frames = settings.WALKING_AID_ESTABLISH_FRAMES
        self._missing_frames = settings.WALKING_AID_MISSING_FRAMES
        self._assoc_dist = settings.WALKING_AID_ASSOC_DIST

    def get_state(self, person_id: str) -> WalkingAidState:
        if person_id not in self._states:
            self._states[person_id] = WalkingAidState()
        return self._states[person_id]

    def update(
        self,
        person_id: str,
        person_center: tuple[float, float] | None,
        yolo_detections: list[WalkingAidDetection],
        mp_heuristic: HeuristicResult | None,
        frame_num: int,
    ) -> WalkingAidState:
        """Update walking aid state for a person.

        Args:
            person_id: tracked person ID
            person_center: normalized (cx, cy) of person bbox, or None
            yolo_detections: all walking aid detections in the frame
            mp_heuristic: MediaPipe heuristic result for this person
            frame_num: current frame number

        Returns:
            Updated WalkingAidState
        """
        state = self.get_state(person_id)

        # Match person to closest walking aid detection
        matched_aid = self._match_person_to_aid(person_center, yolo_detections)

        if matched_aid is not None:
            # Walking aid detected near this person — 다수결 투표
            state.type_votes[matched_aid.class_name] = state.type_votes.get(matched_aid.class_name, 0) + 1
            # 가장 많이 감지된 타입을 aid_type으로 설정
            state.aid_type = max(state.type_votes, key=lambda k: state.type_votes.get(k, 0))
            state.detection_count += 1
            state.missing_count = 0
            state.last_seen_frame = frame_num
            state.is_missing = False
        elif mp_heuristic is not None and mp_heuristic.is_probable:
            # MediaPipe heuristic suggests walking aid usage
            if state.aid_type is None:
                state.aid_type = "walker"  # Heuristic can't distinguish type, assume walker
            state.detection_count += 1
            state.missing_count = 0
            state.last_seen_frame = frame_num
            state.is_missing = False
        elif mp_heuristic is None:
            # YOLO-only 모드: MediaPipe 휴리스틱 없음
            # YOLO 감지 간헐적 → missing 임계값 3배 증가 (더 관대하게)
            if state.established:
                state.missing_count += 1
                if state.missing_count >= self._missing_frames * 3:
                    state.is_missing = True
        else:
            # No walking aid detected (MediaPipe heuristic available but negative)
            if state.established:
                state.missing_count += 1
                if state.missing_count >= self._missing_frames:
                    state.is_missing = True

        # Check if walking aid use is established
        if not state.established and state.detection_count >= self._establish_frames:
            state.established = True
            logger.info(
                "Walking aid established: person=%s, type=%s",
                person_id, state.aid_type,
            )

        return state

    def _match_person_to_aid(
        self,
        person_center: tuple[float, float] | None,
        detections: list[WalkingAidDetection],
    ) -> WalkingAidDetection | None:
        """Match a person to the highest-confidence walking aid within range."""
        if person_center is None or not detections:
            return None

        px, py = person_center
        best_det = None
        best_conf = 0.0

        for det in detections:
            dx = det.center_xy[0] - px
            dy = det.center_xy[1] - py
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= self._assoc_dist and det.confidence > best_conf:
                best_conf = det.confidence
                best_det = det

        return best_det

    def cleanup(self, active_person_ids: set[str]) -> None:
        """Remove states for persons no longer tracked."""
        stale = set(self._states.keys()) - active_person_ids
        for pid in stale:
            del self._states[pid]

    def count_established(self) -> int:
        """Count persons with established walking aid use."""
        return sum(1 for s in self._states.values() if s.established)

    def get_missing_alerts(self) -> list[tuple[str, WalkingAidState]]:
        """Get persons with missing walking aids."""
        return [
            (pid, state)
            for pid, state in self._states.items()
            if state.established and state.is_missing
        ]


# ──────────────────────────────────────────────
# Singletons
# ──────────────────────────────────────────────

walking_aid_detector = WalkingAidDetector()
walking_aid_heuristic = MediaPipeWalkingAidHeuristic()
walking_aid_tracker = WalkingAidStateTracker()
