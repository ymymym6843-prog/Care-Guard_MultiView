# SENTIO WAITING AI - Claude Code 개발 프롬프트 모음

## 📌 사용 방법

이 문서는 Claude Code에서 SENTIO 프로젝트를 개발할 때 사용할 프롬프트 모음입니다.

**사용 순서:**
1. 먼저 "프로젝트 초기화 프롬프트"를 실행
2. 이후 단계별로 순차적으로 프롬프트 실행
3. 각 단계 완료 후 테스트 진행
4. 문제 발생 시 "트러블슈팅 프롬프트" 활용

**팁:**
- 프롬프트 복사 후 Claude Code에 붙여넣기
- `[참조 파일]` 부분에 실제 파일 경로 입력
- 에러 발생 시 에러 메시지와 함께 다시 질문

---

## 🚀 0. 프로젝트 초기화 프롬프트

### 0-1. 프로젝트 생성 및 구조 설정

```
SENTIO WAITING AI 프로젝트를 초기화해줘.

## 프로젝트 개요
- 요양병원 대기실 낙상 감지 웹 애플리케이션
- FastAPI 백엔드 + React 프론트엔드
- MediaPipe Pose 기반 실시간 포즈 분석

## 참조 문서
[개발 로드맵 파일 첨부: SENTIO_개발로드맵.md]

## 요청사항
1. 프로젝트 폴더 구조 생성 (로드맵의 "프로젝트 구조" 참조)
2. backend/requirements.txt 생성 (로드맵의 의존성 참조)
3. frontend/package.json 생성
4. .env.example 파일 생성
5. README.md 기본 템플릿 생성
6. .gitignore 파일 생성

## 주의사항
- Python 3.10+ 기준
- 모든 코드에 한글 주석 추가
- 코딩 초보자도 이해할 수 있도록 상세한 주석 작성
```

### 0-2. 개발 환경 설정 가이드

```
SENTIO 프로젝트의 개발 환경 설정 가이드를 작성해줘.

## 필요한 내용
1. Python 가상환경 생성 및 활성화 방법
2. 백엔드 의존성 설치 명령어
3. 프론트엔드 의존성 설치 명령어
4. VS Code 추천 확장 프로그램
5. 환경 변수 설정 방법

## 대상
- 코딩 초보자 (물리치료사 출신)
- Windows 사용자 기준으로 작성
- 각 단계별로 스크린샷 없이도 따라할 수 있도록 상세히 설명
```

---

## 📦 1단계: MVP 개발 프롬프트

### 1-1. FastAPI 백엔드 기초

```
SENTIO 백엔드의 FastAPI 기본 구조를 만들어줘.

## 참조
[개발 로드맵 파일 첨부]

## 구현할 파일들
1. backend/app/main.py - FastAPI 앱 진입점
2. backend/app/config.py - 환경 설정 관리 (Pydantic Settings)
3. backend/app/api/deps.py - 공통 의존성

## main.py 요구사항
- FastAPI 앱 인스턴스 생성
- CORS 미들웨어 설정 (모든 origin 허용 - 개발용)
- 기본 health check 엔드포인트 ("/health")
- 앱 시작/종료 이벤트 핸들러
- 라우터 등록 준비 (주석으로)

## config.py 요구사항
- pydantic-settings 사용
- 환경변수: CAMERA_INDEX, DEBUG, HOST, PORT
- 기본값 설정

## 주석 요청
- 각 코드 블록마다 "이 부분이 하는 일" 한글 주석
- FastAPI 데코레이터 설명
- 초보자가 이해할 수 있는 수준
```

### 1-2. 카메라 서비스 구현

