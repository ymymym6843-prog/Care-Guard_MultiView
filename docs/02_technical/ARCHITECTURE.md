# SENTIO 시스템 아키텍처

## 시스템 개요
요양병원 대기실의 카메라 영상을 실시간으로 분석하여 낙상을 감지하고 알림을 전달하는 웹 애플리케이션. YOLO11 기반 다중 인물 감지, COCO→MediaPipe 키포인트 변환, GRU ONNX 앙상블 분류기를 통한 하이브리드 파이프라인을 지원합니다. **GPU/CPU 자동 최적화**: GPU→`.pt`(CUDA+FP16), CPU→`.onnx`(ONNX Runtime, 2.7배 빠름) 자동 선택. 같은 가중치이므로 정확도 동일.

## 아키텍처 다이어그램 (ASCII)

```
                        +-------------------+
                        |    Frontend       |
                        | React + Vite      |
                        | (Tailwind, Radix) |
                        +--------+----------+
                                 |
                    WebSocket /ws/monitoring
                    REST API /api/*
                    WebRTC /whep
                                 |
                        +--------+----------+
                        |   FastAPI Server   |
                        |    (main.py)       |
                        +--------+----------+
                                 |
                +----------------+----+----+--------+
                |                |    |    |        |
        +-------+------+  +-----+-----+ +---+--+ +--+---+
        | API Routes   |  |   Core    | |Servs | |go2rtc|
        | auth, events |  | auth, db  | |      | | WebRTC
        | cameras,     |  | ws_mgr    | |YOLO11| | WHEP
        | settings, ws |  | logging   | |      | |      |
        | stream,      |  | exceptions| |ONNX  | +------+
        | zones, stats |  |           | |audit |
        | push         |  |           | |report|
        | push         |  |           | |fhir  |
        +--------------+  +-----------+ +------+
                                 |
                        +--------+----------+
                        |  PostgreSQL 16     |
                        | (async + sqlalchemy)|
                        +-------------------+
```

## 데이터 흐름

### 실시간 모니터링 파이프라인 (하이브리드)

#### YOLO 모드 (다중 인물)
```
Camera Feed
  → YOLO11s-pose (N명 감지, bbox + COCO 17 keypoints + track_id)
    [GPU: .pt + CUDA FP16 | CPU: .onnx + ONNX Runtime 자동 선택]
    → KeypointAdapter (COCO 17 → MediaPipe 33 변환)
      → ZoneChecker (Safe-Zone 판별: exclusion→스킵, safe→억제, danger→통과)
        → FallDetector (앙상블: rules + GRU ML)  ←── 착석 ML 노이즈 억제
          → AlertManager (확률 기반 상태 머신: WARNING 0.50+ / DANGER 0.70+)
              → ConnectionManager (WebSocket broadcast)
                → Frontend Dashboard
              → AuditService (INSERT-only 로깅)
                → PushService (알림)
                → PDF ReportService
```

#### 폴백 모드 (저사양)
```
Camera Feed
  → MediaPipe Pose (5인 제한)
    → PersonTracker (IoU 기반 ID 할당)
      → FallDetector (규칙 기반)
        → AlertManager
          → WebSocket broadcast
          → AuditService
            → PushService
```

### MJPEG 비디오 스트림
```
CameraService -> JPEG encode -> StreamingResponse -> <img> tag
```

### WebRTC 스트림 (go2rtc)
```
Camera (RTSP/MJPEG) -> go2rtc (MJPEG→WebRTC 변환)
  -> WHEP 프로토콜 -> Frontend WebRTCPlayer
```

### 알림 상태 머신 (확률 기반 차등 대응)
```
[확률 기반 WARNING/DANGER 분리]
  normal → monitoring (is_fallen=True, confidence < 0.50)
    → WARNING (confidence ≥ 0.50, 1.5초 유지)
      → DANGER (max_fall_confidence ≥ 0.70, WARNING 후 0.5초 경과)

  ※ GRU Binary 모델: fall_type="unknown" (방향 구분 없음)
  ※ max_fall_confidence: 낙상 에피소드 동안 최대 확신도 추적

[자동 회복]
  WARNING + 정상 포즈 → 3초 최소 유지 후 NORMAL
  DANGER + 정상 포즈 → 5초 대기 후 NORMAL (자동 리셋)
    ※ 재낙상 감지 시 회복 타이머 리셋

danger → acknowledged (확인 버튼 또는 Header 알림 버튼)
  → normal (정상 포즈 복귀)
```

### 낙상 감지 알고리즘 (FallDetector)

