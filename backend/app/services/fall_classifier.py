"""
ONNX Transformer 기반 낙상 분류기

30프레임 시퀀스를 입력받아 낙상 확률을 출력합니다.
ONNX 모델이 없으면 graceful degradation으로 기본 점수 0.0을 반환합니다.

5클래스 분류 지원 (v2):
  출력 1개: sigmoid binary (기존 모델 호환)
  출력 2개: softmax binary 호환 [정상, 낙상]
  출력 4개: 4클래스 softmax [normal, front_fall, back_fall, side_fall]
  출력 5개: 5클래스 softmax [normal, front_fall, back_fall, side_fall, pre_impact]
"""

from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.logging_config import get_logger

logger = get_logger("app.services.fall_classifier")

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
# GRU 모델 우선 (Recall 84.3%, Precision 97.0%)
_ONNX_MODEL_PATH_GRU = _MODEL_DIR / "fall_classifier_gru.onnx"
_ONNX_MODEL_PATH_V2 = _MODEL_DIR / "fall_classifier_v2.onnx"
_ONNX_MODEL_PATH_V1 = _MODEL_DIR / "fall_classifier.onnx"

# ONNX Runtime 가용 여부
_ORT_AVAILABLE: bool | None = None
_ort = None

# 5클래스 매핑 (v2: pre_impact 추가)
_CLASS_NAMES = {
    0: "normal",
    1: "front_fall",
    2: "back_fall",
    3: "side_fall",
    4: "pre_impact",
}


def _check_ort_available() -> bool:
    global _ORT_AVAILABLE, _ort
    if _ORT_AVAILABLE is not None:
        return _ORT_AVAILABLE
    try:
        import onnxruntime as ort
        _ort = ort
        _ORT_AVAILABLE = True
        logger.info("onnxruntime %s 감지됨", ort.__version__)
    except ImportError:
        _ORT_AVAILABLE = False
        logger.info("onnxruntime 미설치 - ML 분류기 비활성화")
    return _ORT_AVAILABLE


@dataclass
class FallPrediction:
    """5클래스 분류 결과"""
    fall_probability: float  # 전체 낙상/전조 확률 (1.0 - P(normal))
    fall_type: str           # "normal", "front_fall", "back_fall", "side_fall", "pre_impact"
    class_probabilities: dict[str, float]  # 클래스별 확률
    is_pre_impact: bool = False  # Pre-impact 감지 여부


