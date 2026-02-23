# SENTIO ML 학습 파이프라인 가이드

> 최종 업데이트: 2026-02-03
> 대상: AIHub/Pre-VFall 랜드마크 추출 및 5클래스 모델 학습

---

## 현재 상태

| 파이프라인 | 상태 | 비고 |
|-----------|------|------|
| Pre-VFall 랜드마크 추출 | **완료** | 3,659 시퀀스, 18.0 MB |
| AIHub 랜드마크 추출 | **진행 중** (~8%, 셔플+재추출) | 18,128건 전체, 청크 100개 단위, 워커 10개 |
| 데이터셋 병합 | 대기 | AIHub 완료 후 실행 |
| 5클래스 모델 학습 | 대기 | 병합 완료 후 실행 |

### 추출 재시작 이력

> **주의**: 2026-02-03 기존 청크를 전부 삭제하고 셔플 적용 후 재추출 시작
>
> **이유**: 기존 추출은 FY→BY→SY→N 순서대로 처리되어 초기 청크에
> front_fall/normal만 존재 (back_fall=0, side_fall=0). 4클래스 학습 불가능.
>
> **변경사항**:
> - 추출 전 `np.random.shuffle(seed=42)` 적용 → 모든 청크에 4클래스 균등 분배
> - chunk_size: 500 → 100 (안정성 향상)
> - workers: 4 → 10 (22코어 CPU 활용)
> - `cap.grab()` 최적화 (미사용 프레임 디코딩 스킵)
>
> 추출 완료 시 기존 `training_landmarks.npz`(불균형 데이터)를 **덮어씁니다**.

---

## 1. AIHub 랜드마크 추출

### 1-1. 재부팅/중단 후 이어서 실행

```bash
cd C:\Users\dbals\VibeCoding\Care-guard

python scripts/training/extract_landmarks.py ^
    --data-root D:/AIHub_Fall_Data ^
    --output-dir D:/AIHub_Fall_Data/landmarks ^
    --split Training ^
    --max-per-class 0 ^
    --chunk-size 100 ^
    --workers 10 ^
    --augment ^
    --resume
```

> **복사해서 바로 실행하면 됩니다.** `--resume`이 완료된 청크를 건너뛰고 이어서 처리합니다.

### 1-2. 추출 파라미터 설명

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `--data-root` | D:/AIHub_Fall_Data | 원본 영상 루트 |
| `--output-dir` | D:/AIHub_Fall_Data/landmarks | 출력 디렉토리 |
| `--chunk-size` | 100 | 청크당 영상 수 (총 182 청크) |
| `--workers` | 10 | 병렬 워커 수 (CPU 22코어 기준) |
| `--augment` | ON | 데이터 증강 (영상당 2~3배 복사본) |
| `--resume` | ON | 완료된 청크 건너뛰기 |

### 1-3. 데이터셋 클래스 분포

| 유형 | 코드 | 영상 수 | label |
|------|------|---------|-------|
| Front Fall | FY | 6,200 | 1 |
| Back Fall | BY | 4,640 | 2 |
| Side Fall | SY | 2,744 | 3 |
| Normal | N | 4,544 | 0 |
| **합계** | | **18,128** | |

셔플(seed=42) 적용으로 모든 청크에 4클래스가 골고루 분배됩니다.

### 1-4. `--resume` 동작 원리

- `D:/AIHub_Fall_Data/landmarks/chunks/` 폴더에 이미 저장된 `chunk_XXXX.npz` 파일을 확인
- 완료된 청크는 건너뛰고, 미완료 청크부터 재개
- 데이터 증강 RNG 상태도 청크 수만큼 advance하여 일관성 유지
- 몇 번이든 중단/재개 가능

**진행 상황 확인:**
```bash
# 완료된 청크 수 확인
ls D:/AIHub_Fall_Data/landmarks/chunks/ | wc -l

# Python으로 상세 확인
python -c "
import numpy as np
from pathlib import Path
chunks = sorted(Path('D:/AIHub_Fall_Data/landmarks/chunks').glob('chunk_*.npz'))
total_seqs = 0
total_proc = 0
total_fail = 0
for c in chunks:
    d = np.load(str(c))
    total_seqs += d['X'].shape[0]
    total_proc += int(d.get('processed', 0))
    total_fail += int(d.get('failed', 0))
print(f'청크: {len(chunks)}/182')
print(f'시퀀스: {total_seqs}개')
print(f'처리: {total_proc}, 실패: {total_fail}')
for lbl in range(4):
    names = ['normal','front_fall','back_fall','side_fall']
    count = sum((np.load(str(c))['y']==lbl).sum() for c in chunks)
    print(f'  {names[lbl]}({lbl}): {count}')
"
```

### 1-5. 추출 완료 확인