```
[기본 조건 (C1-C4)]
  C1: 머리-엉덩이 역전 (head_y < hip_y - threshold)
  C2: 급격한 하강 (descent_rate > threshold)
  C3: 수평 각도 (horizontal_angle > 45°)
  C4: 복합 점수 (head+hip+descent 조합)

[착석 조건 (C5-C7)]
  C5: 착석 전방 쏠림 (전방 기울기 임계값 초과)
  C6: 착석 측면 기울기 (측면 기울기 임계값 초과)
  C7: 착석 수직 하강 (착석 중 급격한 하강)

[확장 조건 (N1-N6, 선택적 활성화)]
  N1: 수직 가속도 (head_y 2차 미분 > threshold)
  N2: 보호 신전 반응 (팔 벌림 속도 감지)
  N3: 무게중심-지지면 이탈 (CoM-BoS deviation)
  N4: 무릎 좌굴 (knee angle 급격 감소)
  N5: 체간 회전 속도 (shoulder tilt delta)
  N6: 높이 궤적 패턴 (후반 가속 감지)

※ 총 13가지 조건 (C1-C7 + N1-N6)

[정확도 개선 알고리즘 (Phase 27)]
  1. Quick Recovery Detection (빠른 회복 감지)
     - lying < 10프레임 + standing ≥ 5프레임 연속
     - → 의도적 눕기/체조로 판정 (오탐 방지)
     - 적용 예: N_normal_standing_03.mp4 (65→14 프레임 오탐 감소)

  2. Multi-frame Accumulation (다중 프레임 누적)
     - 가시성 0.3~0.5 저화질 카메라 대응
     - 3프레임 연속 점수 ≥ 0.35 시 감지 트리거
     - 적용 예: AIHub C1/C4/C8 카메라 미탐 해결

  3. Controlled Movement Post-Fall (제어된 움직임 감지)
     - 낙상 후 10프레임 속도 분산 분석
     - 분산 < 0.0005 + 자세 ≠ LYING → 오탐 해제
     - 적용 예: 천천히 앉는 동작 오탐 방지

[V4 추가 FP 방지 (2026-02-08)]
  4. Standing FP Post-EMA 필터
     - standing + angle>75° + rule<0.20 + score<0.90 → 감지 취소
     - ML 극고확신(score>=0.90) 시 필터 면제

  5. 연속 프레임 완화
     - score>=0.70 + ml_raw>=0.60 → 1프레임 즉시 감지

  6. 착석 감지 완화
     - 0.85→0.75 임계값 하향, score cap 면제 확대

[Trip Fall Boost (걸려 넘어짐 감지)]
  - 전방 낙상 + 급격한 하강 조합 감지
  - FY_front_fall_trip.mp4 미탐 해결 (0→29-38프레임)

[앙상블 가중치 (설정 가능)]
  Rule: FALL_RULE_WEIGHT (기본 0.0)
  ML:   FALL_ML_WEIGHT (기본 1.0)  ← ML 100% 최적 (V4 벤치마크 결과: 424개 영상 F1 94.9)
  최종점수 = rule_score × rule_weight + ml_score × ml_weight

[V4 최종 벤치마크 (424개 영상)]
  Recall: 95.2%, Precision: 94.6%, F1: 94.9
  FP: 17, FN: 15
  카테고리별: BY 99%, FY 97%, SY 91%, N 정상감지율 83%
```

프론트엔드 매핑:
  NORMAL → "safe"
  MONITORING → "warning" (주의: 전조 감지)
  WARNING → "warning" (경고: 낙상 감지)
  DANGER → "danger" (위험: 즉시 확인 필요)

타이밍 설정값:
  FALL_WARNING_SECONDS = 1.5초 (MONITORING → WARNING)
  FALL_DANGER_SECONDS = 0.5초 (WARNING → DANGER, max_confidence ≥ 0.70)
  FALL_DANGER_CONFIDENCE = 0.70 (DANGER 전환 확신도 임계값)
