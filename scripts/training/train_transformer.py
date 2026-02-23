"""
SENTIO 낙상 감지 Transformer 모델 학습

extract_landmarks.py로 추출한 .npz 데이터를 사용하여
경량 Transformer 모델을 학습하고 ONNX로 변환합니다.

4클래스 분류 지원:
  0: Normal (비낙상)
  1: Front Fall (전면 낙상)
  2: Back Fall (후면 낙상)
  3: Side Fall (측면 낙상)

모델 입력: (batch, 30, 99)  - 30프레임 x 33랜드마크 x 3좌표
모델 출력: (batch, 4)       - 4클래스 softmax 확률

Usage:
    # 4클래스 학습
    python scripts/training/train_transformer.py \
        --data D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
        --output backend/models/fall_classifier.onnx \
        --num-classes 4 \
        --epochs 30 \
        --batch-size 64 \
        --kfold 5

    # 기존 binary 학습 (호환)
    python scripts/training/train_transformer.py \
        --data D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
        --output backend/models/fall_classifier.onnx \
        --num-classes 1 \
        --epochs 30

    # 추론 벤치마크
    python scripts/training/train_transformer.py \
        --data D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
        --output backend/models/fall_classifier.onnx \
        --benchmark
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
from torch.utils.data import DataLoader, TensorDataset, Subset

# scikit-learn (optional, for K-Fold CV and classification_report)
try:
    from sklearn.model_selection import StratifiedKFold
    from sklearn.metrics import classification_report, confusion_matrix
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False

CLASS_NAMES = ["normal", "front_fall", "back_fall", "side_fall"]


# ──────────────────────────────────────────────────────
# 모델 아키텍처
# ──────────────────────────────────────────────────────

class PositionalEncoding(nn.Module):
    """시간 위치 인코딩 (30프레임 시퀀스의 순서 정보 제공)"""

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
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class FallDetectionTransformer(nn.Module):
    """
    경량 Transformer 기반 낙상 감지 모델

    아키텍처:
        Input (30, 99) → Linear(99→d_model) → PositionalEncoding
        → TransformerEncoder(2 layers) → GlobalAvgPool → FC

    num_classes=1: Binary (sigmoid), 출력 (batch, 1)
    num_classes=4: 4-class (logits, no activation), 출력 (batch, 4)
    """

    def __init__(
        self,
        input_dim: int = 99,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 2,
        dim_feedforward: int = 256,
        dropout: float = 0.2,
        num_classes: int = 4,
    ):
        super().__init__()
        self.num_classes = num_classes

        self.input_proj = nn.Linear(input_dim, d_model)
        self.pos_encoder = PositionalEncoding(d_model, max_len=100, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
            activation="gelu",
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

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
            num_classes=1: (batch, 1) sigmoid 확률
            num_classes=4: (batch, 4) raw logits
        """
        x = self.input_proj(x)       # (B, 30, d_model)
        x = self.pos_encoder(x)      # (B, 30, d_model)
        x = self.transformer(x)      # (B, 30, d_model)
        x = x.mean(dim=1)            # (B, d_model) - global average pooling
        x = self.classifier(x)       # (B, out_dim)

        if self.num_classes <= 2:
            return torch.sigmoid(x)
        return x  # raw logits for CrossEntropyLoss


class SoftmaxWrapper(nn.Module):
    """ONNX 내보내기 시 softmax 적용 래퍼

    학습 시에는 raw logits + CrossEntropyLoss를 사용하고,
    ONNX 추론 시에는 softmax를 적용합니다.
    출력: (batch, num_classes), 합=1.0
    """

    def __init__(self, model: FallDetectionTransformer):
        super().__init__()
        self.model = model

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.model(x)
        if self.model.num_classes <= 2:
            return logits  # already sigmoid
        return torch.softmax(logits, dim=-1)


# ──────────────────────────────────────────────────────
# 학습 유틸리티
# ──────────────────────────────────────────────────────