```
웹캠 연결 및 프레임 캡처를 담당하는 카메라 서비스를 구현해줘.

## 참조
[개발 로드맵 파일 첨부]

## 구현할 파일
backend/app/services/camera_service.py

## 요구사항
1. CameraService 클래스 구현
   - __init__: 카메라 인덱스 설정
   - start(): 카메라 연결 시작
   - stop(): 카메라 연결 종료
   - get_frame(): 현재 프레임 가져오기
   - is_running: 실행 상태 프로퍼티
   - get_available_cameras(): 사용 가능한 카메라 목록 (static method)

2. OpenCV 사용
   - cv2.VideoCapture 활용
   - 해상도 설정 기능 (1280x720 기본)
   - FPS 설정 기능

3. 에러 처리
   - 카메라 연결 실패 시 예외 처리
   - 프레임 읽기 실패 시 None 반환

## 추가 요청
- 각 메서드에 docstring 작성
- 사용 예시 주석으로 추가
- 테스트 코드도 함께 작성 (tests/test_camera_service.py)
```

### 1-3. MediaPipe 포즈 감지기

```
MediaPipe Pose를 사용한 포즈 감지기를 구현해줘.

## 참조
[개발 로드맵의 pose_detector.py 예시 참조]

## 구현할 파일
backend/app/core/pose_detector.py

## 요구사항

### PoseResult 데이터클래스
- landmarks: 33개 관절점 좌표 리스트
- head_y: 머리(코) Y 좌표 (0~1, 위가 0)
- hip_y: 엉덩이 평균 Y 좌표
- shoulder_y: 어깨 평균 Y 좌표
- body_angle: 몸통 기울기 각도 (0~90도)
- confidence: 감지 신뢰도
- timestamp: 감지 시간

### PoseDetector 클래스
- __init__(model_complexity): MediaPipe Pose 초기화
- detect(frame) -> Optional[PoseResult]: 포즈 감지
- _calculate_body_angle(): 몸통 기울기 계산
- draw_skeleton(frame, landmarks, color): 스켈레톤 그리기 (시각화용)

### 관절점 인덱스 상수 정의
- NOSE = 0
- LEFT_SHOULDER = 11
- RIGHT_SHOULDER = 12
- LEFT_HIP = 23
- RIGHT_HIP = 24
- 등등

## 주석 요청
- MediaPipe Pose가 무엇인지 설명
- 33개 관절점 구조 설명
- 좌표계 설명 (0~1 정규화, Y축 방향)
- body_angle 계산 수식 설명
```

### 1-4. 낙상 감지 알고리즘

```
낙상 감지 알고리즘을 구현해줘.

## 참조
[개발 로드맵의 fall_detector.py 예시 참조]
[프로토타입 HTML 파일의 감지 로직 참조: sentio-v2.html]

## 구현할 파일
backend/app/core/fall_detector.py

## 핵심 감지 조건 (4가지)
1. 머리가 엉덩이보다 아래 + 바닥 근처
2. 급격한 신체 하강 (히스토리 기반)
3. 몸통 수평 기울기 + 바닥 근처
4. (조합) 위 조건들의 복합 판단

## 요구사항

### AlertLevel Enum
- SAFE: 안전
- WARNING: 주의 (3초 이상)
- DANGER: 긴급 (10초 이상)

### DetectionSettings 데이터클래스
- head_hip_threshold: float = 0.02
- rapid_fall_threshold: float = 0.10
- horizontal_angle_threshold: float = 40
- ground_threshold: float = 0.70
- warning_time: float = 3.0
- danger_time: float = 10.0
- history_size: int = 10

### FallDetectionResult 데이터클래스
- level: AlertLevel
- reason: str (감지 이유 한글)
- duration: float (이상 지속 시간)
- conditions: dict (각 조건 충족 여부)
- confidence: float
- timestamp: float

### FallDetector 클래스
- __init__(settings)
- detect(pose_result) -> FallDetectionResult
- _check_conditions(pose) -> dict
- _determine_level(duration) -> AlertLevel
- update_settings(new_settings)
- reset(): 히스토리 초기화

## 상세 설명 요청
- 각 임계값이 의미하는 바
- 히스토리 기반 급락 감지 원리
- 왜 2단계 알림인지 (오탐 방지)
- 실제 낙상 시나리오 예시와 함께 설명
```

