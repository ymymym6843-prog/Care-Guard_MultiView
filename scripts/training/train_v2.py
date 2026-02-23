"""
SENTIO 낙상 감지 Transformer 모델 학습 v2

v1 (train_transformer.py) 대비 개선점:
  1. 전이학습(Transfer Learning) 지원: 기존 4클래스 모델 가중치 로드
  2. 파인튜닝(Fine-tuning): Transformer 인코더 동결 → 분류 헤드만 학습
  3. Pre-impact 가중 손실함수: 낙상 전조 구간에 높은 가중치 부여
  4. Focal Loss: 클래스 불균형 대응
  5. 5클래스 분류: Normal, Front/Back/Side Fall, Pre-impact
  6. 혼합 데이터셋: AI Hub + Pre-VFall 통합 학습
  7. Temporal Attention: 시간축 가중 평균 (단순 GAP 대체)

5클래스 분류:
  0: Normal (비낙상)
  1: Front Fall (전면 낙상)
  2: Back Fall (후면 낙상)
  3: Side Fall (측면 낙상)
  4: Pre-impact (낙상 전조)

Usage:
    # 5클래스 전이학습 (4클래스 기존 모델에서 시작)
    python scripts/training/train_v2.py \\
        --data D:/merged_landmarks.npz \\
        --pretrained backend/models/fall_classifier.onnx \\
        --output backend/models/fall_classifier_v2.onnx \\
        --num-classes 5 \\
        --epochs 30 \\
        --fine-tune \\
        --freeze-epochs 5

    # Pre-impact 가중 학습 (처음부터)
    python scripts/training/train_v2.py \\
        --data D:/merged_landmarks.npz \\
        --output backend/models/fall_classifier_v2.onnx \\
        --num-classes 5 \\
        --pre-impact-weight 3.0 \\
        --focal-loss

    # 4클래스 모드 (v1 호환, Pre-impact 없이)
    python scripts/training/train_v2.py \\
        --data D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \\
        --output backend/models/fall_classifier.onnx \\
        --num-classes 4 \\
        --epochs 30 --kfold 5
"""

import argparse
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset

try:
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import classification_report, confusion_matrix
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

CLASS_NAMES_4 = ["normal", "front_fall", "back_fall", "side_fall"]
CLASS_NAMES_5 = ["normal", "front_fall", "back_fall", "side_fall", "pre_impact"]


# ──────────────────────────────────────────────────────
# 손실 함수
# ──────────────────────────────────────────────────────

class PreImpactWeightedLoss(nn.Module):
    """
    Pre-impact 가중 Cross-Entropy 손실 함수

    낙상 전조(Pre-impact) 구간에 높은 가중치를 부여하여
    모델이 낙상이 발생하기 *전*에 위험을 감지하도록 유도합니다.

    의료 관점:
      - 낙상 감지보다 낙상 예방이 훨씬 중요
      - Pre-impact 감지 → 사전 경고 → 개입 시간 확보
      - False negative (pre-impact 놓침)의 비용 > False positive

    Args:
        num_classes: 클래스 수 (4 또는 5)
        pre_impact_weight: Pre-impact 클래스 가중치 (기본 3.0)
        fall_weight: 낙상 클래스 가중치 (기본 1.5)
        normal_weight: 정상 클래스 가중치 (기본 1.0)
    """

    def __init__(
        self,
        num_classes: int = 5,
        pre_impact_weight: float = 1.5,
        fall_weight: float = 1.5,
        side_fall_weight: float = 3.0,
        normal_weight: float = 1.0,
    ):
        super().__init__()
        self.num_classes = num_classes

        # 클래스별 가중치 벡터
        weights = torch.ones(num_classes)
        weights[0] = normal_weight       # Normal
        weights[1] = fall_weight         # Front Fall
        weights[2] = fall_weight         # Back Fall
        weights[3] = side_fall_weight    # Side Fall (가장 약한 클래스 → 가중치 강화)
        if num_classes >= 5:
            weights[4] = pre_impact_weight   # Pre-impact (과도한 recall 방지 위해 완화)

        self.register_buffer("weights", weights)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """
        Args:
            logits: (batch, num_classes) raw logits
            targets: (batch,) 클래스 인덱스

        Returns:
            weighted cross-entropy loss
        """
        return F.cross_entropy(logits, targets, weight=self.weights)


