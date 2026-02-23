# SENTIO WAITING AI - Claude Code 고급 개발 프롬프트
## 레퍼런스 사이트 기반 전문가 수준 구현 가이드

---

## 📋 프로젝트 컨텍스트

이 프롬프트는 다음 레퍼런스 제품들의 기술을 참고하여 SENTIO 낙상 감지 시스템을 구현합니다:

### 레퍼런스 제품 분석

| 제품 | 회사 | 핵심 기술 | 참고 URL |
|------|------|----------|----------|
| **AI-PAM** | 지오멕스소프트 | PanopticDeepLab, 스켈레톤 분석, 어안렌즈 | https://geomex.co.kr |
| **FDD** | 슈퍼게이트 | AI 기반 낙상 감지, ASIC 최적화 | https://supergate.co.kr/fdd |
| **이상행동 CCTV 데이터셋** | AI Hub | 12가지 이상행동(실신 포함), 700+시간 | https://aihub.or.kr/aidata/139 |

---

## 🚀 마스터 프롬프트 (프로젝트 전체 컨텍스트)

```markdown
# SENTIO 낙상 감지 시스템 개발 요청

## 프로젝트 개요
요양병원/재활병원 대기실 환경에서 카메라 영상을 실시간 분석하여 환자의 낙상 및 이상 행동을 감지하고, 
골든타임(10초 이내) 안에 의료진에게 알림을 제공하는 AI 시스템을 개발합니다.

## 핵심 요구사항
1. **실시간 처리**: 15fps 이상, 지연시간 500ms 이내
2. **다수 인원 감지**: 동시 5명 이상 추적 가능
3. **오탐 최소화**: 누워있음(Lying)과 낙상(Fall) 구분
4. **프라이버시 보호**: 개인 식별 불가 처리 옵션

## 기술 스택
- **Backend**: FastAPI + Python 3.10+
- **AI Models**: YOLOv8-Pose + MediaPipe (하이브리드)
- **Frontend**: React + TypeScript + Tailwind CSS
- **실시간 통신**: WebSocket
- **Database**: SQLite → PostgreSQL

## 레퍼런스 제품 기술 분석

### 1. 지오멕스소프트 AI-PAM 참고 기술
- PanopticDeepLab 기반 세그멘테이션
- I3D CNN + LSTM 행동 인식
- 환자/의료진 구분 기능
- 커튼, 침대 영역 비감지 기능
- 싱글 이미지 기반 깊이값(뎁스맵) 추출
- 야간 적외선 촬영 지원

### 2. 슈퍼게이트 FDD 참고 기술
- AI 기반 자세 분석
- 엣지 컴퓨팅 최적화
- PPE(보호구) 감지 연계 가능

### 3. AI Hub 데이터셋 활용
- 이상행동 CCTV 영상 (717시간, 8436컷)
- 12가지 클래스: 폭행, 싸움, 절도, 기물파손, **실신**, 배회, 침입 등
- XML 라벨링 형식

## 감지 알고리즘 3단계 구현

### Level 1: Bounding Box 비율 기반 (기초)
- 가로/세로 비율 분석: Width/Height >= 0.85 → 낙상 의심
- Head Drop 분석: 머리 위치 급격 하강

### Level 2: 공간적 관계 및 IoU 분석 (중급)
- 안전 구역(Safe-Zone) 필터링: 침대, 의자와의 IoU 분석
- IoU > 0.5 + 안전 가구 = 휴식으로 판단
- IoU < 0.2 + 움직임 없음 = 낙상으로 판단

### Level 3: 스켈레톤 기반 벡터 분석 (고급)
- 상체/하체 벡터와 수직 기준 벡터 비교
- 각도 임계값: 수평에 가까우면(< 0.5) 낙상 판정
- 속도 분석: 엉덩이/어깨 급격한 하강 감지

## 코드 작성 시 주의사항
1. 모든 코드에 한글 주석 필수 (물리치료사 출신 초보자 대상)
2. 각 함수/클래스에 docstring 작성
3. 타입 힌트 적용
4. 에러 처리 철저히
5. 단위 테스트 코드 포함

## 첨부 파일
[개발 로드맵 파일 첨부: SENTIO_개발로드맵.md]
[기획서 파일 첨부: SENTIO_사업기획서.docx]
[프로토타입 참조: sentio-v2.html]
```