def load_data(npz_path: str) -> tuple[np.ndarray, np.ndarray]:
    """추출된 랜드마크 데이터 로드"""
    data = np.load(npz_path)
    X = data["X"]  # (N, 30, 99)
    y = data["y"]  # (N,)
    return X, y


def balance_classes(X: np.ndarray, y: np.ndarray, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """클래스 균형 맞추기 (언더샘플링, 다클래스 지원)"""
    rng = np.random.RandomState(seed)

    unique_classes = np.unique(y)
    class_indices = {c: np.where(y == c)[0] for c in unique_classes}
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


def train_one_epoch_binary(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, float]:
    """1 에포크 학습 (binary)"""
    model.train()
    total_loss = 0
    correct = 0
    total = 0

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device).float().unsqueeze(1)

        optimizer.zero_grad()
        output = model(X_batch)
        loss = criterion(output, y_batch)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        total_loss += loss.item() * len(X_batch)
        preds = (output >= 0.5).float()
        correct += (preds == y_batch).sum().item()
        total += len(X_batch)

    return total_loss / total, correct / total


def train_one_epoch_multiclass(
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
def evaluate_binary(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> tuple[float, float, float, float, float]:
    """평가 binary (loss, accuracy, precision, recall, f1)"""
    model.eval()
    total_loss = 0
    all_preds = []
    all_labels = []

    for X_batch, y_batch in loader:
        X_batch = X_batch.to(device)
        y_batch = y_batch.to(device).float().unsqueeze(1)

        output = model(X_batch)
        loss = criterion(output, y_batch)
        total_loss += loss.item() * len(X_batch)

        preds = (output >= 0.5).float()
        all_preds.append(preds.cpu())
        all_labels.append(y_batch.cpu())

    all_preds = torch.cat(all_preds)
    all_labels = torch.cat(all_labels)
    total = len(all_labels)

    accuracy = (all_preds == all_labels).float().mean().item()

    tp = ((all_preds == 1) & (all_labels == 1)).sum().item()
    fp = ((all_preds == 1) & (all_labels == 0)).sum().item()
    fn = ((all_preds == 0) & (all_labels == 1)).sum().item()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return total_loss / total, accuracy, precision, recall, f1


@torch.no_grad()
def evaluate_multiclass(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    num_classes: int = 4,
) -> tuple[float, float, np.ndarray, np.ndarray]:
    """평가 multiclass (loss, accuracy, all_preds, all_labels)"""
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


def export_onnx(model: nn.Module, output_path: str, device: torch.device, num_classes: int = 4):
    """PyTorch 모델을 ONNX로 변환 (SoftmaxWrapper 적용)"""
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


def run_benchmark(onnx_path: str, num_runs: int = 200):
    """ONNX 추론 벤치마크 (CPU/GPU별 평균/P95/P99 측정)"""
    try:
        import onnxruntime as ort
    except ImportError:
        print("onnxruntime 미설치 - 벤치마크 스킵")
        return

    print(f"\n{'='*60}")
    print(f"추론 벤치마크 ({num_runs}회)")
    print(f"{'='*60}")

    providers_to_test = [("CPUExecutionProvider", "CPU")]

    # GPU 가용 여부 확인
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

        # 워밍업
        for _ in range(10):
            session.run(None, {input_name: dummy})

        # 벤치마크
        times = []
        for _ in range(num_runs):
            t0 = time.perf_counter()
            session.run(None, {input_name: dummy})
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000)  # ms

        times = np.array(times)
        print(f"\n  {label}:")
        print(f"    평균: {times.mean():.3f} ms")
        print(f"    P50:  {np.percentile(times, 50):.3f} ms")
        print(f"    P95:  {np.percentile(times, 95):.3f} ms")
        print(f"    P99:  {np.percentile(times, 99):.3f} ms")
        print(f"    최대: {times.max():.3f} ms")

        # 출력 형태 확인
        result = session.run(None, {input_name: dummy})
        print(f"    출력 shape: {result[0].shape}")
        print(f"    출력 합: {result[0].sum():.4f}")


# ──────────────────────────────────────────────────────
# 메인 학습 루프
# ──────────────────────────────────────────────────────

def train_single_split(
    X: np.ndarray,
    y: np.ndarray,
    args,
    device: torch.device,
    fold_label: str = "",
) -> tuple[nn.Module, float]:
    """단일 train/val 분할에 대한 학습 루프

    Returns:
        (best_model, best_f1)
    """
    is_multiclass = args.num_classes > 2

    # PyTorch 텐서 변환
    X_tensor = torch.tensor(X, dtype=torch.float32)
    y_tensor = torch.tensor(y, dtype=torch.long)

    dataset = TensorDataset(X_tensor, y_tensor)

    # Train/Val 분할
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

    # 모델 생성
    model = FallDetectionTransformer(
        input_dim=99,
        d_model=args.d_model,
        nhead=args.nhead,
        num_layers=args.num_layers,
        dim_feedforward=args.d_model * 2,
        dropout=0.2,
        num_classes=args.num_classes,
    ).to(device)

    # 학습 설정
    if is_multiclass:
        criterion = nn.CrossEntropyLoss()
    else:
        criterion = nn.BCELoss()

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    # 학습 루프
    best_f1 = 0.0
    best_epoch = 0
    best_state = None
    patience_counter = 0

    for epoch in range(1, args.epochs + 1):
        if is_multiclass:
            train_loss, train_acc = train_one_epoch_multiclass(
                model, train_loader, criterion, optimizer, device,
            )
            val_loss, val_acc, val_preds, val_labels = evaluate_multiclass(
                model, val_loader, criterion, device, args.num_classes,
            )
            val_f1 = compute_macro_f1(val_preds, val_labels, args.num_classes)
        else:
            train_loss, train_acc = train_one_epoch_binary(
                model, train_loader, criterion, optimizer, device,
            )
            val_loss, val_acc, val_prec, val_rec, val_f1 = evaluate_binary(
                model, val_loader, criterion, device,
            )

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
            print(
                f"{prefix}{epoch:3d}/{args.epochs} | "
                f"T-Loss={train_loss:.4f} T-Acc={train_acc:.1%} | "
                f"V-Loss={val_loss:.4f} V-Acc={val_acc:.1%} F1={val_f1:.4f} | "
                f"LR={lr:.2e}{marker}"
            )

        if patience_counter >= args.patience:
            if fold_label:
                print(f"  [{fold_label}] Early stopping at epoch {epoch}")
            else:
                print(f"\nEarly stopping at epoch {epoch} (patience={args.patience})")
            break

    # 베스트 모델 로드
    if best_state:
        model.load_state_dict(best_state)

    # 최종 per-class 메트릭 출력
    if is_multiclass and _SKLEARN_AVAILABLE:
        val_loss, val_acc, val_preds, val_labels = evaluate_multiclass(
            model, val_loader, criterion, device, args.num_classes,
        )
        target_names = CLASS_NAMES[:args.num_classes]
        print(f"\n  {'[' + fold_label + '] ' if fold_label else ''}Per-class 메트릭 (Best epoch={best_epoch}, F1={best_f1:.4f}):")
        print(classification_report(val_labels, val_preds, target_names=target_names, digits=4))
        print("  Confusion Matrix:")
        cm = confusion_matrix(val_labels, val_preds)
        # 행: 실제, 열: 예측
        header = "        " + " ".join(f"{n[:6]:>8}" for n in target_names)
        print(header)
        for i, row in enumerate(cm):
            print(f"  {target_names[i][:6]:>6} " + " ".join(f"{v:>8}" for v in row))
        print()

    return model, best_f1


def main():
    parser = argparse.ArgumentParser(description="SENTIO Transformer 모델 학습 (4클래스)")
    parser.add_argument("--data", type=str, required=True, help=".npz 데이터 파일 경로")
    parser.add_argument("--output", type=str, default="backend/models/fall_classifier.onnx")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--d-model", type=int, default=128)
    parser.add_argument("--nhead", type=int, default=4)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--patience", type=int, default=7, help="Early stopping patience")
    parser.add_argument("--num-classes", type=int, default=4,
                        help="분류 클래스 수 (1=binary sigmoid, 4=multiclass softmax)")
    parser.add_argument("--kfold", type=int, default=0,
                        help="K-Fold CV (0=비활성화, 2~10)")
    parser.add_argument("--benchmark", action="store_true",
                        help="ONNX 추론 벤치마크 실행")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"Classes: {args.num_classes} ({'binary (sigmoid)' if args.num_classes <= 2 else 'multiclass (softmax)'})")

    if args.kfold > 0 and not _SKLEARN_AVAILABLE:
        print("WARNING: scikit-learn 미설치 - K-Fold CV 비활성화 (pip install scikit-learn)")
        args.kfold = 0

    # 데이터 로드
    print(f"\n데이터 로드: {args.data}")
    X, y = load_data(args.data)
    print(f"  원본: X={X.shape}")
    unique, counts = np.unique(y, return_counts=True)
    for cls, cnt in zip(unique, counts):
        name = CLASS_NAMES[cls] if cls < len(CLASS_NAMES) else f"class_{cls}"
        print(f"    {name} ({cls}): {cnt}")

    # 클래스 균형
    X, y = balance_classes(X, y, seed=args.seed)
    print(f"  균형 후: X={X.shape}")
    unique, counts = np.unique(y, return_counts=True)
    for cls, cnt in zip(unique, counts):
        name = CLASS_NAMES[cls] if cls < len(CLASS_NAMES) else f"class_{cls}"
        print(f"    {name} ({cls}): {cnt}")

    # 모델 파라미터 표시
    temp_model = FallDetectionTransformer(
        input_dim=99, d_model=args.d_model, nhead=args.nhead,
        num_layers=args.num_layers, dim_feedforward=args.d_model * 2,
        num_classes=args.num_classes,
    )
    total_params = sum(p.numel() for p in temp_model.parameters())
    print(f"\n모델 파라미터: {total_params:,} ({total_params * 4 / 1024:.1f} KB)")
    del temp_model

    # ── K-Fold CV 모드 ──
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

            X_fold = X[train_idx]
            y_fold = y[train_idx]

            # 학습 세트 내에서 자체 val 분할
            _, fold_f1 = train_single_split(X_fold, y_fold, args, device, fold_label)
            fold_f1s.append(fold_f1)

        # K-Fold 요약
        fold_f1s = np.array(fold_f1s)
        print(f"\n{'='*70}")
        print(f"K-Fold CV 결과 ({args.kfold} folds):")
        for i, f1 in enumerate(fold_f1s):
            print(f"  Fold {i+1}: F1={f1:.4f}")
        print(f"  평균 F1: {fold_f1s.mean():.4f} ± {fold_f1s.std():.4f}")
        print(f"{'='*70}")

    # ── 최종 모델 학습 (전체 데이터) ──
    print(f"\n{'='*70}")
    print(f"최종 모델 학습 (전체 데이터)")
    print(f"{'='*70}")

    model, best_f1 = train_single_split(X, y, args, device)
    print(f"\n최종 Best F1: {best_f1:.4f}")

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
        else:
            print(f"    sigmoid 값: {result[0][0][0]:.4f}")
    except ImportError:
        print("  (onnxruntime 미설치 - ONNX 검증 스킵)")

    # 벤치마크
    if args.benchmark:
        run_benchmark(args.output)

    print(f"\n학습 완료! 모델: {args.output}")


if __name__ == "__main__":
    main()