추출이 끝나면 자동으로 모든 청크를 병합하여 최종 파일을 생성합니다:
- 출력: `D:/AIHub_Fall_Data/landmarks/training_landmarks.npz` (**기존 파일 덮어쓰기**)
- 형식: `X=(N, 30, 99) float32`, `y=(N,) int64`

```bash
# 최종 NPZ 확인
python -c "
import numpy as np
d = np.load('D:/AIHub_Fall_Data/landmarks/training_landmarks.npz')
print(f'X: {d[\"X\"].shape}, y: {d[\"y\"].shape}')
names = ['normal','front_fall','back_fall','side_fall']
unique, counts = np.unique(d['y'], return_counts=True)
for u, c in zip(unique, counts):
    print(f'  {names[u]}({u}): {c}')
"
```

### 1-6. 추출 속도 참고

| 항목 | 수치 |
|------|------|
| 실제 처리 속도 | ~0.3 영상/초 |
| 총 소요 시간 | ~15~16시간 |
| 병목 | MediaPipe CPU 포즈 추론 + 4K 영상 디코딩 |
| GPU 가속 | 불가 (MediaPipe Python은 데스크톱 GPU 미지원) |

---

## 2. Pre-VFall 랜드마크 추출 (이미 완료)

```bash
# 재실행이 필요한 경우에만 사용
python scripts/training/extract_prevfall_landmarks.py \
    --data-root D:/PreVFall_Data/Pre-VFallp \
    --output-dir D:/PreVFall_Data/landmarks \
    --mode mediapipe \
    --resume
```

**결과:**
- 출력: `D:/PreVFall_Data/landmarks/prevfall_landmarks.npz` (18.0 MB)
- 시퀀스: 3,659개
- 클래스: normal=2,145 / front_fall=143 / side_fall=38 / pre_impact=1,333

---

## 3. 데이터셋 병합 (AIHub 완료 후)

```bash
python scripts/training/data_preprocessing.py \
    --source merge \
    --aihub-npz D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
    --prevfall-npz D:/PreVFall_Data/landmarks/prevfall_landmarks.npz \
    --output D:/merged_landmarks.npz
```

이 스크립트는:
- AIHub 4클래스 (0,1,2,3) + Pre-VFall 5클래스 (0,1,3,4)를 하나로 병합
- 클래스 라벨 통합 (AIHub에 없는 class 4 = pre_impact는 Pre-VFall에서만 제공)
- 전체 데이터 셔플 + 통계 출력

---

## 4. 5클래스 모델 학습

```bash
python scripts/training/train_v2.py \
    --data D:/merged_landmarks.npz \
    --output backend/models/fall_classifier_v2.onnx \
    --num-classes 5 \
    --epochs 30 \
    --batch-size 64 \
    --lr 1e-3 \
    --patience 7
```

**주요 옵션:**
- `--num-classes 5`: 5클래스 분류 (normal, front_fall, back_fall, side_fall, pre_impact)
- `--focal-loss`: FocalLoss 사용 (클래스 불균형 대응, 기본 ON)
- `--kfold 5`: 5-Fold 교차 검증 (선택)
- `--benchmark`: 추론 속도 벤치마크 (학습 후)

**모델 아키텍처:**

| 항목 | 값 |
|------|---|
| 구조 | FallDetectionTransformer (Lightweight) |
| 입력 | (batch, 30, 99) — 30프레임 x 33관절 x xyz |
| 인코더 | 2-layer Transformer, 4 attention heads |
| d_model | 128 |
| 출력 | 5클래스 softmax |
| Optimizer | AdamW (lr=1e-3, weight_decay=1e-4) |
| Scheduler | CosineAnnealingLR |
| Early Stopping | patience=7 epochs |

**또는 4클래스만 학습 (AIHub 단독):**
```bash
python scripts/training/train_transformer.py \
    --data D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
    --output backend/models/fall_classifier.onnx \
    --num-classes 4 \
    --epochs 30 \
    --batch-size 64 \
    --kfold 5
```

---

## 5. 모델 배포

학습이 완료되면:

1. `backend/models/fall_classifier_v2.onnx` 파일이 생성됨
2. 백엔드 서버 재시작 → 자동으로 v2 모델 로드 (v1 폴백 지원)
3. ONNX 출력 차원에 따라 자동 분류:
   - 1개 → sigmoid binary
   - 2개 → softmax binary
   - 4개 → 4클래스
   - **5개 → 5클래스 (pre_impact 포함)**

```bash
# 서버 재시작
cd backend
uvicorn app.main:app --reload
# 로그에서 확인: "낙상 분류기 ONNX 모델 로드 완료: .../fall_classifier_v2.onnx (output_dim=5)"
```

---

## 전체 파이프라인 요약