---

## 📦 단계별 상세 프롬프트

### PHASE 1: 고급 낙상 감지 알고리즘 구현

#### 1-1. 3단계 낙상 감지 엔진 (AI-PAM 스타일)

```markdown
# 3단계 낙상 감지 엔진 구현 요청

## 참조 기술
- 지오멕스소프트 AI-PAM의 PanopticDeepLab + 스켈레톤 분석
- 제공된 기술 레퍼런스 문서의 Level 1/2/3 로직

## 구현할 파일
backend/app/core/advanced_fall_detector.py

## 클래스 구조

### FallDetectionLevel (Enum)
```python
class FallDetectionLevel(Enum):
    LEVEL_1_BBOX = "bbox"          # Bounding Box 비율
    LEVEL_2_SPATIAL = "spatial"    # 공간적 관계 + IoU
    LEVEL_3_SKELETON = "skeleton"  # 스켈레톤 벡터 분석
```

### SafeZone 데이터클래스
```python
@dataclass
class SafeZone:
    """안전 구역 (침대, 의자 등)"""
    name: str           # "bed", "chair", "sofa"
    bbox: tuple         # (x1, y1, x2, y2) 정규화 좌표
    is_active: bool     # 활성화 여부
```

### FallConditions 데이터클래스
```python
@dataclass
class FallConditions:
    """낙상 판단 조건들의 충족 여부"""
    # Level 1
    aspect_ratio_exceeded: bool     # 가로/세로 비율 초과
    head_drop_detected: bool        # 머리 급격 하강
    
    # Level 2
    outside_safe_zone: bool         # 안전 구역 밖
    low_iou_with_furniture: bool    # 가구와 IoU 낮음
    no_movement_detected: bool      # 움직임 없음
    
    # Level 3
    body_vector_horizontal: bool    # 몸통 벡터 수평
    rapid_descent_speed: bool       # 급격한 하강 속도
    skeleton_confidence_high: bool  # 스켈레톤 신뢰도 높음
    
    # 최종
    is_lying_not_fall: bool         # 누워있음 (낙상 아님)
```

### AdvancedFallDetector 클래스
```python
class AdvancedFallDetector:
    """
    지오멕스 AI-PAM 스타일 3단계 낙상 감지기
    
    Level 1: Bounding Box 비율 분석 (가장 빠름, CPU 친화적)
    Level 2: 공간적 관계 및 IoU 분석 (안전 구역 필터링)
    Level 3: 스켈레톤 벡터 분석 (가장 정밀, GPU 권장)
    """
    
    def __init__(self, config: DetectorConfig):
        pass
    
    def detect(
        self, 
        frame: np.ndarray, 
        pose_result: PoseResult,
        person_bbox: tuple,
        safe_zones: List[SafeZone]
    ) -> AdvancedFallResult:
        """3단계 낙상 감지 실행"""
        pass
    
    def _level1_bbox_analysis(self, bbox: tuple) -> dict:
        """Level 1: Bounding Box 비율 분석"""
        # 가로/세로 비율 계산
        # Width / Height >= 0.85 → 낙상 의심
        pass
    
    def _level2_spatial_analysis(
        self, 
        person_bbox: tuple, 
        safe_zones: List[SafeZone]
    ) -> dict:
        """Level 2: 공간적 관계 및 IoU 분석"""
        # 각 안전 구역과의 IoU 계산
        # IoU > threshold → 휴식 판단
        pass
    
    def _level3_skeleton_analysis(
        self, 
        pose_result: PoseResult
    ) -> dict:
        """Level 3: 스켈레톤 벡터 분석"""
        # 상체/하체 벡터 계산
        # 수직 기준 벡터와의 각도 계산
        pass
    
    def _calculate_iou(self, box1: tuple, box2: tuple) -> float:
        """두 박스 간 IoU 계산"""
        pass
    
    def _calculate_body_vectors(
        self, 
        landmarks: List[dict]
    ) -> tuple:
        """상체/하체 벡터 계산"""
        pass
    
    def _is_lying_vs_fall(
        self, 
        conditions: FallConditions
    ) -> bool:
        """누워있음 vs 낙상 구분 (오탐 방지 핵심)"""
        # AI-PAM 스타일: 움직임 + 위치 + 자세 종합 분석
        pass