```

## Backend 서비스 구조

### core/ - 핵심 인프라
- `auth.py` - JWT 토큰 발급/검증, HttpOnly 쿠키 설정/삭제, 리프레시 토큰 (7일), 토큰 타입 검증 (access/refresh 분리), 비밀번호 해싱 (bcrypt), check-setup 플로우
- `database.py` - SQLAlchemy async 엔진, 세션 관리, PostgreSQL 연동 (Alembic 마이그레이션 지원)
- `connection_manager.py` - WebSocket 연결 관리, 브로드캐스트
- `logging_config.py` - 서비스별 named logger 설정
- `exceptions.py` - 커스텀 예외 계층 (SentioError 기반)

### services/ - 비즈니스 로직
- `camera_service.py` - OpenCV 웹캠 캡처 (전용 스레드), JPEG 인코딩, RTSP 소스 지원, **다중 카메라 탐색/전환** (`list_available_cameras()`, `switch_camera()`), **플레이리스트 모드** (데모 영상 자동 순환), **카메라별 독립 리셋** (`reset_camera()` — 영상 전환 시 해당 카메라만 상태 초기화, 다른 카메라 GRU 버퍼 보존)
- `pose_service.py` - MediaPipe Pose 33관절점 추출, 스켈레톤 렌더링
- `multi_person_detector.py` - YOLO11s-pose + ByteTrack (lazy-load singleton), 다중 인물 감지 + 추적
- `fall_classifier.py` - GRU ONNX 분류기 (30-frame sequence), Binary 분류 (Fall/Normal), sigmoid 확률 출력, `predict_detailed()` → `FallPrediction`, **`reset_camera()`** (카메라별 GRU 버퍼 독립 초기화) — **GRU 모델 학습 완료: Recall 84.3%, Precision 97.0%, V4 최종 Recall 95.2%, Precision 94.6%, F1 94.9 (424개 영상)**
- `fall_detector.py` - 4조건 기반 낙상 감지 (머리-엉덩이 역전, 급하강, 수평각도, 복합점수), 규칙+ML 앙상블 (설정 가능 가중치: `FALL_RULE_WEIGHT`/`FALL_ML_WEIGHT`), `fall_type`/`rule_score`/`ml_score` 반환, **착석 ML 노이즈 스코어 억제** (착석 + 조건 미충족 시 ML 기여분 제거 → 시각적 오탐 제거), **정확도 개선 3종**: Quick Recovery Detection (lying <10프레임 + standing ≥5프레임 → 의도적 눕기 판정), Multi-frame Accumulation (가시성 0.3-0.5에서 3프레임 연속 ≥0.35 → 감지), Controlled Movement Post-Fall (낙상 후 10프레임 속도 분산 <0.0005 → 오탐 해제), **V4 FP 방지**: Standing FP Post-EMA 필터 (standing+angle>75°+rule<0.20+score<0.90 → 취소), 연속 프레임 완화 (score≥0.70+ml_raw≥0.60 → 1프레임), 착석 감지 완화 (임계값 0.85→0.75)
- `walking_aid_detector.py` - 보행도구 감지 (YOLO fine-tuning + MediaPipe 휴리스틱 하이브리드), WalkingAidDetector (YOLO ONNX), MediaPipeWalkingAidHeuristic (양손/엉덩이 위치 분석), WalkingAidStateTracker (인원-도구 매칭, 확립/분실 판정, per-person 상태), Graceful degradation (모델 없으면 휴리스틱만)
- `alert_manager.py` - 알림 상태 머신 (normal/monitoring/warning/danger/acknowledged), per-person 상태 추적, **확률 기반 차등 대응** (0.50~0.69 → WARNING, 0.70+ → DANGER 0.5초 지연), max_fall_confidence 추적, WARNING 3초 최소 유지, **`reset_camera()`** (카메라별 알림 상태 독립 초기화 + 전역 상태 재계산)
- `person_tracker.py` - IoU 기반 프레임 간 인물 추적 (안정적 person_id 할당), 폴백 모드용
- `monitoring_orchestrator.py` - 파이프라인 조합 (camera→pose→zone→fall→alert→broadcast), 모드 선택 (YOLO/폴백), ONNX 추론은 전용 ML 스레드풀에서 비동기 실행, **개발/데모 모드 pause/resume 지원** (`_paused` 플래그), **다중 카메라 순차 처리** (per-camera 상태 격리, 개별 카메라 독립 제어), **per-camera YOLO ByteTrack 트래커 격리** (카메라 간 track_id 충돌 방지)
- `zone_checker.py` - **Safe-Zone 파이프라인 연동 서비스**: DB에서 활성 zone 로드 (30초 TTL 캐시), Ray-casting point-in-polygon 판별, bbox 하단 중앙(발 위치) 기준점 사용, zone 우선순위 (exclusion > danger > safe), 실제 낙상(front/back/side_fall)은 safe zone에서도 알림 허용
- `event_recorder.py` - 이벤트 DB 기록 서비스 (warning/danger 알림 → Event 테이블 자동 저장, 통계/리포트 연동)
- `push_service.py` - Web Push 알림 (VAPID 키 기반, 선택적 활성화)
- `audit_service.py` - INSERT-only 감사 로깅, 이벤트 기록 및 조회
- `report_service.py` - reportlab 기반 PDF 보고서 생성 (일간/주간/월간)
- `fhir_service.py` - HL7 FHIR R4 Observation 리소스 생성, EMR 연동
- `iot_service.py` - IoT Webhook 기반 디바이스 알림 (경광등 등, 선택적 활성화)

### api/routes/ - HTTP/WS 엔드포인트
- `auth.py` - 로그인(쿠키 설정)/회원가입/로그아웃(쿠키 삭제)/사용자정보, check-setup, refresh(쿠키 갱신), 사용자 목록 (관리자용)
- `events.py` - 이벤트 로그 CRUD (페이지네이션), 감시 데이터 저장
- `cameras.py` - 카메라 상태/제어, RTSP 소스 설정, **다중 카메라 탐색/전환 API** (`GET /available`, `POST /switch`)
- `settings_route.py` - 런타임 설정 조회/변경, 감지 임계값, 앙상블 가중치 (`fall_rule_weight`/`fall_ml_weight`) 런타임 조정 (합계 검증 포함)
- `stream.py` - MJPEG 비디오 스트림 (카메라별 `/mjpeg/{camera_id}`), 쿠키/토큰 검증, asyncio.Semaphore 기반 동시 연결 제한, go2rtc 내부 인증 (INTERNAL_STREAM_KEY), **파이프라인 제어 API** (pause/resume — 카메라 제어와 분리)
- `ws.py` - WebSocket (모니터링 데이터 + 클라이언트 메시지), 쿠키 인증 우선 + query param 폴백
- `push.py` - 푸시 알림 구독 관리 (VAPID 키 조회, 구독/해지)
- `zones.py` - 안전지대 CRUD API, polygon 좌표 관리, zone_type (safe/danger/exclusion), CRUD 시 zone_checker 캐시 자동 무효화
- `stats.py` - 통계 API (일간/시간별/인물별/요약), Recharts 친화적 응답 형식
- `reports.py` - PDF 보고서 생성 API (일간/주간//월간), 통계 차트 포함
- `models.py` - **AI 모델 관리 API** (모델 목록 조회, 활성 모델 교체, 모델 파일 업로드) - YOLO11/YOLO26 전환 지원 (관리자 전용)
- `false_reports.py` - **오탐지/미탐지 보고 API** (CRUD + 통계 요약 + 이미지 첨부/조회, 임계치 초과 시 alert 포함 응답)
- `rooms.py` - **다중공간 관리 API** (Room CRUD, RoomCameraMapping 관리, 공간별 카메라 할당)


### models/ - 데이터 모델
- `user.py` - 사용자 (username, password, role, is_first_user)
- `event.py` - 이벤트 로그 (timestamp, alert_level, duration, confidence, person_id)
- `camera.py` - 카메라 설정 (name, rtsp_url, resolution)
- `push_subscription.py` - 푸시 구독 (endpoint, keys, user_id, is_active)
- `audit_log.py` - 감사 로그 (event_type, actor_id, target_id, action, timestamp, metadata) - INSERT-only
- `safe_zone.py` - 안전지대 (polygon 좌표 배열, camera_id, zone_type, created_by, is_active)

## Frontend 구조

### 상태 관리
- Zustand 단일 스토어 (`store/monitoring.ts`)
- AlertLevel, ConnectionStatus, PrivacyMode 타입 관리
- 사용자 인증: HttpOnly 쿠키 기반 (브라우저 자동 관리, 클라이언트 코드에 토큰 노출 없음)

### 주요 컴포넌트
- `DashboardView` - 메인 대시보드 레이아웃
- `LoginPage` - 로그인 (토큰 없음 시)
- `RegisterPage` - 첫 사용자 등록 (check-setup=true 시)
- `VideoFeed` - MJPEG 스트림 + 프라이버시 모드 (skeleton/blur/full)
- `WebRTCPlayer` - WHEP WebRTC 플레이어 (go2rtc 연동)
- `StatusCard` - 현재 알림 상태 표시
- `DangerAlertDialog` - 긴급 낙상 알림 모달 (진동 + 알림음)
- `EventLog` - 이벤트 이력 (ARIA live region)
- `SettingsCard` - 감지 설정 슬라이더
- `AlertSoundControl` - 알림음 볼륨/뮤트 제어
- `ConnectionStatus` - WebSocket 연결 상태 배지
- `OfflineBanner` - 오프라인 상태 인디케이터
- `UserManagement` - 관리자 사용자 관리 (추가/삭제/역할 변경)
- `StatsView` - 통계 대시보드 (Recharts, 차트 + 테이블)
- `SafeZoneEditor` - Canvas 기반 polygon 편집기 (zone_type 선택), **MJPEG 카메라 미리보기 오버레이** (정확한 영역 지정), LIVE 뱃지, 카메라 비활성 안내
- `ModelManager` - AI 모델 관리 (YOLO 모델 목록, 활성 모델 교체, 모델 설명 표시, YOLO26 정보 안내)

### 커스텀 훅
- `useWebSocket` - WS 연결 + 지수 백오프 자동 재연결 + heartbeat
- `useAlertSound` - Web Audio API 오실레이터 + Vibration API + **TTS 음성 알림** (Web Speech API, 한국어)
- `useSkeletonRenderer` - Canvas 2D 스켈레톤 렌더링
- `useEventLog` - 이벤트 로그 관리
- `useAcknowledge` - 알림 확인 처리
- `usePushNotifications` - Service Worker 푸시 구독 (VAPID 키 → 권한 요청 → 구독 등록)

### 라이브러리
- `auth.ts` - HttpOnly 쿠키 기반 인증 유틸리티, `apiCall()` 래퍼 (`credentials: "include"`, 401 자동 갱신), `checkAuth()`, `logout()`

## 인증 플로우 (HttpOnly 쿠키 기반)

```
[첫 시작]
  → check-setup 요청 (needs_setup=true)
    → RegisterPage (첫 사용자 가입)
      → POST /api/auth/register (credentials: "include")
      → POST /api/auth/login → Set-Cookie (access_token, refresh_token)
      → DashboardView 렌더링

