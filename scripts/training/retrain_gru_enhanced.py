"""
GRU 모델 재학습 스크립트 (SY 측면 낙상 보강)

기존 AIHub 데이터 + UP-Fall 데이터 병합
SY 클래스 오버샘플링 + 가중치 강화

사용법:
    python scripts/training/retrain_gru_enhanced.py \
        --aihub D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
        --upfall D:/UP_Fall_Data/upfall_landmarks.npz \
        --epochs 25 \
        --output backend/models/fall_classifier_gru.onnx

    # UP-Fall 없이 SY 오버샘플링만:
    python scripts/training/retrain_gru_enhanced.py \
        --aihub D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
        --epochs 25
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix


# ============================================================
# 1. 모델 정의 (기존과 동일 구조)
# ============================================================
class FallDetectorGRUBinary(nn.Module):
    def __init__(
        self,
        input_size: int = 99,
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.3,
        bidirectional: bool = True,
    ):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=bidirectional,
        )
        fc_input = hidden_size * 2 if bidirectional else hidden_size
        self.classifier = nn.Sequential(
            nn.Linear(fc_input, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        gru_out, _ = self.gru(x)
        last_hidden = gru_out[:, -1, :]
        return self.classifier(last_hidden).squeeze(-1)


# ============================================================
# 2. 데이터셋
# ============================================================
class FallDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        # 이진 분류: N=0, 나머지(BY/FY/SY)=1
        self.y = torch.FloatTensor((y > 0).astype(np.float32))

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ============================================================
# 3. 데이터 병합 및 SY 오버샘플링
# ============================================================
def merge_and_oversample(
    aihub_path: str,
    upfall_path: str | None = None,
    sy_oversample_ratio: float = 3.0,
    noise_augment_count: int = 2,
):
    """
    AIHub + UP-Fall 데이터 병합 및 SY 오버샘플링

    Args:
        aihub_path: AIHub 데이터 경로
        upfall_path: UP-Fall 데이터 경로 (없으면 AIHub만)
        sy_oversample_ratio: SY 클래스 오버샘플링 비율 (3.0 = 3배)
        noise_augment_count: SY에 대한 노이즈 증강 횟수
    """
    print("=" * 60)
    print("데이터 로드 및 병합")
    print("=" * 60)

    # AIHub 로드
    print(f"\n  AIHub: {aihub_path}")
    aihub = np.load(aihub_path, allow_pickle=True)
    X_aihub = aihub['X']
    y_aihub = aihub['y']
    class_names = aihub['class_names']
    print(f"  AIHub shape: {X_aihub.shape}, classes: {class_names}")

    X_all = [X_aihub]
    y_all = [y_aihub]

    # UP-Fall 로드 (있으면)
    if upfall_path and Path(upfall_path).exists():
        print(f"\n  UP-Fall: {upfall_path}")
        upfall = np.load(upfall_path, allow_pickle=True)
        X_upfall = upfall['X']
        y_upfall = upfall['y']
        print(f"  UP-Fall shape: {X_upfall.shape}")

        # UP-Fall 데이터 정규화 (AIHub와 범위 맞추기)
        # MediaPipe 좌표는 0~1 범위이므로 이미 호환
        X_all.append(X_upfall)
        y_all.append(y_upfall)
    elif upfall_path:
        print(f"\n  [경고] UP-Fall 파일 없음: {upfall_path}")
        print("  AIHub 데이터만 사용합니다.")

    X = np.concatenate(X_all, axis=0)
    y = np.concatenate(y_all, axis=0)

    print(f"\n  병합 후: X={X.shape}, y={y.shape}")

    # 클래스 분포 확인
    unique, counts = np.unique(y, return_counts=True)
    print("\n  클래스 분포 (병합 후):")
    for cls, cnt in zip(unique, counts):
        name = class_names[cls] if cls < len(class_names) else f"Class_{cls}"
        print(f"    {name}: {cnt:,} ({cnt/len(y)*100:.1f}%)")

    # SY (class 3) 오버샘플링
    print(f"\n  SY 오버샘플링 (x{sy_oversample_ratio})...")
    sy_mask = y == 3  # side_fall
    X_sy = X[sy_mask]
    y_sy = y[sy_mask]
    n_sy_orig = len(X_sy)

    # 원본 복제
    n_copies = int(sy_oversample_ratio) - 1  # 원본 포함이므로 -1
    for _ in range(n_copies):
        X_all.append(X_sy)
        y_all.append(y_sy)

    # 노이즈 증강
    print(f"  SY 노이즈 증강 (x{noise_augment_count})...")
    for _ in range(noise_augment_count):
        noise = np.random.normal(0, 0.003, X_sy.shape).astype(np.float32)
        X_noisy = (X_sy + noise).clip(0, 1)
        X_all.append(X_noisy)
        y_all.append(y_sy)

    # 시간 왜곡 증강 (SY만)
    print("  SY 시간 왜곡 증강...")
    # 빠른 버전 (프레임 건너뛰기)
    if len(X_sy) > 0 and X_sy.shape[1] >= 30:
        indices_fast = np.sort(np.random.choice(30, 30, replace=True))
        X_time_warp = X_sy[:, indices_fast, :]
        X_all.append(X_time_warp)
        y_all.append(y_sy)

    X = np.concatenate(X_all, axis=0)
    y = np.concatenate(y_all, axis=0)

    # 최종 분포
    unique, counts = np.unique(y, return_counts=True)
    print(f"\n  최종 데이터: X={X.shape}, y={y.shape}")
    print("\n  클래스 분포 (오버샘플링 후):")
    for cls, cnt in zip(unique, counts):
        name = class_names[cls] if cls < len(class_names) else f"Class_{cls}"
        print(f"    {name}: {cnt:,} ({cnt/len(y)*100:.1f}%)")

    n_sy_final = (y == 3).sum()
    print(f"\n  SY 증가: {n_sy_orig:,} → {n_sy_final:,} ({n_sy_final/n_sy_orig:.1f}x)")

    return X, y, class_names


# ============================================================
# 4. Focal Loss (클래스 불균형 대응)
# ============================================================
class FocalLoss(nn.Module):
    """
    Focal Loss for binary classification
    낙상 클래스에 대한 recall 향상
    """
    def __init__(self, alpha: float = 0.75, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs, targets):
        bce = nn.functional.binary_cross_entropy(inputs, targets, reduction='none')
        pt = torch.where(targets == 1, inputs, 1 - inputs)
        alpha_t = torch.where(targets == 1, self.alpha, 1 - self.alpha)
        focal_weight = alpha_t * (1 - pt) ** self.gamma
        return (focal_weight * bce).mean()


# ============================================================
# 5. 학습 함수
# ============================================================
def train_model(
    model, train_loader, val_loader,
    epochs: int = 25, lr: float = 0.001, device: str = "cuda",
    use_focal_loss: bool = True,
):
    model = model.to(device)

    if use_focal_loss:
        criterion = FocalLoss(alpha=0.75, gamma=2.0)
    else:
        criterion = nn.BCELoss()

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=5, T_mult=2, eta_min=1e-6
    )

    best_f1 = 0.0
    best_model_state = None
    history = []

    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item()

        scheduler.step()

        # Validation
        model.eval()
        val_loss = 0.0
        all_preds = []
        all_labels = []
        all_probs = []

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()
                preds = (outputs > 0.5).long()
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(y_batch.cpu().numpy())
                all_probs.extend(outputs.cpu().numpy())

        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)

        # Metrics
        fall_mask = all_labels == 1
        tp = ((all_preds == 1) & (all_labels == 1)).sum()
        fp = ((all_preds == 1) & (all_labels == 0)).sum()
        fn = ((all_preds == 0) & (all_labels == 1)).sum()
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (all_preds == all_labels).mean()

        lr_current = optimizer.param_groups[0]['lr']
        print(f"Epoch {epoch+1}/{epochs} | lr={lr_current:.6f}")
        print(f"  Loss: train={train_loss/len(train_loader):.4f} val={val_loss/len(val_loader):.4f}")
        print(f"  Acc={accuracy:.4f} Recall={recall:.4f} Prec={precision:.4f} F1={f1:.4f}")

        history.append({
            'epoch': epoch + 1, 'recall': recall, 'precision': precision,
            'f1': f1, 'accuracy': accuracy,
        })

        # Best model 저장 (F1 기준, recall >= 0.83 조건)
        if f1 > best_f1 and recall >= 0.83:
            best_f1 = f1
            best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
            print(f"  >>> New Best F1: {f1:.4f} (Recall={recall:.4f})")

    if best_model_state:
        model.load_state_dict(best_model_state)
    else:
        print("\n[경고] recall >= 0.83 조건을 만족하는 모델 없음. 마지막 모델 사용.")

    return model, best_f1, history


# ============================================================
# 6. SY별 성능 분석
# ============================================================
def analyze_sy_performance(model, X_val, y_val_orig, device):
    """SY (class 3) 성능을 별도로 분석"""
    model.eval()

    # 원본 4-class 레이블 기준으로 분석
    print("\n" + "=" * 60)
    print("낙상 유형별 성능 분석")
    print("=" * 60)

    class_names = ['normal', 'front_fall', 'back_fall', 'side_fall']

    with torch.no_grad():
        X_tensor = torch.FloatTensor(X_val).to(device)
        # 배치 처리
        batch_size = 512
        all_probs = []
        for i in range(0, len(X_tensor), batch_size):
            batch = X_tensor[i:i+batch_size]
            probs = model(batch).cpu().numpy()
            all_probs.extend(probs)
        all_probs = np.array(all_probs)

    # 이진 예측
    preds_binary = (all_probs > 0.5).astype(int)

    for cls in range(4):
        mask = y_val_orig == cls
        if mask.sum() == 0:
            continue

        n_total = mask.sum()
        if cls == 0:  # normal
            # Normal: 올바르게 0으로 예측한 비율
            correct = (preds_binary[mask] == 0).sum()
            rate = correct / n_total
            print(f"  {class_names[cls]:12s}: {correct}/{n_total} ({rate:.1%}) correctly normal")
        else:  # fall types
            detected = (preds_binary[mask] == 1).sum()
            rate = detected / n_total
            avg_prob = all_probs[mask].mean()
            print(f"  {class_names[cls]:12s}: {detected}/{n_total} ({rate:.1%}) detected, avg_prob={avg_prob:.3f}")

    # SY 상세 분석
    sy_mask = y_val_orig == 3
    if sy_mask.sum() > 0:
        sy_probs = all_probs[sy_mask]
        print(f"\n  SY 분포: min={sy_probs.min():.3f} median={np.median(sy_probs):.3f} "
              f"max={sy_probs.max():.3f} mean={sy_probs.mean():.3f}")
        print(f"  SY < 0.3: {(sy_probs < 0.3).sum()} / {len(sy_probs)}")
        print(f"  SY < 0.5: {(sy_probs < 0.5).sum()} / {len(sy_probs)}")
        print(f"  SY >= 0.5: {(sy_probs >= 0.5).sum()} / {len(sy_probs)}")
        print(f"  SY >= 0.7: {(sy_probs >= 0.7).sum()} / {len(sy_probs)}")


# ============================================================
# 7. ONNX 변환
# ============================================================
def export_to_onnx(model, output_path: str, input_shape=(1, 30, 99)):
    model.eval()
    model_cpu = model.cpu()
    dummy_input = torch.randn(*input_shape)

    torch.onnx.export(
        model_cpu,
        dummy_input,
        output_path,
        input_names=["keypoints_sequence"],
        output_names=["fall_probability"],
        dynamic_axes={
            "keypoints_sequence": {0: "batch_size"},
            "fall_probability": {0: "batch_size"},
        },
        opset_version=11,
    )
    print(f"  ONNX 모델 저장: {output_path}")


# ============================================================
# 8. 메인
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="GRU 재학습 (SY 보강)")
    parser.add_argument("--aihub", type=str,
                        default="D:/AIHub_Fall_Data/landmarks/training_landmarks.npz")
    parser.add_argument("--upfall", type=str, default=None,
                        help="UP-Fall 데이터 경로 (없으면 AIHub만)")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.0008)
    parser.add_argument("--sy-oversample", type=float, default=3.0,
                        help="SY 오버샘플링 비율")
    parser.add_argument("--output", type=str,
                        default="backend/models/fall_classifier_gru.onnx")
    parser.add_argument("--no-focal", action="store_true",
                        help="Focal Loss 비활성화 (BCE 사용)")
    args = parser.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    if device == "cpu":
        print("[경고] GPU 없음. 학습이 느릴 수 있습니다.")

    # 데이터 병합 및 오버샘플링
    X, y, class_names = merge_and_oversample(
        args.aihub, args.upfall,
        sy_oversample_ratio=args.sy_oversample,
    )

    # Train/Val 분할 (원본 레이블 보존하여 SY 분석용)
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n  Train: {len(X_train):,}, Val: {len(X_val):,}")

    # 이진 레이블
    y_train_bin = (y_train > 0).astype(np.float32)
    y_val_bin = (y_val > 0).astype(np.float32)

    # WeightedRandomSampler: 낙상 샘플 더 자주 선택
    fall_weight = len(y_train_bin) / (2 * (y_train_bin == 1).sum())
    normal_weight = len(y_train_bin) / (2 * (y_train_bin == 0).sum())
    sample_weights = np.where(y_train_bin == 1, fall_weight, normal_weight)
    sampler = WeightedRandomSampler(
        weights=sample_weights,
        num_samples=len(sample_weights),
        replacement=True,
    )

    train_dataset = FallDataset(X_train, y_train)
    val_dataset = FallDataset(X_val, y_val)

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size,
        sampler=sampler, num_workers=0, pin_memory=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size,
        shuffle=False, num_workers=0, pin_memory=True,
    )

    # 모델 생성
    model = FallDetectorGRUBinary(
        input_size=99, hidden_size=128, num_layers=2, dropout=0.3,
    )
    print(f"\n  모델 파라미터: {sum(p.numel() for p in model.parameters()):,}")

    # 기존 모델 가중치 로드 (전이학습)
    existing_pt = Path(args.output).with_suffix(".pt")
    if existing_pt.exists():
        print(f"\n  기존 모델 로드 (전이학습): {existing_pt}")
        try:
            checkpoint = torch.load(existing_pt, map_location='cpu', weights_only=False)
            if 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
                print(f"  기존 Recall: {checkpoint.get('best_recall', 'N/A')}")
            else:
                model.load_state_dict(checkpoint)
            print("  전이학습 가중치 로드 완료!")
        except Exception as e:
            print(f"  [경고] 기존 모델 로드 실패: {e}")
            print("  처음부터 학습합니다.")

    # 학습
    print("\n" + "=" * 60)
    print("학습 시작")
    print("=" * 60)
    start_time = time.time()

    model, best_f1, history = train_model(
        model, train_loader, val_loader,
        epochs=args.epochs, lr=args.lr, device=device,
        use_focal_loss=not args.no_focal,
    )

    elapsed = time.time() - start_time
    print(f"\n  학습 완료! 소요 시간: {elapsed/60:.1f}분")
    print(f"  Best F1: {best_f1:.4f}")

    # SY별 성능 분석
    analyze_sy_performance(model, X_val, y_val, device)

    # 최종 평가
    print("\n" + "=" * 60)
    print("최종 평가")
    print("=" * 60)
    model.eval()
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            X_batch = X_batch.to(device)
            outputs = model(X_batch)
            preds = (outputs > 0.5).long().cpu()
            all_preds.extend(preds.numpy())
            all_labels.extend(y_batch.numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)
    print(classification_report(all_labels, all_preds, target_names=["Normal", "Fall"]))
    print("Confusion Matrix:")
    print(confusion_matrix(all_labels, all_preds))

    # ONNX 저장
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 기존 모델 백업
    if output_path.exists():
        backup_path = output_path.with_name(
            output_path.stem + "_backup_" + time.strftime("%Y%m%d_%H%M%S") + output_path.suffix
        )
        import shutil
        shutil.copy2(output_path, backup_path)
        print(f"\n  기존 모델 백업: {backup_path}")

    export_to_onnx(model, str(output_path))

    # PyTorch 모델 저장
    torch_path = output_path.with_suffix(".pt")
    torch.save({
        'model_state_dict': model.state_dict(),
        'class_names': list(class_names),
        'binary': True,
        'best_f1': best_f1,
        'history': history,
        'sy_oversample_ratio': args.sy_oversample,
        'upfall_used': args.upfall is not None,
    }, torch_path)
    print(f"  PyTorch 모델 저장: {torch_path}")

    print("\n" + "=" * 60)
    print("완료!")
    print("=" * 60)
    print(f"\n다음 단계: 벤치마크 실행")
    print(f"  python scripts/benchmark_aihub_fall_detection.py")


if __name__ == "__main__":
    main()