```

## 핵심 알고리즘 상세

### 1. Bounding Box 비율 분석
```python
def _level1_bbox_analysis(self, bbox: tuple) -> dict:
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    
    aspect_ratio = width / height if height > 0 else 0
    
    return {
        "aspect_ratio": aspect_ratio,
        "exceeded": aspect_ratio >= 0.85,
        "confidence": min(aspect_ratio / 1.0, 1.0)
    }
```

### 2. IoU 계산 및 안전 구역 분석
```python
def _level2_spatial_analysis(self, person_bbox, safe_zones):
    results = []
    for zone in safe_zones:
        iou = self._calculate_iou(person_bbox, zone.bbox)
        results.append({
            "zone_name": zone.name,
            "iou": iou,
            "is_safe": iou > 0.5  # 50% 이상 겹치면 안전
        })
    
    # 모든 안전 구역에서 벗어났는지 확인
    outside_all_zones = all(r["iou"] < 0.2 for r in results)
    
    return {
        "zone_analysis": results,
        "outside_safe_zones": outside_all_zones
    }
```

### 3. 스켈레톤 벡터 분석
```python
def _level3_skeleton_analysis(self, pose_result):
    landmarks = pose_result.landmarks
    
    # 어깨 중심점
    shoulder_center = (
        (landmarks[11]["x"] + landmarks[12]["x"]) / 2,
        (landmarks[11]["y"] + landmarks[12]["y"]) / 2
    )
    
    # 엉덩이 중심점
    hip_center = (
        (landmarks[23]["x"] + landmarks[24]["x"]) / 2,
        (landmarks[23]["y"] + landmarks[24]["y"]) / 2
    )
    
    # 상체 벡터 (어깨 → 엉덩이)
    upper_vector = (
        hip_center[0] - shoulder_center[0],
        hip_center[1] - shoulder_center[1]
    )
    
    # 수직 기준 벡터 (아래 방향)
    vertical_ref = (0, 1)
    
    # 코사인 유사도 계산
    dot_product = upper_vector[0] * vertical_ref[0] + upper_vector[1] * vertical_ref[1]
    magnitude = math.sqrt(upper_vector[0]**2 + upper_vector[1]**2)
    cos_similarity = dot_product / magnitude if magnitude > 0 else 0
    
    # 수평에 가까우면 (cos < 0.5) 낙상 의심
    is_horizontal = abs(cos_similarity) < 0.5
    
    return {
        "upper_vector": upper_vector,
        "cos_similarity": cos_similarity,
        "is_horizontal": is_horizontal,
        "body_angle": math.degrees(math.acos(abs(cos_similarity)))
    }
```

## 출력 형식
- 완전한 Python 코드
- 각 메서드에 한글 주석
- 단위 테스트 코드 (tests/test_advanced_fall_detector.py)
- 사용 예시 코드
```

---

#### 1-2. YOLOv8-Pose + MediaPipe 하이브리드 파이프라인

```markdown
# YOLOv8-Pose + MediaPipe 하이브리드 파이프라인 구현

## 목적
- YOLOv8: 다수 인원 동시 탐지 + 바운딩 박스
- MediaPipe: 개인별 정밀 관절점 추출

## 참조 기술
- 제공된 레퍼런스 문서의 "하이브리드 접근" 섹션
- Top-down 방식 (객체 먼저 → 관절점 추출)

## 구현할 파일
backend/app/core/hybrid_pose_pipeline.py

## 클래스 구조

```python
from ultralytics import YOLO
import mediapipe as mp
from dataclasses import dataclass
from typing import List, Optional
import numpy as np