### 1-5. WebSocket 실시간 통신

```
실시간 데이터 전송을 위한 WebSocket 엔드포인트를 구현해줘.

## 참조
[개발 로드맵 참조]

## 구현할 파일들
1. backend/app/api/routes/websocket.py
2. backend/app/core/stream_processor.py (영상 처리 루프)

## websocket.py 요구사항

### ConnectionManager 클래스
- active_connections 리스트 관리
- connect(websocket): 연결 추가
- disconnect(websocket): 연결 제거
- broadcast(message): 모든 클라이언트에 전송
- send_personal(websocket, message): 특정 클라이언트에 전송

### WebSocket 엔드포인트
- /ws/stream: 실시간 포즈 + 알림 스트리밍

### 전송 메시지 형식
```json
{
  "type": "pose_update" | "alert" | "event" | "status",
  "payload": { ... },
  "timestamp": 1234567890.123
}
```

## stream_processor.py 요구사항

### StreamProcessor 클래스
- 카메라 서비스, 포즈 감지기, 낙상 감지기 통합
- 메인 처리 루프 (async)
- 프레임 처리 → 포즈 감지 → 낙상 판단 → WebSocket 전송
- FPS 제어 (목표: 15fps)

## 주석 요청
- WebSocket이 HTTP와 다른 점 설명
- 비동기(async/await) 개념 간단 설명
- 메시지 흐름 다이어그램 (텍스트로)
```

### 1-6. REST API 엔드포인트

```
기본 REST API 엔드포인트들을 구현해줘.

## 구현할 파일들
1. backend/app/api/routes/camera.py
2. backend/app/api/routes/events.py
3. backend/app/api/routes/settings.py

## camera.py 엔드포인트
- GET /api/camera/list: 사용 가능한 카메라 목록
- POST /api/camera/start: 스트리밍 시작 (body: camera_id, resolution)
- POST /api/camera/stop: 스트리밍 중지
- GET /api/camera/status: 현재 카메라 상태

## events.py 엔드포인트
- GET /api/events: 이벤트 로그 조회 (쿼리: limit, offset, type)
- GET /api/events/{id}: 특정 이벤트 조회
- DELETE /api/events: 전체 로그 삭제

## settings.py 엔드포인트
- GET /api/settings: 현재 설정 조회
- PUT /api/settings: 설정 업데이트
- POST /api/settings/reset: 기본값으로 초기화

## 요청/응답 모델
- Pydantic 모델로 정의
- 각 필드에 Field description 추가
- 예시값 포함

## 주석 요청
- 각 엔드포인트 용도 설명
- HTTP 메서드 선택 이유
- 에러 응답 처리 방법
```

### 1-7. React 프론트엔드 초기화

```
React + Vite 프론트엔드 프로젝트를 초기화하고 기본 구조를 만들어줘.

## 요구사항
1. Vite + React 프로젝트 생성
2. Tailwind CSS 설정
3. 기본 폴더 구조 생성
4. 전역 스타일 설정 (colors, fonts)

## 폴더 구조
frontend/src/
├── components/
│   ├── Dashboard/
│   ├── Alerts/
│   └── common/
├── hooks/
├── services/
├── store/
└── styles/

## 스타일 테마 (Tailwind 커스텀)
```js
colors: {
  safe: '#10B981',
  warning: '#F59E0B', 
  danger: '#EF4444',
  bg: '#0F172A',
  card: '#1E293B',
  border: '#334155',
  text: '#F8FAFC',
  'text-muted': '#94A3B8',
  accent: '#3B82F6'
}
```

## 생성할 기본 파일들
- App.jsx: 메인 앱 컴포넌트
- main.jsx: 엔트리포인트
- styles/globals.css: 전역 스타일
- services/api.js: API 호출 함수
- services/websocket.js: WebSocket 연결

## 주석 요청
- React 컴포넌트 구조 설명
- Tailwind CSS 사용법 간단 설명
- 폴더별 역할 설명
```