class FocalLoss(nn.Module):
    """
    Focal Loss for 클래스 불균형 대응

    잘 분류되는 easy examples의 가중치를 줄이고,
    어려운 hard examples (특히 pre-impact)에 집중합니다.

    FL(p_t) = -alpha_t * (1 - p_t)^gamma * log(p_t)

    Args:
        num_classes: 클래스 수
        alpha: 클래스별 가중치 (None이면 uniform)
        gamma: focusing parameter (기본 2.0, 클수록 hard example에 집중)
        pre_impact_weight: Pre-impact 클래스 추가 가중치
    """

    def __init__(
        self,
        num_classes: int = 5,
        alpha: torch.Tensor | None = None,
        gamma: float = 2.0,
        pre_impact_weight: float = 1.5,
        side_fall_weight: float = 3.0,
    ):
        super().__init__()
        self.gamma = gamma
        self.num_classes = num_classes

        if alpha is None:
            alpha = torch.ones(num_classes)
            alpha[0] = 1.0      # Normal
            alpha[1] = 1.5      # Front Fall
            alpha[2] = 1.5      # Back Fall
            alpha[3] = side_fall_weight  # Side Fall (가장 약한 클래스 강화)
            if num_classes >= 5:
                alpha[4] = pre_impact_weight  # Pre-impact (완화)

        self.register_buffer("alpha", alpha)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = F.softmax(logits, dim=-1)
        targets_one_hot = F.one_hot(targets, self.num_classes).float()

        # 정답 클래스의 확률
        p_t = (probs * targets_one_hot).sum(dim=-1)

        # Focal weight: (1 - p_t)^gamma
        focal_weight = (1.0 - p_t) ** self.gamma

        # Alpha weight: 클래스별 가중치
        alpha_t = self.alpha[targets]

        # Cross-entropy
        ce = -torch.log(p_t.clamp(min=1e-8))

        loss = alpha_t * focal_weight * ce
        return loss.mean()


# ──────────────────────────────────────────────────────
# 모델 아키텍처 (v2 - Temporal Attention 추가)
# ──────────────────────────────────────────────────────