@dataclass
class PersonPose:
    """개인별 포즈 정보"""
    person_id: int              # 추적 ID
    bbox: tuple                 # (x1, y1, x2, y2)
    bbox_confidence: float      # YOLO 탐지 신뢰도
    keypoints_yolo: List[dict]  # YOLO 17개 관절점
    keypoints_mp: List[dict]    # MediaPipe 33개 관절점
    pose_confidence: float      # 포즈 추정 신뢰도

class HybridPosePipeline:
    """
    YOLOv8-Pose + MediaPipe 하이브리드 파이프라인
    
    처리 흐름:
    1. YOLOv8-Pose로 다수 인원 탐지 + 기본 관절점
    2. 각 인원 영역을 crop
    3. crop된 영역에 MediaPipe 적용하여 정밀 관절점 추출
    4. 두 결과 융합
    """
    
    def __init__(
        self,
        yolo_model: str = "yolov8m-pose.pt",
        use_mediapipe: bool = True,
        confidence_threshold: float = 0.5
    ):
        # YOLO 모델 로드
        self.yolo = YOLO(yolo_model)
        
        # MediaPipe 초기화
        if use_mediapipe:
            self.mp_pose = mp.solutions.pose.Pose(
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
        
        self.use_mediapipe = use_mediapipe
        self.confidence_threshold = confidence_threshold
    
    def process(self, frame: np.ndarray) -> List[PersonPose]:
        """
        프레임 처리 메인 메서드
        
        Args:
            frame: BGR 이미지 (OpenCV 형식)
        
        Returns:
            PersonPose 리스트
        """
        # 1단계: YOLO로 사람 탐지 + 기본 포즈
        yolo_results = self._detect_with_yolo(frame)
        
        persons = []
        for idx, detection in enumerate(yolo_results):
            bbox = detection["bbox"]
            yolo_keypoints = detection["keypoints"]
            
            # 2단계: 옵션에 따라 MediaPipe로 정밀 분석
            mp_keypoints = None
            if self.use_mediapipe:
                cropped = self._crop_person(frame, bbox)
                mp_keypoints = self._analyze_with_mediapipe(cropped, bbox)
            
            # 3단계: 결과 융합
            persons.append(PersonPose(
                person_id=idx,
                bbox=bbox,
                bbox_confidence=detection["confidence"],
                keypoints_yolo=yolo_keypoints,
                keypoints_mp=mp_keypoints,
                pose_confidence=self._calculate_pose_confidence(
                    yolo_keypoints, mp_keypoints
                )
            ))
        
        return persons
    
    def _detect_with_yolo(self, frame: np.ndarray) -> List[dict]:
        """YOLOv8-Pose로 탐지"""
        results = self.yolo(frame, classes=[0], verbose=False)
        
        detections = []
        for r in results:
            boxes = r.boxes
            keypoints = r.keypoints
            
            for i in range(len(boxes)):
                if boxes.conf[i] < self.confidence_threshold:
                    continue
                
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()
                
                # YOLO 17개 관절점 추출
                kpts = keypoints.data[i].tolist() if keypoints else []
                
                detections.append({
                    "bbox": (x1, y1, x2, y2),
                    "confidence": boxes.conf[i].item(),
                    "keypoints": self._format_yolo_keypoints(kpts)
                })
        
        return detections
    
    def _crop_person(
        self, 
        frame: np.ndarray, 
        bbox: tuple,
        padding: float = 0.1
    ) -> np.ndarray:
        """개인 영역 crop (패딩 포함)"""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        
        # 패딩 추가
        pad_w = (x2 - x1) * padding
        pad_h = (y2 - y1) * padding
        
        x1 = max(0, int(x1 - pad_w))
        y1 = max(0, int(y1 - pad_h))
        x2 = min(w, int(x2 + pad_w))
        y2 = min(h, int(y2 + pad_h))
        
        return frame[y1:y2, x1:x2]
    
    def _analyze_with_mediapipe(
        self, 
        cropped: np.ndarray,
        original_bbox: tuple
    ) -> List[dict]:
        """MediaPipe로 정밀 관절점 추출"""
        if cropped.size == 0:
            return None
        
        rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        results = self.mp_pose.process(rgb)
        
        if not results.pose_landmarks:
            return None
        
        # crop 좌표를 원본 좌표로 변환
        landmarks = []
        x1, y1, x2, y2 = original_bbox
        crop_w, crop_h = x2 - x1, y2 - y1
        
        for i, lm in enumerate(results.pose_landmarks.landmark):
            landmarks.append({
                "index": i,
                "x": x1 + lm.x * crop_w,  # 원본 이미지 좌표
                "y": y1 + lm.y * crop_h,
                "z": lm.z,
                "visibility": lm.visibility
            })
        
        return landmarks
    
    def _format_yolo_keypoints(self, kpts: List) -> List[dict]:
        """YOLO 관절점 포맷 변환"""
        # YOLO 17개 관절점: nose, eyes, ears, shoulders, elbows, wrists, 
        #                   hips, knees, ankles
        names = [
            "nose", "left_eye", "right_eye", "left_ear", "right_ear",
            "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
            "left_wrist", "right_wrist", "left_hip", "right_hip",
            "left_knee", "right_knee", "left_ankle", "right_ankle"
        ]
        
        formatted = []
        for i, kpt in enumerate(kpts):
            if len(kpt) >= 3:
                formatted.append({
                    "index": i,
                    "name": names[i] if i < len(names) else f"point_{i}",
                    "x": kpt[0],
                    "y": kpt[1],
                    "confidence": kpt[2]
                })
        
        return formatted
    
    def _calculate_pose_confidence(
        self, 
        yolo_kpts: List[dict],
        mp_kpts: List[dict]
    ) -> float:
        """두 모델의 결과를 종합한 신뢰도 계산"""
        scores = []
        
        if yolo_kpts:
            yolo_conf = np.mean([k.get("confidence", 0) for k in yolo_kpts])
            scores.append(yolo_conf)
        
        if mp_kpts:
            mp_conf = np.mean([k.get("visibility", 0) for k in mp_kpts])
            scores.append(mp_conf)
        
        return np.mean(scores) if scores else 0.0
```

## 테스트 요구사항
- 단일 인원 / 다중 인원 테스트
- YOLO only vs Hybrid 성능 비교
- FPS 측정
```

---

#### 1-3. 안전 구역(Safe-Zone) 관리 시스템

```markdown
# 안전 구역(Safe-Zone) 관리 시스템 구현

## 목적
- 침대, 의자, 소파 등 안전 가구 영역 정의
- 해당 영역 내 누워있음 = 정상 (오탐 방지)
- AI-PAM의 "커튼, 침대 영역 비감지 기능" 참고

## 구현할 파일
backend/app/core/safe_zone_manager.py

## 요구사항

### SafeZoneManager 클래스
```python
class SafeZoneManager:
    """
    안전 구역 관리자
    
    기능:
    1. 안전 구역(침대, 의자 등) CRUD
    2. 실시간 IoU 계산
    3. 구역 내/외 상태 판단
    4. 구역별 비감지 설정
    """
    
    def __init__(self):
        self.zones: List[SafeZone] = []
    
    def add_zone(
        self, 
        name: str, 
        bbox: tuple, 
        zone_type: str = "furniture"
    ) -> SafeZone:
        """안전 구역 추가"""
        pass
    
    def remove_zone(self, zone_id: str) -> bool:
        """안전 구역 제거"""
        pass
    
    def update_zone(self, zone_id: str, **kwargs) -> SafeZone:
        """안전 구역 업데이트"""
        pass
    
    def check_person_safety(
        self, 
        person_bbox: tuple
    ) -> SafetyStatus:
        """
        사람이 안전 구역에 있는지 확인
        
        Returns:
            SafetyStatus:
                - in_safe_zone: bool
                - zone_name: Optional[str]
                - iou: float
                - should_suppress_alert: bool (알림 억제 여부)
        """
        pass
    
    def get_zones_for_camera(self, camera_id: str) -> List[SafeZone]:
        """특정 카메라의 안전 구역 목록"""
        pass
    
    def auto_detect_furniture(
        self, 
        frame: np.ndarray
    ) -> List[SafeZone]:
        """
        YOLO로 가구 자동 탐지 (선택적 기능)
        - bed, chair, couch 클래스 탐지
        - COCO 데이터셋 클래스 ID: bed=59, chair=56, couch=57
        """
        pass
```

### 구역 타입 정의
```python
class ZoneType(Enum):
    BED = "bed"           # 침대 - 누워있어도 정상
    CHAIR = "chair"       # 의자 - 앉아있어도 정상
    SOFA = "sofa"         # 소파 - 누워있어도 정상
    WHEELCHAIR = "wheelchair"  # 휠체어
    RESTRICTED = "restricted"  # 출입 금지 구역
    PRIVACY = "privacy"   # 프라이버시 구역 (감지 제외)
```

### REST API 엔드포인트
- GET /api/zones - 전체 구역 목록
- POST /api/zones - 구역 추가
- PUT /api/zones/{id} - 구역 수정
- DELETE /api/zones/{id} - 구역 삭제
- POST /api/zones/auto-detect - 자동 탐지

## UI 요구사항
- 비디오 위에 드래그로 구역 그리기
- 구역별 색상 구분
- 활성화/비활성화 토글
```

---

### PHASE 2: AI Hub 데이터셋 활용

#### 2-1. AI Hub 이상행동 데이터셋 로더

```markdown
# AI Hub 이상행동 CCTV 데이터셋 로더 구현

## 데이터셋 정보
- URL: https://aihub.or.kr/aidata/139
- 12가지 이상행동: 폭행, 싸움, 절도, 기물파손, **실신**, 배회, 침입, 투기, 강도, 데이트폭력, 납치, 주취행동
- 총 717시간 (8,436컷)
- 포맷: 영상(.mp4) + 라벨(.xml)

## 구현할 파일
backend/app/data/aihub_dataset_loader.py

## 요구사항

### AIHubDatasetLoader 클래스
```python
class AIHubDatasetLoader:
    """
    AI Hub 이상행동 CCTV 데이터셋 로더
    
    주요 활용 클래스:
    - faint (실신): 낙상 감지 학습에 활용
    - wandering (배회): 이상 행동 감지에 활용
    """
    
    def __init__(self, data_root: str):
        self.data_root = data_root
        self.class_map = {
            "assault": 0,      # 폭행
            "fight": 1,        # 싸움
            "theft": 2,        # 절도
            "vandalism": 3,    # 기물파손
            "faint": 4,        # 실신 ⭐ (낙상과 유사)
            "wandering": 5,    # 배회
            "intrusion": 6,    # 침입
            "dumping": 7,      # 투기
            "robbery": 8,      # 강도
            "violence": 9,     # 데이트폭력
            "kidnapping": 10,  # 납치
            "drunken": 11      # 주취행동
        }
    
    def load_dataset(
        self, 
        classes: List[str] = ["faint", "wandering"],
        split: str = "train"
    ) -> Dataset:
        """지정된 클래스의 데이터셋 로드"""
        pass
    
    def parse_xml_label(self, xml_path: str) -> dict:
        """XML 라벨 파싱"""
        pass
    
    def extract_frames(
        self, 
        video_path: str, 
        event_times: List[tuple]
    ) -> List[np.ndarray]:
        """이벤트 구간 프레임 추출"""
        pass
    
    def convert_to_yolo_format(
        self, 
        xml_labels: dict
    ) -> str:
        """YOLO 학습용 포맷 변환"""
        pass
```

### XML 라벨 구조 파싱
```xml
<!-- AI Hub 라벨 예시 -->
<annotation>
    <video_info>
        <filename>video_001.mp4</filename>
        <duration>60.0</duration>
    </video_info>
    <events>
        <event>
            <action>faint</action>
            <start_time>15.5</start_time>
            <end_time>45.2</end_time>
            <bbox>100,200,300,400</bbox>
        </event>
    </events>
</annotation>
```

## 데이터 증강 파이프라인
- 회전 (±15도)
- 밝기 조절 (±30%)
- 노이즈 추가
- 좌우 반전
- 스케일링 (0.8~1.2)
```

---

### PHASE 3: 실시간 알림 시스템

#### 3-1. 다중 채널 알림 시스템 (AI-PAM 스타일)

```markdown
# 다중 채널 알림 시스템 구현

## 참조
- AI-PAM: 스마트폰 앱, 스마트 워치, 태블릿, 간호사 스테이션

## 구현할 파일
backend/app/services/notification_service.py

## 알림 채널
1. WebSocket (웹 대시보드)
2. Firebase Cloud Messaging (모바일 앱)
3. Telegram Bot (선택)
4. SMS (선택)

## 요구사항

### NotificationService 클래스
```python
class NotificationService:
    """
    다중 채널 알림 서비스
    
    알림 레벨:
    - INFO: 일반 정보 (로그만)
    - WARNING: 주의 필요 (화면 표시)
    - DANGER: 긴급 (모든 채널 발송)
    """
    
    async def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        data: dict,
        channels: List[str] = ["websocket", "fcm"]
    ) -> dict:
        """알림 발송"""
        pass
    
    async def send_to_websocket(
        self, 
        message: dict
    ) -> bool:
        """WebSocket으로 실시간 전송"""
        pass
    
    async def send_to_fcm(
        self, 
        title: str, 
        body: str, 
        data: dict
    ) -> bool:
        """Firebase Cloud Messaging 푸시"""
        pass
    
    async def send_to_telegram(
        self, 
        message: str, 
        image: Optional[bytes] = None
    ) -> bool:
        """Telegram 봇 메시지"""
        pass