### 1-8. 대시보드 UI 컴포넌트

```
메인 대시보드 UI 컴포넌트들을 구현해줘.

## 참조
[프로토타입 HTML 파일: sentio-v2.html의 UI 디자인 참조]

## 구현할 컴포넌트들

### 1. Dashboard.jsx (메인 레이아웃)
- 헤더: 로고, 연결 상태, 시간 표시
- 메인: 비디오 영역 + 사이드바
- WebSocket 연결 관리
- 상태 관리 (Zustand 사용)

### 2. VideoFeed.jsx (비디오 영역)
- 캔버스에 스켈레톤 오버레이
- 상태 표시 오버레이 (안전/주의/위험)
- FPS, 해상도, 감지 인원 표시
- 상태별 테두리 색상 변경

### 3. StatusPanel.jsx (상태 패널)
- 현재 상태 아이콘 + 텍스트
- 측정값 표시 (머리 높이, 엉덩이 높이, 기울기, 지속 시간)
- 상태별 색상 변경

### 4. EventLog.jsx (이벤트 로그)
- 이벤트 목록 (최신순)
- 이벤트 타입별 아이콘
- 시간 표시
- 스크롤 가능한 리스트

### 5. SettingsPanel.jsx (설정 패널)
- 민감도 슬라이더들 (5개)
- 토글 스위치 (알림음, 스켈레톤, 측정값 표시)
- 기본값 복원 버튼

### 6. AlertModal.jsx (긴급 알림 모달)
- 전체 화면 오버레이
- 경고 아이콘 애니메이션
- 확인 버튼

## 스타일 요구사항
- 프로토타입(sentio-v2.html)의 디자인 그대로 구현
- 다크 테마
- 상태별 색상 (safe: 녹색, warning: 노랑, danger: 빨강)
- 반응형 (1024px 이하 단일 컬럼)

## 주석 요청
- 각 컴포넌트 역할 설명
- props 설명
- 이벤트 핸들러 설명
```

### 1-9. 커스텀 훅 구현

```
React 커스텀 훅들을 구현해줘.

## 구현할 훅들

### 1. useWebSocket.js
```js
const { 
  isConnected, 
  lastMessage, 
  sendMessage, 
  connect, 
  disconnect 
} = useWebSocket(url);
```
- 자동 재연결 기능
- 메시지 파싱
- 연결 상태 관리

### 2. useCamera.js
```js
const {
  cameras,
  selectedCamera,
  isStreaming,
  startStream,
  stopStream,
  selectCamera,
  refreshCameras
} = useCamera();
```
- 카메라 목록 조회
- 스트리밍 제어
- API 호출 래핑

### 3. useAlert.js
```js
const {
  currentLevel,
  showModal,
  dismissAlert,
  playSound
} = useAlert();
```
- 알림 상태 관리
- 알림음 재생 (Web Audio API)
- 모달 표시 제어

### 4. useSettings.js
```js
const {
  settings,
  updateSetting,
  resetSettings,
  isLoading
} = useSettings();
```
- 설정 조회/수정
- API 동기화
- 로컬 상태 관리

## 주석 요청
- 커스텀 훅이란 무엇인지
- 각 훅의 사용 예시
- 상태 관리 흐름 설명
```

### 1-10. 통합 테스트 및 실행

```
MVP 1단계 통합 테스트를 진행하고 실행 스크립트를 만들어줘.

## 요청사항

### 1. 테스트 코드 작성
- tests/test_pose_detector.py
- tests/test_fall_detector.py
- tests/test_api.py
- pytest 사용

### 2. 실행 스크립트
- scripts/run_dev.sh (Linux/Mac)
- scripts/run_dev.bat (Windows)
- 백엔드 + 프론트엔드 동시 실행

### 3. docker-compose.yml
- backend 서비스
- frontend 서비스
- 개발용 설정

### 4. 통합 테스트 체크리스트 문서
- 카메라 연결 확인
- 포즈 감지 확인
- 낙상 감지 확인 (실제 동작으로)
- WebSocket 연결 확인
- UI 표시 확인
- 알림 기능 확인

## 테스트 시나리오
1. 정상 자세 → 안전 상태 유지
2. 허리 숙이기 3초 이상 → 주의 알림
3. 바닥에 눕기 10초 이상 → 긴급 알림 + 모달
4. 일어서기 → 안전 상태 복귀

## 출력 형식
- 각 파일 전체 코드
- 실행 방법 상세 설명
- 예상되는 문제점과 해결책
```