class PositionalEncoding(nn.Module):
    """시간 위치 인코딩"""

    def __init__(self, d_model: int, max_len: int = 100, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        if d_model % 2 == 1:
            pe[:, 1::2] = torch.cos(position * div_term[:-1])
        else:
            pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class TemporalAttentionPool(nn.Module):
    """
    시간축 어텐션 풀링

    단순 Global Average Pooling 대신, 각 프레임의 중요도를
    학습하여 가중 평균을 계산합니다.

    낙상 전조/낙상 순간 프레임에 더 높은 가중치를 자동으로 부여.
    """

    def __init__(self, d_model: int):
        super().__init__()
        self.attention = nn.Sequential(
            nn.Linear(d_model, d_model // 4),
            nn.Tanh(),
            nn.Linear(d_model // 4, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len, d_model)
        Returns:
            pooled: (batch, d_model) - 어텐션 가중 평균
        """
        # 어텐션 스코어: (batch, seq_len, 1)
        scores = self.attention(x)
        weights = F.softmax(scores, dim=1)  # (batch, seq_len, 1)

        # 가중 평균
        pooled = (x * weights).sum(dim=1)  # (batch, d_model)
        return pooled


class FallDetectionTransformerV2(nn.Module):
    """
    경량 Transformer 기반 낙상 감지 모델 v2

    v1 대비 변경:
      - TemporalAttentionPool 추가 (GAP 대체 가능)
      - 5클래스 지원 (Pre-impact 추가)
      - 전이학습 호환 설계

    아키텍처:
        Input (30, 99)
        → Linear(99→d_model) → PositionalEncoding
        → TransformerEncoder(2 layers, 4 heads)
        → TemporalAttentionPool 또는 GAP
        → Classifier Head (LayerNorm → FC → GELU → Dropout → FC)

    전이학습 시:
        - input_proj, pos_encoder, transformer: 기존 가중치 로드
        - classifier: 새로 초기화 (차원 확장)
    """

    def __init__(
        self,
        input_dim: int = 99,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 256,
        dropout: float = 0.2,
        num_classes: int = 5,
        use_temporal_attention: bool = True,
    ):
        super().__init__()
        self.num_classes = num_classes
        self.use_temporal_attention = use_temporal_attention

        # 입력 프로젝션 (v1과 동일)
        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model, max_len=100, dropout=dropout)

        # Transformer 인코더 (v1과 동일)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # 시간축 풀링
        if use_temporal_attention:
            self.temporal_pool = TemporalAttentionPool(d_model)
        else:
            self.temporal_pool = None

        # 분류 헤드
        out_dim = 1 if num_classes <= 2 else num_classes
        self.classifier = nn.Sequential(
            nn.LayerNorm(d_model),
            nn.Linear(d_model, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, out_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, seq_len=30, features=99)
        Returns:
            num_classes<=2: (batch, 1) sigmoid
            num_classes>2: (batch, num_classes) raw logits
        """
        x = self.input_proj(x)       # (B, 30, d_model)
        x = self.pos_encoder(x)      # (B, 30, d_model)
        x = self.transformer(x)      # (B, 30, d_model)

        # 시간축 풀링
        if self.temporal_pool is not None:
            x = self.temporal_pool(x)  # (B, d_model) - attention weighted
        else:
            x = x.mean(dim=1)         # (B, d_model) - GAP

        x = self.classifier(x)       # (B, out_dim)

        if self.num_classes <= 2:
            return torch.sigmoid(x)
        return x  # raw logits


class SoftmaxWrapper(nn.Module):
    """ONNX 내보내기 시 softmax 적용 래퍼"""

    def __init__(self, model: FallDetectionTransformerV2):
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.model(x)
        if self.model.num_classes <= 2:
            return logits
        return torch.softmax(logits, dim=-1)


# ──────────────────────────────────────────────────────
# 전이학습 유틸리티
# ──────────────────────────────────────────────────────

def load_pretrained_weights(
    model: FallDetectionTransformerV2,
    pretrained_path: str,
    strict: bool = False,
) -> list[str]:
    """
    기존 모델(v1 또는 이전 ONNX)에서 가중치를 로드합니다.

    전략:
      - input_proj, pos_encoder, transformer: 완전 로드
      - classifier: shape 일치하면 로드, 불일치하면 새로 초기화
      - temporal_pool: v2 전용 → 항상 새로 초기화

    Args:
        model: 대상 모델 (v2)
        pretrained_path: .pth 또는 .onnx 경로
        strict: True면 모든 키 일치 필수

    Returns:
        loaded_keys: 로드된 파라미터 키 목록
    """
    ext = Path(pretrained_path).suffix.lower()

    if ext == ".onnx":
        return _load_from_onnx(model, pretrained_path)
    elif ext in (".pth", ".pt"):
        return _load_from_pytorch(model, pretrained_path, strict)
    else:
        print(f"지원하지 않는 파일 형식: {ext}")
        return []


def _load_from_pytorch(
    model: FallDetectionTransformerV2,
    pth_path: str,
    strict: bool = False,
) -> list[str]:
    """PyTorch 체크포인트에서 가중치 로드"""
    state_dict = torch.load(pth_path, map_location="cpu", weights_only=True)

    # SoftmaxWrapper 안의 모델인 경우 접두사 제거
    cleaned = {}
    for k, v in state_dict.items():
        if k.startswith("model."):
            cleaned[k[6:]] = v
        else:
            cleaned[k] = v

    loaded = []
    skipped = []

    model_sd = model.state_dict()
    for key, param in cleaned.items():
        if key in model_sd:
            if model_sd[key].shape == param.shape:
                model_sd[key].copy_(param)
                loaded.append(key)
            else:
                skipped.append(f"{key}: shape {param.shape} → {model_sd[key].shape}")
        else:
            skipped.append(f"{key}: 모델에 없음")

    if loaded:
        model.load_state_dict(model_sd)

    print(f"  전이학습 로드: {len(loaded)}/{len(cleaned)} 파라미터")
    if skipped:
        print(f"  건너뛴 파라미터: {len(skipped)}")
        for s in skipped[:5]:
            print(f"    - {s}")

    return loaded


def _load_from_onnx(
    model: FallDetectionTransformerV2,
    onnx_path: str,
) -> list[str]:
    """
    ONNX 모델에서 간접적으로 가중치 전이

    ONNX에서 직접 PyTorch state_dict를 추출하기 어려우므로,
    기존 v1 모델 아키텍처를 재생성하여 ONNX와 동일한 가중치를 구성합니다.

    실제로는 .pth 체크포인트 사용이 권장됩니다.
    """
    print(f"  ONNX 기반 전이학습은 제한적입니다.")
    print(f"  권장: 학습 시 --save-checkpoint 로 .pth 파일을 저장하세요.")
    print(f"  ONNX 경로: {onnx_path}")

    # ONNX에서 가중치 추출 시도
    try:
        import onnx
        from onnx import numpy_helper

        onnx_model = onnx.load(onnx_path)
        onnx_weights = {}
        for initializer in onnx_model.graph.initializer:
            onnx_weights[initializer.name] = numpy_helper.to_array(initializer)

        print(f"  ONNX 가중치 {len(onnx_weights)}개 발견")

        # 이름 매핑 시도 (ONNX export 시 이름이 변환됨)
        # 완벽한 매핑은 어려우므로, 공통 패턴만 시도
        loaded = []
        model_sd = model.state_dict()

        for onnx_name, onnx_param in onnx_weights.items():
            # 간단한 이름 매핑 시도
            for model_key, model_param in model_sd.items():
                if model_param.shape == onnx_param.shape:
                    # shape 일치하는 첫 번째 미매핑 파라미터에 할당
                    if model_key not in loaded:
                        model_sd[model_key].copy_(torch.tensor(onnx_param))
                        loaded.append(model_key)
                        break

        if loaded:
            model.load_state_dict(model_sd)
            print(f"  ONNX에서 {len(loaded)}개 파라미터 전이 성공")
        else:
            print(f"  ONNX 가중치 매핑 실패 - 처음부터 학습합니다")

        return loaded

    except ImportError:
        print(f"  onnx 패키지 미설치 (pip install onnx)")
        return []
    except Exception as e:
        print(f"  ONNX 로드 실패: {e}")
        return []


def freeze_backbone(model: FallDetectionTransformerV2):
    """Transformer 인코더를 동결 (분류 헤드만 학습)"""
    frozen = 0
    for name, param in model.named_parameters():
        if any(prefix in name for prefix in ["input_proj", "pos_encoder", "transformer"]):
            param.requires_grad = False
            frozen += 1

    trainable = sum(1 for p in model.parameters() if p.requires_grad)
    total = sum(1 for p in model.parameters())
    print(f"  동결: {frozen}/{total} 파라미터 (학습 가능: {trainable})")


def unfreeze_all(model: FallDetectionTransformerV2):
    """모든 파라미터 학습 가능으로 전환"""
    for param in model.parameters():
        param.requires_grad = True
    trainable = sum(1 for p in model.parameters() if p.requires_grad)
    print(f"  전체 해동: {trainable} 파라미터 학습 가능")


# ──────────────────────────────────────────────────────
# 학습 유틸리티
# ──────────────────────────────────────────────────────

def load_data(npz_path: str) -> tuple[np.ndarray, np.ndarray]:
    """추출된 랜드마크 데이터 로드"""
    data = np.load(npz_path)
    X = data["X"]
    y = data["y"]
    return X, y


def balance_classes(
    X: np.ndarray,
    y: np.ndarray,
    seed: int = 42,
    oversample_minority: bool = False,
    max_per_class: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    클래스 균형 맞추기

    Args:
        oversample_minority: True면 소수 클래스 오버샘플링,
                            False면 다수 클래스 언더샘플링
        max_per_class: 오버샘플링 시 클래스당 최대 샘플 수 (0=무제한)
                       메모리 절약을 위해 다수 클래스도 이 수로 제한
    """
    rng = np.random.RandomState(seed)

    unique_classes = np.unique(y)
    class_indices = {c: np.where(y == c)[0] for c in unique_classes}

    if oversample_minority:
        # 오버샘플링: 타겟 크기 결정
        max_count = max(len(idx) for idx in class_indices.values())
        if max_per_class > 0:
            target_count = min(max_count, max_per_class)
        else:
            target_count = max_count
        balanced_indices = []
        for c in unique_classes:
            idx = class_indices[c]
            if len(idx) < target_count:
                # 부족한 만큼 복제
                extra = rng.choice(idx, target_count - len(idx), replace=True)
                idx = np.concatenate([idx, extra])
            elif len(idx) > target_count:
                # 다수 클래스 다운샘플
                idx = rng.choice(idx, target_count, replace=False)
            balanced_indices.append(idx)
    else:
        # 언더샘플링: 최소 클래스 크기에 맞춤
        min_count = min(len(idx) for idx in class_indices.values())
        balanced_indices = []
        for c in unique_classes:
            idx = class_indices[c]
            if len(idx) > min_count:
                idx = rng.choice(idx, min_count, replace=False)
            balanced_indices.append(idx)

    indices = np.concatenate(balanced_indices)
    rng.shuffle(indices)

    return X[indices], y[indices]


def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    """1 에포크 학습 (multiclass)"""
    model.train()
    total_loss = 0
    correct = 0
    total = 0

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device).long()

        optimizer.zero_grad()
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item() * len(X_batch)
        preds = logits.argmax(dim=1)
        correct += (preds == y_batch).sum().item()
        total += len(X_batch)

    return total_loss / total, correct / total


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    num_classes: int = 5,
) -> tuple[float, float, np.ndarray, np.ndarray]:
    """평가 (loss, accuracy, preds, labels)"""
    model.eval()
    total_loss = 0
    all_preds = []
    all_labels = []

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device).long()

        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        total_loss += loss.item() * len(X_batch)

        preds = logits.argmax(dim=1)
        all_preds.append(preds.cpu().numpy())
        all_labels.append(y_batch.cpu().numpy())

    all_preds = np.concatenate(all_preds)
    all_labels = np.concatenate(all_labels)
    total = len(all_labels)

    accuracy = (all_preds == all_labels).sum() / total

    return total_loss / total, accuracy, all_preds, all_labels


def compute_macro_f1(preds: np.ndarray, labels: np.ndarray, num_classes: int) -> float:
    """매크로 F1 스코어 계산"""
    f1s = []
    for c in range(num_classes):
        tp = ((preds == c) & (labels == c)).sum()
        fp = ((preds == c) & (labels != c)).sum()
        fn = ((preds != c) & (labels == c)).sum()
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        f1s.append(f1)
    return float(np.mean(f1s))


def export_onnx(model: nn.Module, output_path: str, device: torch.device, num_classes: int = 5):
    """PyTorch 모델을 ONNX로 변환"""
    if num_classes > 2:
        export_model = SoftmaxWrapper(model)
    else:
        export_model = model

    export_model.eval()
    dummy_input = torch.randn(1, 30, 99).to(device)

    torch.onnx.export(
        export_model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
    )
    print(f"\nONNX 모델 저장: {output_path}")
    print(f"  파일 크기: {os.path.getsize(output_path) / 1024:.1f} KB")


# ──────────────────────────────────────────────────────
# 메인 학습 루프
# ──────────────────────────────────────────────────────

def train_model(
    X: np.ndarray,
    y: np.ndarray,
    args,
    device: torch.device,
    fold_label: str = "",
) -> tuple[nn.Module, float]:
    """학습 루프 (전이학습 + 파인튜닝 지원)"""

    # 모델 생성
    model = FallDetectionTransformerV2(
        input_dim=99,
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.num_layers,
        dim_feedforward=args.d_model * 2,
        dropout=0.2,
        num_classes=args.num_classes,
        use_temporal_attention=args.temporal_attention,
    ).to(device)

    # 전이학습: 기존 가중치 로드
    if args.pretrained:
        print(f"\n전이학습: {args.pretrained}")
        load_pretrained_weights(model, args.pretrained)

    # 파인튜닝: backbone 동결
    is_fine_tuning = args.fine_tune and args.pretrained
    if is_fine_tuning:
        print("\n파인튜닝 모드: Transformer 인코더 동결")
        freeze_backbone(model)

    # 데이터 준비
    X_tensor = torch.tensor(X, dtype=torch.float32)
    y_tensor = torch.tensor(y, dtype=torch.long)
    dataset = TensorDataset(X_tensor, y_tensor)

    val_size = int(len(dataset) * args.val_ratio)
    train_size = len(dataset) - val_size
    train_ds, val_ds = torch.utils.data.random_split(
        dataset, [train_size, val_size],
        generator=torch.Generator().manual_seed(args.seed),
    )

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=0)

    if fold_label:
        print(f"\n  [{fold_label}] Train: {train_size}, Val: {val_size}")

    # 손실 함수 선택
    side_w = getattr(args, "side_fall_weight", 3.0)
    if args.focal_loss:
        criterion = FocalLoss(
            num_classes=args.num_classes,
            gamma=args.focal_gamma,
            pre_impact_weight=args.pre_impact_weight,
            side_fall_weight=side_w,
        ).to(device)
        print(f"  손실 함수: Focal Loss (gamma={args.focal_gamma}, pre-impact={args.pre_impact_weight}, side_fall={side_w})")
    elif args.pre_impact_weight != 1.0 or args.num_classes >= 5:
        criterion = PreImpactWeightedLoss(
            num_classes=args.num_classes,
            pre_impact_weight=args.pre_impact_weight,
            side_fall_weight=side_w,
        ).to(device)
        print(f"  손실 함수: Pre-impact Weighted CE (pre-impact={args.pre_impact_weight}, side_fall={side_w})")
    else:
        criterion = nn.CrossEntropyLoss().to(device)
        print(f"  손실 함수: Cross-Entropy (균등 가중치)")

    # 옵티마이저
    optimizer = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=args.lr,
        weight_decay=1e-4,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # 학습 루프
    best_f1 = 0.0
    best_epoch = 0
    best_state = None
    patience_counter = 0

    for epoch in range(1, args.epochs + 1):
        # 파인튜닝: freeze_epochs 후 전체 해동
        if is_fine_tuning and epoch == args.freeze_epochs + 1:
            print(f"\n  Epoch {epoch}: Backbone 해동 (전체 학습 시작)")
            unfreeze_all(model)
            # 옵티마이저 재생성 (새 파라미터 포함)
            optimizer = torch.optim.AdamW(
                model.parameters(), lr=args.lr * 0.1, weight_decay=1e-4,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=args.epochs - epoch + 1,
            )

        train_loss, train_acc = train_one_epoch(
            model, train_loader, criterion, optimizer, device,
        )
        val_loss, val_acc, val_preds, val_labels = evaluate(
            model, val_loader, criterion, device, args.num_classes,
        )
        val_f1 = compute_macro_f1(val_preds, val_labels, args.num_classes)

        scheduler.step()
        lr = scheduler.get_last_lr()[0]

        if val_f1 > best_f1:
            best_f1 = val_f1
            best_epoch = epoch
            patience_counter = 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            patience_counter += 1

        if not fold_label or (epoch % 5 == 0 or epoch == 1 or patience_counter >= args.patience):
            prefix = f"  [{fold_label}] " if fold_label else ""
            marker = " *" if epoch == best_epoch else ""
            frozen_tag = " [frozen]" if is_fine_tuning and epoch <= args.freeze_epochs else ""
            print(
                f"{prefix}{epoch:3d}/{args.epochs} | "
                f"T-Loss={train_loss:.4f} T-Acc={train_acc:.1%} | "
                f"V-Loss={val_loss:.4f} V-Acc={val_acc:.1%} F1={val_f1:.4f} | "
                f"LR={lr:.2e}{marker}{frozen_tag}"
            )

        if patience_counter >= args.patience:
            msg = f"Early stopping at epoch {epoch} (patience={args.patience})"
            if fold_label:
                print(f"  [{fold_label}] {msg}")
            else:
                print(f"\n{msg}")
            break

    # 베스트 모델 로드
    if best_state:
        model.load_state_dict(best_state)

    # 최종 메트릭 출력
    if _SKLEARN_AVAILABLE:
        val_loss, val_acc, val_preds, val_labels = evaluate(
            model, val_loader, criterion, device, args.num_classes,
        )
        class_names = CLASS_NAMES_5[:args.num_classes] if args.num_classes >= 5 else CLASS_NAMES_4[:args.num_classes]
        prefix_str = f"[{fold_label}] " if fold_label else ""
        print(f"\n  {prefix_str}Per-class 메트릭 (Best epoch={best_epoch}, F1={best_f1:.4f}):")
        print(classification_report(val_labels, val_preds, target_names=class_names, digits=4))
        print("  Confusion Matrix:")
        cm = confusion_matrix(val_labels, val_preds)
        header = "        " + " ".join(f"{n[:8]:>10}" for n in class_names)
        print(header)
        for i, row in enumerate(cm):
            print(f"  {class_names[i][:8]:>8} " + " ".join(f"{v:>10}" for v in row))
        print()

    return model, best_f1


def main():
    parser = argparse.ArgumentParser(description="SENTIO Transformer v2 (전이학습 + Pre-impact)")
    parser.add_argument("--data", type=str, required=True, help=".npz 데이터 파일 경로")
    parser.add_argument("--output", type=str, default="backend/models/fall_classifier_v2.onnx")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--nhead", type=int, default=4)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=7)
    parser.add_argument("--num-classes", type=int, default=5,
                        help="분류 클래스 수 (4=기존, 5=Pre-impact 포함)")

    # 전이학습
    parser.add_argument("--pretrained", type=str, default="",
                        help="기존 모델 경로 (.pth 또는 .onnx)")
    parser.add_argument("--fine-tune", action="store_true",
                        help="파인튜닝 모드 (backbone 동결 후 점진적 해동)")
    parser.add_argument("--freeze-epochs", type=int, default=5,
                        help="backbone 동결 에포크 수")

    # 손실 함수
    parser.add_argument("--pre-impact-weight", type=float, default=1.5,
                        help="Pre-impact 클래스 손실 가중치 (3.0→1.5 완화, 과도한 recall 감소)")
    parser.add_argument("--focal-loss", action="store_true", default=True,
                        help="Focal Loss 사용 (기본: ON)")
    parser.add_argument("--no-focal-loss", action="store_true",
                        help="Focal Loss 비활성화")
    parser.add_argument("--focal-gamma", type=float, default=2.0,
                        help="Focal Loss gamma (클수록 hard example 집중)")
    parser.add_argument("--side-fall-weight", type=float, default=3.0,
                        help="Side Fall 클래스 손실 가중치 (가장 약한 클래스 강화)")

    # 모델 변형
    parser.add_argument("--temporal-attention", action="store_true", default=True,
                        help="Temporal Attention Pooling 사용 (기본: ON)")
    parser.add_argument("--no-temporal-attention", action="store_true",
                        help="GAP 사용 (v1 호환)")

    # 클래스 균형
    parser.add_argument("--oversample", action="store_true", default=True,
                        help="소수 클래스 오버샘플링 (기본: ON, 데이터 손실 방지)")
    parser.add_argument("--no-oversample", action="store_true",
                        help="언더샘플링 사용 (오버샘플링 비활성화)")
    parser.add_argument("--max-per-class", type=int, default=80000,
                        help="오버샘플링 시 클래스당 최대 샘플 수 (메모리 제어, 기본: 80000)")

    # K-Fold CV
    parser.add_argument("--kfold", type=int, default=0,
                        help="K-Fold CV (0=비활성화)")

    # 체크포인트
    parser.add_argument("--save-checkpoint", type=str, default="",
                        help="PyTorch 체크포인트 저장 경로 (.pth)")

    # 벤치마크
    parser.add_argument("--benchmark", action="store_true")

    args = parser.parse_args()

    if args.no_temporal_attention:
        args.temporal_attention = False
    if args.no_focal_loss:
        args.focal_loss = False
    if args.no_oversample:
        args.oversample = False

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    class_names = CLASS_NAMES_5 if args.num_classes >= 5 else CLASS_NAMES_4

    print(f"{'='*70}")
    print(f"SENTIO Fall Detection Transformer v2")
    print(f"{'='*70}")
    print(f"Device: {device}")
    print(f"Classes: {args.num_classes} ({', '.join(class_names[:args.num_classes])})")
    print(f"Temporal Attention: {'ON' if args.temporal_attention else 'OFF (GAP)'}")
    if args.pretrained:
        print(f"Transfer Learning: {args.pretrained}")
    if args.fine_tune:
        print(f"Fine-tuning: freeze {args.freeze_epochs} epochs → unfreeze")
    print(f"Oversample: {'ON' if args.oversample else 'OFF (undersample)'}")
    if args.focal_loss:
        print(f"Loss: Focal (gamma={args.focal_gamma}, pre-impact={args.pre_impact_weight}, side_fall={args.side_fall_weight})")
    else:
        print(f"Loss: Weighted CE (pre-impact={args.pre_impact_weight}, side_fall={args.side_fall_weight})")

    if args.kfold > 0 and not _SKLEARN_AVAILABLE:
        print("WARNING: scikit-learn 미설치 - K-Fold CV 비활성화")
        args.kfold = 0

    # 데이터 로드
    print(f"\n데이터 로드: {args.data}")
    X, y = load_data(args.data)
    print(f"  원본: X={X.shape}")
    unique, counts = np.unique(y, return_counts=True)
    for cls, cnt in zip(unique, counts):
        name = class_names[cls] if cls < len(class_names) else f"class_{cls}"
        print(f"    {name} ({cls}): {cnt}")

    # 클래스 균형
    X, y = balance_classes(
        X, y, seed=args.seed,
        oversample_minority=args.oversample,
        max_per_class=args.max_per_class,
    )
    print(f"  균형 후: X={X.shape}")
    unique, counts = np.unique(y, return_counts=True)
    for cls, cnt in zip(unique, counts):
        name = class_names[cls] if cls < len(class_names) else f"class_{cls}"
        print(f"    {name} ({cls}): {cnt}")

    # 모델 파라미터 표시
    temp_model = FallDetectionTransformerV2(
        input_dim=99, d_model=args.d_model, nhead=args.nhead,
        num_layers=args.num_layers, dim_feedforward=args.d_model * 2,
        num_classes=args.num_classes,
        use_temporal_attention=args.temporal_attention,
    )
    total_params = sum(p.numel() for p in temp_model.parameters())
    print(f"\n모델 파라미터: {total_params:,} ({total_params * 4 / 1024:.1f} KB)")
    del temp_model

    # K-Fold CV
    if args.kfold >= 2:
        print(f"\n{'='*70}")
        print(f"K-Fold Cross Validation (K={args.kfold})")
        print(f"{'='*70}")

        skf = StratifiedKFold(n_splits=args.kfold, shuffle=True, random_state=args.seed)
        fold_f1s = []

        for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            fold_label = f"Fold {fold_idx + 1}/{args.kfold}"
            print(f"\n{'─'*50}")
            print(f"  {fold_label}")
            print(f"{'─'*50}")

            _, fold_f1 = train_model(X[train_idx], y[train_idx], args, device, fold_label)
            fold_f1s.append(fold_f1)

        fold_f1s = np.array(fold_f1s)
        print(f"\n{'='*70}")
        print(f"K-Fold CV 결과 ({args.kfold} folds):")
        for i, f1 in enumerate(fold_f1s):
            print(f"  Fold {i+1}: F1={f1:.4f}")
        print(f"  평균 F1: {fold_f1s.mean():.4f} +/- {fold_f1s.std():.4f}")
        print(f"{'='*70}")

    # 최종 모델 학습
    print(f"\n{'='*70}")
    print(f"최종 모델 학습 (전체 데이터)")
    print(f"{'='*70}")

    model, best_f1 = train_model(X, y, args, device)
    print(f"\n최종 Best F1: {best_f1:.4f}")

    # 체크포인트 저장 (.pth - 전이학습용)
    if args.save_checkpoint:
        os.makedirs(os.path.dirname(args.save_checkpoint) or ".", exist_ok=True)
        torch.save(model.state_dict(), args.save_checkpoint)
        print(f"체크포인트 저장: {args.save_checkpoint}")

    # ONNX 변환
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    export_onnx(model.cpu(), args.output, torch.device("cpu"), args.num_classes)

    # ONNX 검증
    try:
        import onnxruntime as ort
        session = ort.InferenceSession(args.output)
        dummy = np.random.randn(1, 30, 99).astype(np.float32)
        result = session.run(None, {"input": dummy})
        print(f"  ONNX 검증 성공: output shape={result[0].shape}")
        if args.num_classes > 2:
            print(f"    softmax 합: {result[0].sum():.4f} (기대값: 1.0)")
            print(f"    클래스별 확률: {result[0][0]}")
    except ImportError:
        print("  (onnxruntime 미설치 - ONNX 검증 스킵)")

    # 벤치마크
    if args.benchmark:
        _run_benchmark(args.output)

    print(f"\n학습 완료! 모델: {args.output}")


def _run_benchmark(onnx_path: str, num_runs: int = 200):
    """ONNX 추론 벤치마크"""
    try:
        import onnxruntime as ort
    except ImportError:
        print("onnxruntime 미설치 - 벤치마크 스킵")
        return

    print(f"\n{'='*60}")
    print(f"추론 벤치마크 ({num_runs}회)")
    print(f"{'='*60}")

    providers_to_test = [("CPUExecutionProvider", "CPU")]
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        providers_to_test.append(("CUDAExecutionProvider", "GPU (CUDA)"))

    dummy = np.random.randn(1, 30, 99).astype(np.float32)

    for provider, label in providers_to_test:
        try:
            session = ort.InferenceSession(onnx_path, providers=[provider])
        except Exception as e:
            print(f"  {label}: 세션 생성 실패 ({e})")
            continue

        input_name = session.get_inputs()[0].name

        for _ in range(10):
            session.run(None, {input_name: dummy})

        times = []
        for _ in range(num_runs):
            t0 = time.perf_counter()
            session.run(None, {input_name: dummy})
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)

        times = np.array(times)
        print(f"\n  {label}:")
        print(f"    평균: {times.mean():.3f} ms")
        print(f"    P95:  {np.percentile(times, 95):.3f} ms")
        print(f"    P99:  {np.percentile(times, 99):.3f} ms")

        result = session.run(None, {input_name: dummy})
        print(f"    출력 shape: {result[0].shape}")
        print(f"    출력 합: {result[0].sum():.4f}")


if __name__ == "__main__":
    main()