```

### 알림 에스컬레이션 로직
```python
class AlertEscalation:
    """
    시간 기반 알림 에스컬레이션
    
    0~3초: 내부 로그만
    3~10초: WARNING 알림 (대시보드)
    10초+: DANGER 알림 (모든 채널)
    30초+: 2차 알림 (관리자 호출)
    """
    
    def check_escalation(
        self, 
        event_id: str, 
        duration: float
    ) -> AlertLevel:
        pass
```

## WebSocket 메시지 포맷
```json
{
    "type": "alert",
    "level": "danger",
    "timestamp": "2024-01-15T14:32:15.123Z",
    "payload": {
        "event_id": "evt_abc123",
        "title": "🚨 낙상 감지",
        "message": "대기실에서 낙상이 감지되었습니다",
        "camera_id": "cam_01",
        "person_id": 1,
        "duration": 12.5,
        "confidence": 0.92,
        "snapshot_url": "/api/events/evt_abc123/snapshot"
    }
}
```
```

---

### PHASE 4: 프론트엔드 고도화

#### 4-1. 안전 구역 설정 UI

```markdown
# 안전 구역 설정 UI 컴포넌트 구현

## 참조 디자인
- 디자인 레퍼런스 문서 참조
- AI-PAM의 커튼/침대 비감지 설정 UI

## 구현할 컴포넌트
frontend/src/components/SafeZone/SafeZoneEditor.jsx

## 요구사항

### 기능
1. 비디오 위에 드래그로 사각형 영역 그리기
2. 영역 타입 선택 (침대, 의자, 소파, 프라이버시)
3. 영역 리사이즈 / 이동 / 삭제
4. 영역별 색상 및 라벨 표시
5. 활성화/비활성화 토글

### 컴포넌트 구조
```jsx
// SafeZoneEditor.jsx
const SafeZoneEditor = ({ videoRef, onZonesChange }) => {
    const [zones, setZones] = useState([]);
    const [isDrawing, setIsDrawing] = useState(false);
    const [selectedZone, setSelectedZone] = useState(null);
    
    // 마우스 드래그로 영역 그리기
    const handleMouseDown = (e) => { ... };
    const handleMouseMove = (e) => { ... };
    const handleMouseUp = (e) => { ... };
    
    // 영역 렌더링
    const renderZones = () => { ... };
    
    return (
        <div className="safe-zone-editor">
            {/* 비디오 오버레이 캔버스 */}
            <canvas 
                ref={canvasRef}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
            />
            
            {/* 영역 목록 패널 */}
            <SafeZoneList 
                zones={zones}
                onSelect={setSelectedZone}
                onDelete={handleDeleteZone}
                onToggle={handleToggleZone}
            />
            
            {/* 타입 선택 팝업 */}
            {showTypeSelector && (
                <ZoneTypeSelector 
                    onSelect={handleTypeSelect}
                />
            )}
        </div>
    );
};
```

### 스타일 가이드
- 침대: 파란색 반투명 (#3B82F620)
- 의자: 녹색 반투명 (#10B98120)
- 소파: 보라색 반투명 (#8B5CF620)
- 프라이버시: 회색 해시 패턴
```