```
[Step 1] AIHub 영상 → extract_landmarks.py → chunks/ → training_landmarks.npz (덮어쓰기)
                          (셔플, 100개 단위)              (4클래스: 0,1,2,3)

[Step 2] Pre-VFall 이미지 → extract_prevfall_landmarks.py → prevfall_landmarks.npz (완료)
                                                              (5클래스: 0,1,3,4)

[Step 3] training_landmarks.npz + prevfall_landmarks.npz → data_preprocessing.py → merged.npz
                                                                                    (5클래스: 0,1,2,3,4)

[Step 4] merged.npz → train_v2.py → fall_classifier_v2.onnx

[Step 5] fall_classifier_v2.onnx → backend/models/ → 서버 재시작 → 5클래스 추론
```

**소요 시간 비중:** 추출(Step 1)이 전체 파이프라인의 대부분을 차지하며, 이후 단계(병합→학습→배포)는 상대적으로 빠르게 완료됩니다.

---

## 트러블슈팅

### Q: AIHub 추출이 중단되었다 (PC 재부팅, 연결 끊김 등)
```bash
cd C:\Users\dbals\VibeCoding\Care-guard
python scripts/training/extract_landmarks.py ^
    --data-root D:/AIHub_Fall_Data ^
    --output-dir D:/AIHub_Fall_Data/landmarks ^
    --split Training --max-per-class 0 --chunk-size 100 --workers 10 --augment --resume
```
> `--resume`이 자동으로 완료된 청크를 건너뜁니다. 몇 번이든 중단/재개 가능합니다.

### Q: 추출 속도가 갑자기 느려졌다
- 긴 영상(수천 프레임)을 만나면 일시적으로 느려짐 → 정상, 해당 영상 처리 후 복구
- ETA는 전체 평균 기반이므로 긴 영상 처리 중 급등할 수 있음
- 병목은 MediaPipe CPU 추론이며, GPU 가속은 데스크톱 Python에서 미지원

### Q: 이전 training_landmarks.npz는?
- 추출 완료 시 자동 덮어쓰기됨
- 기존 파일은 불균형 데이터 (front_fall+normal만)로 학습에 사용 불가
- 새 파일은 셔플 적용으로 4클래스 균형 데이터

### Q: Pre-VFall 추출에서 42건 실패
- MediaPipe가 해당 이미지에서 포즈를 감지하지 못한 경우 (어둡거나 가려진 이미지)
- `--mode openpose` 옵션으로 기존 OpenPose JSON 활용 가능 (대안)

### Q: 메모리 부족
- `--chunk-size`를 줄이세요 (현재 100, 더 줄일 수 있음)
- 청크별 즉시 저장되므로 메모리 사용량은 청크 크기에 비례

### Q: 모델 v1과 v2를 동시에 사용하고 싶다
- `backend/models/` 폴더에 두 파일 모두 배치
- 코드는 v2 (`fall_classifier_v2.onnx`) 우선, 없으면 v1 (`fall_classifier.onnx`) 폴백

---

## 5클래스 분류 체계

| ID | 이름 | 설명 | 데이터 소스 |
|----|------|------|------------|
| 0 | normal | 정상 상태 | AIHub + Pre-VFall |
| 1 | front_fall | 전면 낙상 | AIHub (FY) + Pre-VFall (forward) |
| 2 | back_fall | 후면 낙상 | AIHub (BY) only |
| 3 | side_fall | 측면 낙상 | AIHub (SY) + Pre-VFall (side) |
| 4 | pre_impact | 낙상 전조 (비틀거림, 균형 상실) | Pre-VFall (Abnormal) only |

---

## 파일 구조

```
scripts/training/
├── extract_landmarks.py          # AIHub 영상 → 랜드마크 추출 (VIDEO 모드, 셔플+grab최적화)
├── extract_prevfall_landmarks.py # Pre-VFall 이미지 → 랜드마크 추출 (IMAGE 모드)
├── data_preprocessing.py         # 데이터 병합/변환 유틸리티
├── train_v2.py                   # 5클래스 모델 학습 (FocalLoss, 클래스 가중치)
├── train_transformer.py          # 4클래스 모델 학습
├── download_data.py              # AIHub 데이터 다운로드
└── download_prevfall.py          # Pre-VFall 데이터 다운로드

D:/AIHub_Fall_Data/
├── Training/                     # 원본 영상 데이터 (4K, 60fps)
└── landmarks/
    ├── chunks/                   # 청크별 NPZ (중간 산출물, 182개)
    │   ├── chunk_0000.npz        #   셔플 적용, 4클래스 균등 분배
    │   ├── chunk_0001.npz
    │   └── ...
    └── training_landmarks.npz    # 최종 병합 NPZ (추출 완료 시 덮어쓰기)

D:/PreVFall_Data/
├── Pre-VFallp/                   # 원본 이미지 데이터
└── landmarks/
    ├── prevfall_chunks/          # 청크별 NPZ (중간 산출물)
    └── prevfall_landmarks.npz    # 최종 NPZ (완료)

backend/models/
├── fall_classifier.onnx          # v1 모델 (4클래스, 현재 배포)
└── fall_classifier_v2.onnx       # v2 모델 (5클래스, 학습 대기)
```