---

## 🔧 트러블슈팅 프롬프트

### 카메라 연결 문제

```
카메라 연결이 안 되는 문제를 해결해줘.

## 에러 상황
[에러 메시지 붙여넣기]

## 환경
- OS: Windows 11
- Python: 3.10
- OpenCV: 4.8.1

## 시도한 것
[시도한 내용 작성]

## 요청
1. 에러 원인 분석
2. 해결 방법 단계별 안내
3. 카메라 연결 테스트 코드
```

### WebSocket 연결 문제

```
WebSocket 연결이 계속 끊어지는 문제를 해결해줘.

## 에러 상황
[에러 메시지 또는 증상 설명]

## 코드
[관련 코드 붙여넣기]

## 요청
1. 원인 분석
2. 재연결 로직 개선
3. 연결 상태 디버깅 방법
```

### 낙상 감지 정확도 문제

```
낙상 감지가 너무 민감하거나/둔감한 문제를 조정해줘.

## 현재 상황
- 문제: [오탐이 많음 / 미탐이 많음]
- 현재 설정값: [설정값 나열]

## 테스트 환경
- 카메라 위치: [설명]
- 조명 상태: [설명]
- 테스트 동작: [어떤 동작을 했는지]

## 요청
1. 임계값 조정 권장안
2. 추가 조건 제안
3. 디버깅용 로그 추가
```

---

## 📦 2단계 개발 프롬프트 (다수 인원 추적)

### 2-1. YOLO 사람 탐지 추가

```
YOLOv8을 사용한 다수 인원 탐지 기능을 추가해줘.

## 참조
[개발 로드맵 2단계 참조]

## 구현할 파일
backend/app/core/person_detector.py

## 요구사항
1. YOLOv8n 모델 사용 (경량 버전)
2. 사람만 탐지 (class 0)
3. 바운딩 박스 추출
4. 신뢰도 필터링 (threshold: 0.5)
5. 프레임 스킵으로 성능 최적화

## PersonDetector 클래스
- __init__(model_path, confidence_threshold)
- detect(frame) -> List[DetectedPerson]
- draw_boxes(frame, persons): 시각화용

## DetectedPerson 데이터클래스
- bbox: tuple (x1, y1, x2, y2)
- confidence: float
- center: tuple (cx, cy)
- area: float

## 주의사항
- GPU 없이 CPU에서도 동작해야 함
- 15fps 이상 유지
```

### 2-2. ByteTrack 객체 추적

```
ByteTrack을 사용해서 탐지된 사람들을 추적하고 ID를 부여해줘.

## 요구사항
1. YOLO 탐지 결과를 ByteTrack에 연결
2. 각 사람에게 고유 ID 부여
3. 프레임 간 ID 유지
4. 사라졌다 다시 나타나도 같은 ID 유지 (일정 시간 내)

## 구현할 파일
backend/app/core/person_tracker.py

## PersonTracker 클래스
- __init__(max_age, min_hits)
- update(detections) -> List[TrackedPerson]
- get_person(id) -> TrackedPerson

## TrackedPerson 데이터클래스
- id: int (고유 ID)
- bbox: tuple
- center: tuple
- velocity: tuple (이동 속도)
- age: int (추적 프레임 수)
- state: str (active/lost)
```

### 2-3. 다중 포즈 분석 통합