---

## 🔧 트러블슈팅 프롬프트

### 오탐(False Positive) 문제 해결

```markdown
# 오탐 문제 해결 요청

## 상황
[구체적인 오탐 상황 설명]
예: "환자가 의자에 앉아있는데 낙상으로 감지됨"

## 현재 설정값
- head_hip_threshold: 0.02
- horizontal_angle_threshold: 40
- ground_threshold: 0.70

## 요청
1. 오탐 원인 분석
2. 임계값 조정 권장안
3. 추가 필터링 로직 제안
4. AI-PAM의 오탐 방지 기법 참고

## 참고
- AI-PAM: "앉아 있음"과 "낙상" 구분 위해 어깨 높이와 침대 높이 비교
- Safe-Zone IoU 분석으로 가구 위 상태 필터링
```

### 성능 최적화 문제

```markdown
# 성능 최적화 요청

## 상황
- 현재 FPS: [현재 값]
- 목표 FPS: 15fps 이상
- 하드웨어: [GPU 있음/없음]

## 요청
1. 병목 지점 분석
2. 최적화 방안 제안:
   - TensorRT 변환
   - 프레임 스킵
   - 모델 경량화 (YOLOv8n)
   - 양자화 (FP16/INT8)
3. 레퍼런스 문서의 "성능 최적화" 섹션 참고

## 참고
- 슈퍼게이트: ASIC 기반 엣지 최적화
- 지오멕스: 빠른 추론 속도의 병실 특화 모델
```

