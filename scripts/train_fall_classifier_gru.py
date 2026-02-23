"""
AIHub 낙상 데이터셋 GRU 학습 스크립트

목표: Recall 85%+ 달성
데이터: D:/AIHub_Fall_Data/landmarks/training_landmarks.npz
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import time
from pathlib import Path


# ============================================================
# 1. 모델 정의: 경량 GRU 분류기
# ============================================================
class FallDetectorGRU(nn.Module):
    """
    경량 GRU 기반 낙상 분류기
    - 입력: (batch, seq_len=30, features=99)
    - 출력: (batch, 4) - [N, BY, FY, SY] 확률
    """
    def __init__(
        self,
        input_size: int = 99,      # 33 keypoints × 3 coords
        hidden_size: int = 128,     # GRU hidden dimension
        num_layers: int = 2,        # GRU layers
        num_classes: int = 4,       # N, BY, FY, SY
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

        # Bidirectional이면 hidden_size * 2
        fc_input = hidden_size * 2 if bidirectional else hidden_size

        self.classifier = nn.Sequential(
            nn.Linear(fc_input, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x):
        # x: (batch, seq_len, features)
        gru_out, _ = self.gru(x)  # (batch, seq_len, hidden*2)

        # 마지막 타임스텝 사용
        last_hidden = gru_out[:, -1, :]  # (batch, hidden*2)

        logits = self.classifier(last_hidden)  # (batch, num_classes)
        return logits


# ============================================================
# 2. 이진 분류 모델 (낙상 vs 정상)
# ============================================================
class FallDetectorGRUBinary(nn.Module):
    """
    이진 분류 버전 (낙상=1, 정상=0)
    Recall 최적화에 더 적합
    """
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
            nn.Linear(64, 1),  # 이진 분류
            nn.Sigmoid(),
        )

    def forward(self, x):
        gru_out, _ = self.gru(x)
        last_hidden = gru_out[:, -1, :]
        prob = self.classifier(last_hidden)
        return prob.squeeze(-1)


# ============================================================
# 3. 데이터셋 클래스
# ============================================================
class FallDataset(Dataset):
    def __init__(self, X, y, binary=False):
        self.X = torch.FloatTensor(X)

        if binary:
            # 이진 분류: N=0, 나머지(BY/FY/SY)=1
            self.y = torch.FloatTensor((y > 0).astype(np.float32))
        else:
            self.y = torch.LongTensor(y)

        self.binary = binary

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ============================================================
# 4. 학습 함수
# ============================================================
def train_model(
    model,
    train_loader,
    val_loader,
    epochs: int = 20,
    lr: float = 0.001,
    device: str = "cuda",
    binary: bool = False,
    class_weights: torch.Tensor = None,
):
    model = model.to(device)

    if binary:
        # 이진 분류: BCE Loss + 낙상 가중치
        criterion = nn.BCELoss()
    else:
        # 다중 분류: CrossEntropy + 클래스 가중치
        criterion = nn.CrossEntropyLoss(weight=class_weights.to(device) if class_weights is not None else None)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)

    best_recall = 0.0
    best_model_state = None

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
            optimizer.step()

            train_loss += loss.item()

        # Validation
        model.eval()
        val_loss = 0.0
        all_preds = []
        all_labels = []

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)
                val_loss += loss.item()

                if binary:
                    preds = (outputs > 0.5).long()
                else:
                    preds = outputs.argmax(dim=1)

                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(y_batch.cpu().numpy())

        # Metrics
        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)

        if binary:
            # 이진 분류 Recall (낙상 감지율)
            fall_mask = all_labels == 1
            recall = (all_preds[fall_mask] == 1).sum() / fall_mask.sum() if fall_mask.sum() > 0 else 0
            precision = (all_labels[all_preds == 1] == 1).sum() / (all_preds == 1).sum() if (all_preds == 1).sum() > 0 else 0
        else:
            # 다중 분류: 낙상(BY/FY/SY) Recall
            fall_mask = all_labels > 0  # BY, FY, SY
            fall_preds = all_preds > 0
            recall = (fall_preds[fall_mask]).sum() / fall_mask.sum() if fall_mask.sum() > 0 else 0
            precision = (all_labels[fall_preds] > 0).sum() / fall_preds.sum() if fall_preds.sum() > 0 else 0

        accuracy = (all_preds == all_labels).mean()

        scheduler.step(val_loss)

        print(f"Epoch {epoch+1}/{epochs}")
        print(f"  Train Loss: {train_loss/len(train_loader):.4f}")
        print(f"  Val Loss: {val_loss/len(val_loader):.4f}")
        print(f"  Accuracy: {accuracy:.4f}, Recall: {recall:.4f}, Precision: {precision:.4f}")

        # Best model 저장 (Recall 기준)
        if recall > best_recall:
            best_recall = recall
            best_model_state = model.state_dict().copy()
            print(f"  ⭐ New best Recall: {recall:.4f}")

    # Best model 복원
    if best_model_state:
        model.load_state_dict(best_model_state)

    return model, best_recall


# ============================================================
# 5. ONNX 변환
# ============================================================
def export_to_onnx(model, output_path: str, input_shape=(1, 30, 99)):
    model.eval()
    dummy_input = torch.randn(*input_shape)

    torch.onnx.export(
        model.cpu(),
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
    print(f"✅ ONNX 모델 저장: {output_path}")


# ============================================================
# 6. 메인 학습 루프
# ============================================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description="GRU 낙상 분류기 학습")
    parser.add_argument("--data", type=str, default="D:/AIHub_Fall_Data/landmarks/training_landmarks.npz")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--binary", action="store_true", help="이진 분류 모드")
    parser.add_argument("--output", type=str, default="backend/models/fall_classifier_gru.onnx")
    args = parser.parse_args()

    # GPU 확인
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    if device == "cpu":
        print("⚠️  GPU가 없습니다. 학습이 느릴 수 있습니다.")

    # 데이터 로드
    print(f"\n📂 데이터 로드: {args.data}")
    data = np.load(args.data, allow_pickle=True)
    X = data['X']
    y = data['y']
    class_names = data['class_names']

    print(f"  X shape: {X.shape}")
    print(f"  y shape: {y.shape}")
    print(f"  Classes: {class_names}")

    # 클래스 분포 확인
    unique, counts = np.unique(y, return_counts=True)
    print("\n📊 클래스 분포:")
    for cls, cnt in zip(unique, counts):
        name = class_names[cls] if cls < len(class_names) else f"Class_{cls}"
        print(f"  {name}: {cnt:,} ({cnt/len(y)*100:.1f}%)")

    # Train/Val 분할
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\n📊 Train: {len(X_train):,}, Val: {len(X_val):,}")

    # Dataset & DataLoader
    train_dataset = FallDataset(X_train, y_train, binary=args.binary)
    val_dataset = FallDataset(X_val, y_val, binary=args.binary)

    # Windows에서는 num_workers=0 사용 (multiprocessing 이슈)
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0, pin_memory=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0, pin_memory=True)

    # 클래스 가중치 (불균형 보정)
    if not args.binary:
        class_weights = torch.FloatTensor([
            1.0,  # N (정상) - 가중치 낮춤
            2.0,  # BY (후방) - 낙상 가중치
            2.0,  # FY (전방) - 낙상 가중치
            2.0,  # SY (측면) - 낙상 가중치
        ])
    else:
        class_weights = None

    # 모델 생성
    if args.binary:
        model = FallDetectorGRUBinary(
            input_size=99,
            hidden_size=128,
            num_layers=2,
            dropout=0.3,
        )
    else:
        model = FallDetectorGRU(
            input_size=99,
            hidden_size=128,
            num_layers=2,
            num_classes=4,
            dropout=0.3,
        )

    print(f"\n🧠 모델 파라미터: {sum(p.numel() for p in model.parameters()):,}")

    # 학습
    print("\n🚀 학습 시작...")
    start_time = time.time()

    model, best_recall = train_model(
        model,
        train_loader,
        val_loader,
        epochs=args.epochs,
        lr=args.lr,
        device=device,
        binary=args.binary,
        class_weights=class_weights,
    )

    elapsed = time.time() - start_time
    print(f"\n✅ 학습 완료! 소요 시간: {elapsed/60:.1f}분")
    print(f"   Best Recall: {best_recall:.4f}")

    # 최종 평가
    print("\n📊 최종 평가:")
    model.eval()
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            X_batch = X_batch.to(device)
            outputs = model(X_batch)

            if args.binary:
                preds = (outputs > 0.5).long().cpu()
            else:
                preds = outputs.argmax(dim=1).cpu()

            all_preds.extend(preds.numpy())
            all_labels.extend(y_batch.numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    if args.binary:
        print(classification_report(all_labels, all_preds, target_names=["Normal", "Fall"]))
    else:
        print(classification_report(all_labels, all_preds, target_names=list(class_names)))

    print("\nConfusion Matrix:")
    print(confusion_matrix(all_labels, all_preds))

    # ONNX 변환
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_to_onnx(model, str(output_path))

    # PyTorch 모델도 저장
    torch_path = output_path.with_suffix(".pt")
    torch.save({
        'model_state_dict': model.state_dict(),
        'class_names': list(class_names),
        'binary': args.binary,
        'best_recall': best_recall,
    }, torch_path)
    print(f"✅ PyTorch 모델 저장: {torch_path}")


if __name__ == "__main__":
    main()