```
다수 인원 각각에 대해 개별 포즈 분석과 낙상 감지를 적용해줘.

## 요구사항
1. 각 TrackedPerson의 bbox 영역을 crop
2. crop된 영역에 MediaPipe Pose 적용
3. 사람별 FallDetector 인스턴스 관리
4. 여러 명이 동시에 위험 상태일 수 있음
5. UI에 사람별 상태 표시

## 구현/수정할 파일들
1. backend/app/core/multi_person_analyzer.py (새로 생성)
2. backend/app/core/stream_processor.py (수정)
3. frontend/src/components/Dashboard/VideoFeed.jsx (수정)

## MultiPersonAnalyzer 클래스
- __init__()
- analyze(frame) -> List[PersonAnalysisResult]
- _manage_detectors(): 사람별 FallDetector 생성/삭제
- get_all_status() -> dict

## PersonAnalysisResult 데이터클래스
- person_id: int
- pose_result: Optional[PoseResult]
- fall_result: FallDetectionResult
- bbox: tuple
```

---

## 📱 3단계 개발 프롬프트 (알림 고도화)

### 3-1. Firebase Cloud Messaging 연동

```
Firebase Cloud Messaging을 연동해서 모바일 푸시 알림을 구현해줘.

## 요구사항
1. Firebase 프로젝트 설정 가이드
2. 서버 측 FCM 전송 로직
3. 클라이언트 토큰 등록 API
4. 알림 메시지 템플릿

## 구현할 파일들
1. backend/app/services/notification.py
2. backend/app/api/routes/notification.py
3. frontend/src/services/firebase.js

## 알림 트리거 조건
- WARNING 상태 3초 지속 → 첫 번째 푸시
- DANGER 상태 진입 → 긴급 푸시
- 푸시 간격 최소 30초 (스팸 방지)

## 메시지 형식
{
  "title": "🚨 SENTIO 긴급 알림",
  "body": "대기실에서 낙상이 감지되었습니다. 즉시 확인이 필요합니다.",
  "data": {
    "event_id": "...",
    "level": "danger",
    "timestamp": "..."
  }
}
```

---

## 📋 전체 개발 완료 후 점검 프롬프트

```
SENTIO 1단계 MVP 개발 완료 점검을 해줘.

## 체크리스트 확인
1. 백엔드
   - [ ] FastAPI 서버 정상 실행
   - [ ] 모든 API 엔드포인트 동작
   - [ ] WebSocket 연결 안정성
   - [ ] 에러 핸들링 완료

2. AI 분석
   - [ ] MediaPipe 포즈 감지 정상
   - [ ] 낙상 감지 알고리즘 동작
   - [ ] 2단계 알림 시스템 동작

3. 프론트엔드
   - [ ] 대시보드 UI 완성
   - [ ] 실시간 데이터 표시
   - [ ] 알림 모달 동작
   - [ ] 설정 변경 기능

4. 테스트
   - [ ] 단위 테스트 통과
   - [ ] 통합 테스트 완료
   - [ ] 실제 환경 테스트

## 요청
1. 각 항목 점검 결과 보고
2. 미완료 항목 있으면 완료 방법 안내
3. 개선 권장 사항
4. 2단계 개발 준비 상태 확인
```

---

## 💡 추가 팁

### Claude Code 사용 시 권장사항

1. **한 번에 하나씩**: 프롬프트를 작은 단위로 나눠서 요청
2. **파일 첨부**: 관련 파일을 항상 첨부하여 컨텍스트 제공
3. **에러 공유**: 에러 발생 시 전체 에러 메시지 공유
4. **테스트 확인**: 각 단계 완료 후 반드시 테스트

### 자주 사용하는 명령어

```bash
# 백엔드 실행
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프론트엔드 실행
cd frontend
npm run dev

# 테스트 실행
pytest tests/ -v

# 의존성 설치
pip install -r requirements.txt
npm install
```

---

*이 프롬프트 모음은 SENTIO WAITING AI 프로젝트의 체계적인 개발을 위해 작성되었습니다.*
*각 프롬프트를 순서대로 실행하면서 개발을 진행하세요.*