[앱 초기화]
  → checkAuth() → GET /api/auth/me (credentials: "include")
    → 성공 (쿠키 유효): 인증 상태 설정
    → 401: 자동 refresh 시도 → 실패 시 LoginPage 표시

[일반 로그인]
  → LoginPage
    → POST /api/auth/login (form-data, credentials: "include")
      → Set-Cookie: access_token, refresh_token (HttpOnly)
      → MainLayout 렌더링

[토큰 갱신] (Access token 만료 시)
  → apiCall() 자동 감지 (401)
    → POST /api/auth/refresh (쿠키에서 refresh_token 자동 추출)
      → Set-Cookie: 갱신된 access_token, refresh_token
      → 원래 요청 재시도

[WebSocket 연결]
  → ws://host/ws/monitoring (쿠키 자동 전송, same-origin)
    → Backend: cookies.get("access_token") 또는 query_params.get("token") 폴백
```

## DB 스키마 (주요 테이블)

```sql
-- 사용자
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    full_name VARCHAR,
    role VARCHAR DEFAULT 'staff',
    is_active BOOLEAN DEFAULT true,
    is_first_user BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 이벤트 로그
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    alert_level VARCHAR NOT NULL,  -- 'warning', 'danger'
    person_id INTEGER,
    duration FLOAT,
    confidence FLOAT,
    fall_type VARCHAR,
    camera_id VARCHAR,
    room_id INTEGER REFERENCES rooms(id),
    is_acknowledged BOOLEAN DEFAULT false,
    ack_by VARCHAR,
    ack_at TIMESTAMP
);

-- 감사 로그 (INSERT-only)
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR NOT NULL,
    actor_id VARCHAR,
    target_id VARCHAR,
    action VARCHAR NOT NULL,
    timestamp TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

-- 안전지대
CREATE TABLE safe_zones (
    id SERIAL PRIMARY KEY,
    camera_id VARCHAR NOT NULL,
    name VARCHAR,
    zone_type VARCHAR NOT NULL,  -- 'safe', 'danger', 'exclusion'
    polygon JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_by VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 공간
CREATE TABLE rooms (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 공간-카메라 매핑
CREATE TABLE room_camera_mappings (
    room_id INTEGER REFERENCES rooms(id),
    camera_id VARCHAR NOT NULL,
    PRIMARY KEY (room_id, camera_id)
);
```

## 성능 벤치마크

| 항목 | 수치 |
|------|------|
| AI 파이프라인 처리 (5인 동시) | P95 = 3.07ms |
| 30 FPS 예산 | 33.3ms |
| 예산 대비 사용 | 9.2% |
| ONNX CPU 추론 속도 | GPU 대비 2.7배 (CPU 환경) |
| V4 낙상 감지 F1 | 94.9 (424개 영상) |