---

## 📋 개발 완료 체크리스트

```markdown
# SENTIO 개발 완료 점검

## Phase 1: 핵심 AI 엔진
- [ ] 3단계 낙상 감지 알고리즘 (Level 1/2/3)
- [ ] YOLOv8-Pose + MediaPipe 하이브리드
- [ ] 안전 구역(Safe-Zone) 관리
- [ ] 오탐 방지 로직 (Lying vs Fall)

## Phase 2: 데이터 & 학습
- [ ] AI Hub 데이터셋 로더
- [ ] 데이터 증강 파이프라인
- [ ] 커스텀 학습 스크립트

## Phase 3: 알림 시스템
- [ ] 다중 채널 알림 (WebSocket, FCM)
- [ ] 알림 에스컬레이션
- [ ] 이벤트 로깅 및 저장

## Phase 4: UI/UX
- [ ] 실시간 대시보드
- [ ] 안전 구역 설정 UI
- [ ] 모바일 반응형

## Phase 5: 배포 & 최적화
- [ ] Docker 컨테이너화
- [ ] TensorRT 최적화
- [ ] 성능 테스트 (15fps 달성)

## 레퍼런스 제품 기능 구현 확인
- [ ] AI-PAM 스타일 세그멘테이션
- [ ] AI-PAM 스타일 프라이버시 보호 (마스킹)
- [ ] AI-PAM 스타일 주야간 통합 검출
- [ ] 슈퍼게이트 스타일 엣지 최적화
```

---

## 📚 추가 참고 자료

### 논문 및 기술 문서
- PanopticDeepLab (Google, 2020)
- YOLOv8-Pose 문서: https://docs.ultralytics.com/tasks/pose/
- MediaPipe Pose: https://google.github.io/mediapipe/solutions/pose.html
- ByteTrack: https://github.com/ifzhang/ByteTrack

### 레퍼런스 제품 상세
- 지오멕스소프트: https://geomex.co.kr
- 슈퍼게이트: https://supergate.co.kr
- AI Hub: https://aihub.or.kr

---

*이 프롬프트 모음은 레퍼런스 제품의 기술을 참고하여 전문가 수준의 낙상 감지 시스템을 구현하기 위해 작성되었습니다.*