class FallClassifier:
    """ONNX 기반 낙상 분류기 (싱글톤)

    30프레임 시퀀스의 33개 랜드마크(x, y, z) = (30, 99) 입력 텐서를 사용합니다.

    ONNX 출력 자동 감지:
      - 출력 1개: sigmoid binary (기존 모델 호환)
      - 출력 2개: softmax binary [정상, 낙상]
      - 출력 4개: 4클래스 softmax [normal, front_fall, back_fall, side_fall]
    """

    SEQUENCE_LENGTH = 30
    LANDMARKS_DIM = 33 * 3  # x, y, z for 33 landmarks = 99

    def __init__(self):
        self._session = None
        self._enabled = False
        self._initialized = False
        self._output_dim = 0  # 모델 출력 차원 (1, 2, 4)
        # person별 시퀀스 버퍼
        # 주의: add_frame()과 _run_inference()는 동일 스레드(ml-worker)에서
        # fall_detector.detect() 내부에서 순차 호출됩니다.
        # 스레드 간 동시 접근 시에는 Lock이 필요합니다.
        self._buffers: dict[str, deque] = {}

    @property
    def enabled(self) -> bool:
        if not self._initialized:
            self._initialized = True
            # GRU 우선 (최고 성능) → v2 → v1 폴백
            model_path = None
            if _check_ort_available():
                if _ONNX_MODEL_PATH_GRU.exists():
                    model_path = _ONNX_MODEL_PATH_GRU
                elif _ONNX_MODEL_PATH_V2.exists():
                    model_path = _ONNX_MODEL_PATH_V2
                elif _ONNX_MODEL_PATH_V1.exists():
                    model_path = _ONNX_MODEL_PATH_V1

            if model_path is not None:
                try:
                    # GPU 사용 가능하면 CUDAExecutionProvider 우선, 아니면 CPU 폴백
                    available_providers = _ort.get_available_providers()  # type: ignore[union-attr]
                    if "CUDAExecutionProvider" in available_providers:
                        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                        logger.info("GRU 분류기: CUDA GPU 사용")
                    else:
                        providers = ["CPUExecutionProvider"]
                        logger.info("GRU 분류기: CPU 사용 (CUDA 미설치)")

                    # ONNX Runtime 세션 최적화 (정확도 영향 없음, 그래프 최적화만)
                    import os
                    sess_options = _ort.SessionOptions()  # type: ignore[union-attr]
                    sess_options.graph_optimization_level = _ort.GraphOptimizationLevel.ORT_ENABLE_ALL  # type: ignore[union-attr]
                    cpu_count = os.cpu_count() or 4
                    sess_options.intra_op_num_threads = max(1, cpu_count // 2)
                    sess_options.inter_op_num_threads = max(1, cpu_count // 4)
                    sess_options.execution_mode = _ort.ExecutionMode.ORT_SEQUENTIAL  # type: ignore[union-attr]

                    self._session = _ort.InferenceSession(  # type: ignore[union-attr]
                        str(model_path),
                        sess_options=sess_options,
                        providers=providers,
                    )
                    # 출력 차원 감지
                    output_shape = self._session.get_outputs()[0].shape
                    self._output_dim = output_shape[-1] if len(output_shape) > 1 else 1
                    self._enabled = True
                    logger.info(
                        "낙상 분류기 ONNX 모델 로드 완료: %s (output_dim=%d)",
                        model_path, self._output_dim,
                    )
                except Exception as e:
                    logger.warning("ONNX 모델 로드 실패: %s", e)
                    self._enabled = False
            else:
                self._enabled = False
                logger.info(
                    "ONNX 모델 미발견 (GRU: %s, v2: %s, v1: %s) - ML 분류기 비활성화. "
                    "규칙 기반 감지만 사용합니다.",
                    _ONNX_MODEL_PATH_GRU, _ONNX_MODEL_PATH_V2, _ONNX_MODEL_PATH_V1,
                )
        return self._enabled

    @property
    def output_dim(self) -> int:
        """모델 출력 차원 (1, 2, 4)"""
        return self._output_dim

    def _get_buffer(self, person_id: str) -> deque:
        if person_id not in self._buffers:
            self._buffers[person_id] = deque(maxlen=self.SEQUENCE_LENGTH)
        return self._buffers[person_id]

    def add_frame(self, person_id: str, landmarks: list[dict]) -> None:
        """프레임 랜드마크를 시퀀스 버퍼에 추가"""
        if len(landmarks) < 33:
            return

        frame_vec = []
        for lm in landmarks[:33]:
            frame_vec.extend([lm.get("x", 0.0), lm.get("y", 0.0), lm.get("z", 0.0)])

        buf = self._get_buffer(person_id)
        buf.append(frame_vec)

    def _run_inference(self, person_id: str) -> np.ndarray | None:
        """ONNX 추론 실행, raw 출력 반환

        Returns:
            output array 또는 None (버퍼 부족/비활성화)
        """
        if not self.enabled or self._session is None:
            return None

        buf = self._get_buffer(person_id)
        if len(buf) < self.SEQUENCE_LENGTH:
            return None

        # (30, 99) -> (1, 30, 99) float32 텐서
        sequence = np.array(list(buf), dtype=np.float32)
        input_tensor = sequence.reshape(1, self.SEQUENCE_LENGTH, self.LANDMARKS_DIM)

        try:
            input_name = self._session.get_inputs()[0].name
            output_name = self._session.get_outputs()[0].name
            result = self._session.run([output_name], {input_name: input_tensor})
            return result[0][0]  # type: ignore[index]  # (output_dim,) or scalar
        except Exception as e:
            logger.error("ONNX 추론 실패: %s", e)
            return None

    def predict_detailed(self, person_id: str) -> FallPrediction:
        """5클래스 확률 + fall_type 반환

        ONNX 출력 자동 감지:
          출력 1개 → sigmoid binary (기존 모델 호환)
          출력 2개 → softmax binary [정상, 낙상]
          출력 4개 → 4클래스 softmax [normal, front_fall, back_fall, side_fall]
          출력 5개 → 5클래스 softmax [normal, ..., pre_impact]

        Returns:
            FallPrediction with fall_probability, fall_type, class_probabilities, is_pre_impact
        """
        default = FallPrediction(
            fall_probability=0.0,
            fall_type="normal",
            class_probabilities={name: 0.0 for name in _CLASS_NAMES.values()},
        )
        default.class_probabilities["normal"] = 1.0

        output = self._run_inference(person_id)
        if output is None:
            return default

        output = np.atleast_1d(output)
        n_outputs = len(output)

        if n_outputs == 1:
            # sigmoid binary: output[0] = 낙상 확률
            # binary 모델은 방향 구분 불가 → "unknown" (WARNING 단계 정상 표시)
            fall_prob = float(np.clip(output[0], 0.0, 1.0))
            return FallPrediction(
                fall_probability=fall_prob,
                fall_type="unknown" if fall_prob >= 0.5 else "normal",
                class_probabilities={
                    "normal": 1.0 - fall_prob,
                    "front_fall": fall_prob,
                    "back_fall": 0.0,
                    "side_fall": 0.0,
                    "pre_impact": 0.0,
                },
            )

        elif n_outputs == 2:
            # softmax binary: [P(normal), P(fall)]
            # binary 모델은 방향 구분 불가 → "unknown"
            probs = output.astype(float)
            fall_prob = float(np.clip(probs[1], 0.0, 1.0))
            return FallPrediction(
                fall_probability=fall_prob,
                fall_type="unknown" if fall_prob >= 0.5 else "normal",
                class_probabilities={
                    "normal": float(probs[0]),
                    "front_fall": float(probs[1]),
                    "back_fall": 0.0,
                    "side_fall": 0.0,
                    "pre_impact": 0.0,
                },
            )

        else:
            # 4 또는 5클래스 softmax
            probs = output[:min(n_outputs, 5)].astype(float)
            normal_prob = float(np.clip(probs[0], 0.0, 1.0))
            fall_prob = 1.0 - normal_prob

            class_probs = {}
            for i, name in _CLASS_NAMES.items():
                if i < len(probs):
                    class_probs[name] = float(probs[i])
                else:
                    class_probs[name] = 0.0

            # Pre-impact 감지 여부
            pre_impact_prob = class_probs.get("pre_impact", 0.0)
            is_pre_impact = pre_impact_prob > 0.3  # 30% 이상이면 전조 감지

            # fall_type 결정: pre_impact 또는 가장 높은 낙상 유형
            if fall_prob >= 0.5:
                if is_pre_impact and pre_impact_prob >= max(
                    class_probs.get("front_fall", 0),
                    class_probs.get("back_fall", 0),
                    class_probs.get("side_fall", 0),
                ):
                    fall_type = "pre_impact"
                else:
                    fall_classes = {
                        k: v for k, v in class_probs.items()
                        if k not in ("normal", "pre_impact")
                    }
                    fall_type = max(fall_classes, key=lambda k: fall_classes.get(k, 0)) if fall_classes else "front_fall"
            else:
                fall_type = "pre_impact" if is_pre_impact else "normal"

            return FallPrediction(
                fall_probability=fall_prob,
                fall_type=fall_type,
                class_probabilities=class_probs,
                is_pre_impact=is_pre_impact,
            )

    def predict(self, person_id: str) -> float:
        """시퀀스에서 낙상 확률 예측 (기존 시그니처 호환)

        Returns:
            float: 낙상 확률 (0.0 ~ 1.0), 모델 미사용 시 0.0
        """
        result = self.predict_detailed(person_id)
        return result.fall_probability

    def reset_person(self, person_id: str) -> None:
        """인물 시퀀스 버퍼 초기화"""
        self._buffers.pop(person_id, None)

    def reset_camera(self, camera_id: str) -> None:
        """특정 카메라의 버퍼만 초기화 (캐시는 보존)"""
        prefix = f"{camera_id}_"
        to_remove = [pid for pid in self._buffers if pid.startswith(prefix)]
        for pid in to_remove:
            del self._buffers[pid]

    def reset_all(self) -> None:
        """모든 버퍼 초기화"""
        self._buffers.clear()


# 싱글톤
fall_classifier = FallClassifier()
