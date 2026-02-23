# SENTIO 기능 확장 및 보완 계획

> 작성일: 2026-02-02 (최종 업데이트: 2026-02-08)
> 기준: Phase 1-30 완료, 2026년 2월 최신 기술 동향 반영
> **V4 확정**: 확장 벤치마크 최종 (Recall 95.2%, Precision 94.6%, F1 94.9, 424영상)

---

## Phase 16: AIHub ML 학습 완료 (2026-02-02)

AIHub 낙상사고 위험동작 영상 데이터로 GRU 모델 학습을 완료했습니다:

### ML 학습 결과
- **데이터**: AIHub 낙상 영상 2,000건 → MediaPipe 33점 추출 → 20,983 시퀀스
- **균형**: 언더샘플링 9,000 시퀀스 (Fall 4,500 / Normal 4,500)
- **모델**: FallDetectionTransformer (d_model=128, nhead=4, num_layers=2, 286,337 params) — 이후 GRU 모델로 대체됨
- **성능**: Accuracy 88.4%, Precision 0.9341, Recall 0.8315, **F1 0.8798**
- **배포**: `backend/models/fall_classifier.onnx` (1,227 KB) — ONNX 변환 + 검증 완료

### 학습 스크립트
- `scripts/training/extract_landmarks.py`: 영상 → 랜드마크 추출 (30프레임 슬라이딩 윈도우)
- `scripts/training/train_transformer.py`: 모델 학습 + ONNX 변환

---

## 최종 통합 작업 (2026-01-31)

다음 통합 및 버그 수정 작업이 완료되었습니다:

### 보안 강화
- go2rtc 내부 인증 (INTERNAL_STREAM_KEY) 추가
- JWT_SECRET_KEY 고정 기본값 설정 (재시작 시 토큰 무효화 방지)

### 개발 환경 개선
- Vite WebRTC 프록시 추가 (개발 환경에서 go2rtc 스트리밍 지원)

### UI 통합
- SafeZoneEditor 컴포넌트 통합 (CameraView에서 활성화)
- WebRTCPlayer 컴포넌트 통합 (VideoFeed에서 활성화)
- Push 알림 토글 UI 통합 (Settings에서 활성화)
- apiCall 래퍼 통합 (6개 컴포넌트: Login, Register, CameraView, Dashboard, Metrics, Settings)

### 백엔드 개선
- webpush() 비동기 전환 (asyncio.to_thread 사용, 블로킹 방지)
- FHIR 서비스 초기화 및 이벤트 콜백 연결 (event_service.py)

### 인프라 개선
- nginx-ssl.conf.template envsubst 지원 (환경 변수 주입)

### 테스트 확장
- API 통합 테스트 21개 추가 (총 96개)
  - 카메라 관리 테스트
  - Safe Zone CRUD 테스트
  - 통계 API 테스트
  - Push 구독 테스트
  - FHIR 연동 테스트
  - 감사 로그 테스트

---

## 현재 상태 요약

| 항목 | 현황 |
|------|------|
| 낙상 감지 | GRU ONNX 앙상블 (ML 100%) — Binary 분류 (V4 최종: Recall 95.2%, Precision 94.6%, F1 94.9, 424영상) |
| 영상 전송 | MJPEG + WebRTC (go2rtc WHEP) + RTSP |
| 알림 | WebSocket + Web Audio + Web Push (VAPID) + **TTS 음성** (한국어) |
| 배포 | Docker Compose + Nginx + go2rtc + certbot (SSL) |
| PWA | vite-plugin-pwa + Service Worker + 오프라인 배너 |
| DB | SQLite (개발) / PostgreSQL (Docker) |
| 인증 | HttpOnly 쿠키 기반 (Access 8h + Refresh 7d, XSS 방어) |
| 카메라 | USB 웹캠 + RTSP IP 카메라 (go2rtc) |

> **Note**: Phase 9-15 전부 구현 완료되었습니다. 아래 항목들은 모두 "구현 완료" 상태이며, 미구현된 기능은 "남은 향후 과제" 섹션을 참고하세요.

---

## Phase 9: 다중 인원 추적 시스템

> **담당**: python-cv-expert + fall-detection-expert
> **핵심 기술**: YOLO11 Pose + ByteTrack
> **상태**: **구현 완료**

### 9-1. YOLO11 Pose 도입

**배경**: 2025년 발표된 YOLO11 Pose는 YOLOv8 대비 정확도 향상 + 추론 속도 개선. 단일 forward pass에서 다중 인원 감지 + 17개 키포인트 추출 가능. Ultralytics 공식 지원으로 `bytetrack.yaml` 한 줄로 추적 활성화.

**구현 완료 내용**:
- `ultralytics` 패키지 추가 (`pip install ultralytics`)
- `backend/app/services/multi_person_detector.py` 신규 생성
- YOLO11s-pose (Small) 모델 기본 적용 (정확도-속도 균형)
- MediaPipe와 하이브리드 운용:
  - YOLO11: 다중 인원 탐지 + 바운딩박스 + 17 키포인트
  - MediaPipe: ROI 크롭 후 33 키포인트 정밀 분석 (낙상 판정용)

**참고 논문**:
- "A hybrid human fall detection method based on modified YOLOv8s and AlphaPose" (Scientific Reports, 2025)
  - YOLOv8 + AlphaPose 조합으로 소형 객체 탐지 정확도 4.3% 향상
- "Pose-Based Fall Detection System: Efficient Monitoring on Standard CPUs" (arXiv, 2025.03)
  - MediaPipe + 20-frame 버퍼 + 가중 투표 메커니즘으로 오탐 감소

### 9-2. ByteTrack 객체 추적

**배경**: ByteTrack은 높은 신뢰도 탐지뿐 아니라 낮은 신뢰도 탐지까지 활용하여 추적 정확도를 높이는 2단계 연관 전략 사용. Ultralytics 생태계에서 기본 지원.

**구현 완료 내용**:
- `bytetrack.yaml` 설정 파일 생성 (track_high_thresh, track_low_thresh, match_thresh)
- `PersonTracker` 클래스: 프레임 간 person_id 일관성 유지
- 기존 `fall_detector.py`의 per-person 상태 추적과 통합
- person_id 형식: `person_{track_id}` (ByteTrack 부여 ID 활용)

### 9-3. 파이프라인 변경

```
[이전] Camera → MediaPipe (1명) → FallDetector → AlertManager
[현재] Camera → YOLO11 (N명 탐지+추적) → 각 ROI → MediaPipe 33점 → FallDetector(per-person) → AlertManager
```

**구현 완료 파일**:
- `monitoring_orchestrator.py`: 멀티-포즈 루프
- `fall_detector.py`: per-person 구조로 수정 완료
- `alert_manager.py`: 다중 인원 동시 알림 UI 지원
- `connection_manager.py`: person별 알림 브로드캐스트

### 9-4. 프론트엔드 다중 인원 표시

- `VideoFeed.tsx`: 각 인원별 바운딩박스 + 상태 배지 오버레이 구현 완료
- `MetricsCard.tsx`: 인원 수, 개인별 confidence 표시 완료
- `DangerAlertDialog.tsx`: 특정 person_id 지정 acknowledge 완료

---

## Phase 10: 영상 스트리밍 고도화

> **담당**: websocket-expert + python-cv-expert
> **핵심 기술**: WebRTC (go2rtc / MediaMTX)
> **상태**: **구현 완료**

### 10-1. MJPEG → WebRTC 전환

**배경**: MJPEG는 프레임마다 전체 JPEG를 전송하여 대역폭 비효율적. WebRTC는 H.264 코덱으로 압축하여 동일 화질 대비 5-10배 대역폭 절약, 오디오 동시 전송 가능, 지연 250ms 이하.

**2026년 최신 동향**:
- `go2rtc`: RTSP/MJPEG → WebRTC 변환 오픈소스 (GitHub 10K+ stars)
- `MediaMTX`: 경량 RTSP/WebRTC 서버 (FFmpeg + libx264)
- WHIP/WHEP: WebRTC를 HTTP처럼 단순화하는 IETF 표준 (2025년 채택)

**구현 완료 방안 (go2rtc)**:
- `docker-compose.yml`에 go2rtc 컨테이너 추가 완료
- FastAPI가 MJPEG/RTSP 소스를 go2rtc에 등록
- 프론트엔드는 go2rtc의 WebRTC WHEP 엔드포인트로 직접 연결
- 기존 MJPEG 폴백 유지 (구형 브라우저 호환)
- `WebRTCPlayer.tsx` 컴포넌트 구현 완료

### 10-2. RTSP IP 카메라 지원

- `camera_service.py` 확장: RTSP URL 입력 지원 구현 완료
- `config.py`: `CAMERA_SOURCE` 설정 추가 완료
- go2rtc가 RTSP → WebRTC 변환 자동 처리
- 다중 카메라 관리: cameras DB 테이블 활용

### 10-3. 낙상 순간 스냅샷/클립 저장

- 낙상 감지 시 해당 프레임 JPEG 저장 (`static/snapshots/`) 구현 완료
- 선택적: 전후 5초 MP4 클립 저장 (FFmpeg)
- Event 모델의 `snapshot_path` 필드 활용
- 프론트엔드 이벤트 상세에서 스냅샷 표시

---

## Phase 11: 알림 시스템 고도화 + PWA

> **담당**: notification-expert + react-web-expert
> **핵심 기술**: FCM + PWA + Service Worker
> **상태**: **구임 완료** (PWA + Web Push), SMS 미구현

### 11-1. PWA 변환 (vite-plugin-pwa) - **구현 완료**

- `vite-plugin-pwa` 기반 Service Worker 등록 완료
- 정적 자산 프리캐싱 (앱 셸 캐싱) 완료
- `sw-custom.ts` 커스텀 Service Worker (Push 이벤트 핸들링) 완료
- `OfflineBanner.tsx` 오프라인 상태 인디케이터 완료
- 홈 화면 설치 가능 완료

### 11-2. Web Push 알림 (VAPID) - **구현 완료**

- Backend: `push_service.py` (VAPID 키 기반 싱글톤 서비스) 완료
- Backend: `push.py` 라우트 (GET /api/push/vapid-key, POST /api/push/subscribe, POST /api/push/unsubscribe) 완료
- Backend: `push_subscription.py` 모델 (endpoint, keys, user_id, is_active, datetime fix) 완료
- Frontend: `usePushNotifications.ts` 훅 (권한 요청 → 구독 등록) 완료
- Service Worker가 백그라운드 Push 수신 및 시스템 알림 표시 완료

### 11-3. SMS 백업 알림 - **미구현 (향후)**

- Twilio API 연동 (`twilio` Python SDK)
- danger 상태 30초 미확인 시 SMS 에스컬레이션
- 야간 시간대 자동 SMS (설정 가능)
- 수신자 관리 UI (관리자 설정)

### 11-4. 에스컬레이션 정책 - **부분 구현**

```
[0초]  danger 감지 → WebSocket + 대시보드 알림 + 알림음 + Web Push (구현 완료)
[30초] 미확인 → SMS 발송 (담당 간호사) (미구현)
[60초] 미확인 → SMS 발송 (수간호사/관리자) (미구현)
```

---

## Phase 12: 배포 인프라 (Docker + PostgreSQL)

> **담당**: Bash (DevOps) + db-expert
> **핵심 기술**: Docker Compose + Nginx + PostgreSQL + go2rtc + certbot
> **상태**: **구현 완료**

### 12-1. Docker Compose 구성 - **구현 완료**

**현재 구성** (`docker-compose.yml`, `docker-compose.ssl.yml`, `nginx/nginx.conf`, Backend/Frontend Dockerfile):
```yaml
services:
  db:           # PostgreSQL 16 (health check, pgdata 볼륨)
  backend:      # FastAPI + Gunicorn (depends_on: db)
  frontend:     # React 빌드 → 정적 파일 (frontend_dist 볼륨)
  nginx:        # 리버스 프록시 (port 80/443, gzip, WebSocket upgrade)
  go2rtc:       # WebRTC 스트리밍 (WHEP 지원)
```

**프로덕션 배포 표준 (구현 완료)**:
- Gunicorn + Uvicorn workers (CPU 코어 수 = 워커 수) 완료
- `--proxy-headers` 플래그 (Nginx 뒤에서 실행) 완료
- `--preload` 옵션 (copy-on-write 메모리 최적화) 완료
- `max_requests` + `max_requests_jitter` (메모리 누수 방지) 완료
- Health check 구성 완료

### 12-2. PostgreSQL 마이그레이션 - **구현 완료**

- `DATABASE_URL` 변경: `postgresql+asyncpg://...` 완료
- Connection pooling 설정 (asyncpg) 완료
- **Alembic 마이그레이션 도구 도입** - **구현 완료** (Phase 17)
- **기존 SQLite 데이터 마이그레이션 스크립트** - **구현 완료** (Phase 17)

### 12-3. Nginx 리버스 프록시 - **구현 완료**

```nginx
server {
    listen 443 ssl;

    # React SPA 정적 파일
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # FastAPI API
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # WebRTC (go2rtc)
    location /webrtc/ {
        proxy_pass http://go2rtc:8554;
    }
}
```

### 12-4. HTTPS/TLS - **구현 완료**

- Let's Encrypt 인증서 자동 갱신 (certbot) 완료
- Nginx SSL 설정 (TLS 1.2+) 완료 (`nginx-ssl.conf`)
- HSTS 헤더 활성화 완료
- `docker-compose.ssl.yml` 추가 구성 완료

---

## Phase 13: 보안 및 컴플라이언스 강화

> **담당**: security-auditor + hipaa-expert
> **핵심**: 의료 데이터 보호, 감사 추적
> **상태**: **구현 완료**

### 13-1. 감사 로깅 (Audit Trail) - **구현 완료**

- `audit_log.py` 모델: user_id, action, resource, timestamp, ip_address 완료
- `audit_service.py`: 모든 인증/데이터 접근 이벤트 로깅 완료
- `audit_logs` 테이블: INSERT only, DELETE/UPDATE 불가 정책 완료
- 90일 보존 정책 완료

### 13-2. Refresh Token 체계 - **구현 완료**

- Access Token: 8시간 (현재 설정)
- Refresh Token: 7일 (HttpOnly 쿠키 저장) 완료
- Token rotation: Refresh 사용 시 새 쌍 발급 완료
- `/api/auth/refresh` 엔드포인트 구현 완료
- **토큰 저장 방식**: HttpOnly 쿠키 (XSS 방어, Phase 17에서 전환)
- **검증 방식**: JWT decode (쿠키에서 자동 추출)

### 13-3. 개인정보 보호 강화 - **부분 구현**

- 얼굴 모자이크 자동 처리 (MediaPipe Face Detection) - 향후
- 스냅샷 저장 시 얼굴 블러 후 저장 - 향후
- 이벤트 데이터 자동 삭제 정책 (90일) 완료
- **GDPR/개인정보보호법 동의 UI** - **미구현 (향후)**

### 13-4. API 보안 강화 - **부분 구현**

- **레이트 리밋**: 로그인 엔드포인트만 구현 (IP별 5회/60초, in-memory)
- **전체 API Redis 기반 레이트 리밋** - **미구현 (향후)**
- CORS 허용 메서드/헤더 제한 완료
- Content Security Policy (CSP) 헤더 완료
- SQL Injection 방어 검증 (SQLAlchemy ORM 사용으로 기본 방어) 완료

---

## Phase 14: AI 고도화

> **담당**: fall-detection-expert + python-cv-expert
> **핵심 기술**: ONNX + Safe-Zone 관리
> **상태**: **구현 완료**

### 14-1. GRU 기반 낙상 판별 + ONNX 앙상블 - **구현 완료 + ML 학습 완료**

**2025년 최신 연구**:
- "Next-generation fall detection: harnessing human pose estimation and transformer technology" (PMC, 2025)
  - Transformer 입력: 포즈 시퀀스 → 시간적 패턴 학습
  - 정확도 98%, F1 90.91%, 민감도 95.24%
- "Multistage fall detection via 3D pose sequences and TCN" (Scientific Reports, 2025)
  - 2D → 3D 포즈 재구성 + Temporal Conv Network
  - NTU RGB+D 벤치마크 99.87% 정확도

**구현 완료 내용**:
- `fall_classifier.py` (ONNX Runtime): GRU 모델 추론
- 20-30 프레임 시퀀스 입력 → 낙상 확률 출력 완료
- ML 100% (최적 가중치) 가중 평균 완료
- `ensemble_scoring()` 함수 구현 완료

**ML 학습 완료 (Phase 16, 2026-02-02)**:
- AIHub 낙상 영상 2,000건 → 20,983 시퀀스 추출 → 9,000 균형 데이터
- FallDetectionTransformer → GRU 모델로 대체됨: d_model=128, nhead=4, num_layers=2, 286,337 params
- **최종 성능 (V4 확장 벤치마크 424개 영상)**: Recall 95.2%, Precision 94.6%, F1 94.9
- ONNX 모델 배포: `backend/models/fall_classifier.onnx` (1,227 KB)

### 14-2. 합성 데이터 기반 학습 - **향후**

- GenAI 활용 낙상 시나리오 영상 생성 (노인 낙상 데이터 부족 문제 해결)
- 데이터 증강: 조명 변화, 시점 변화, 체형 변화
- 공개 데이터셋 활용: Le2i, NTU RGB+D, MPFDD

### 14-3. Safe-Zone 관리 - **UI + CRUD 완료, 감지 연동 미완료**

- 프론트엔드: Canvas로 영역 드래그 설정 (`SafeZoneEditor.tsx`) 완료
- zone 데이터 DB 저장 (`safe_zones` 테이블) 완료
- Safe-Zone CRUD API (`safe_zones.py` 라우트) 완료
- **[미연결]** 감지 파이프라인에서 zone 데이터 미사용 — `fall_detector.py`, `monitoring_orchestrator.py`에서 zone 참조 0건
- **[미구현]** Point-in-polygon 알고리즘, zone-aware 임계값 분기
- **[향후]** 위험구역 진입 시 즉시 "주의" 알림 → 낙상 위험 조기 발견 기능

### 14-4. 행동 패턴 분석 - **미구현 (향후)**

- 장시간 미움직임 감지 (의식 없음 가능성)
- 비정상적 보행 패턴 감지 (낙상 전조)
- 일일 활동량 통계 (보행 거리, 자세 변화 횟수)

---

## Phase 15: 통계 및 리포팅

> **담당**: chart-expert + react-web-expert
> **핵심 기술**: Recharts + PDF 리포트 + FHIR
> **상태**: **부분 구현**

### 15-1. 통계 대시보드 - **구현 완료**

- `stats.py` API: 일별/주별/월별 낙상 발생 빈도 완료
- 시간대별 위험 패턴 히트맵 완료
- 인원별 낙상 위험도 트렌드 완료
- 카메라별 감지 통계 완료
- `StatsView.tsx` (Recharts 기반) UI 완료

### 15-2. 리포트 생성 - **구현 완료** (Phase 19)

- `report_service.py`: PDF 리포트 자동 생성 - **구현 완료**
- `report_scheduler.py`: 일간/주간 자동 리포트 스케줄러 - **구현 완료**
- `ReportView.tsx`: 리포트 목록/생성/다운로드 UI - **구현 완료**
- CSV/Excel 데이터 내보내기 (`/api/events/export`) - **구현 완료**
- **이메일 발송 (관리자)** - **미구현 (향후)**

### 15-3. EMR/HIS 연동 - **부분 구현**

- `fhir_service.py`: HL7 FHIR API 연동 (FHIR R4 표준) 완료
- **HL7 FHIR R4 Observation 리소스 변환 완료**
- **FHIR 서버 전송 기능 완료** (FHIR_BASE_URL 설정 시 활성화)
- **환자 ID 매핑 (person_id → 환자 번호)** - **향후**
- **FHIR Bundle 형식 지원** - **향후**
- **FHIR Patient 리소스 매핑** - **향후**

---

## 구현 우선순위 및 로드맵

### 완료된 항목 (Phase 9-15)

| 순위 | Phase | 핵심 기능 | 상태 |
|------|-------|-----------|------|
| ~~1~~ | ~~**9**~~ | ~~YOLO11 다중 인원 추적 + ByteTrack + hybrid pipeline + MediaPipe ROI~~ | **완료** |
| ~~2~~ | ~~**10**~~ | ~~go2rtc WebRTC WHEP + RTSP + WebRTCPlayer.tsx~~ | **완료** |
| ~~3~~ | ~~**11**~~ | ~~PWA + Web Push + Service Worker + 오프라인 배너~~ | **완료** |
| ~~4~~ | ~~**12**~~ | ~~Docker Compose + Nginx + Gunicorn + PostgreSQL + go2rtc + certbot (HTTPS)~~ | **완료** |
| ~~5~~ | ~~**13**~~ | ~~감사 로깅 + Refresh Token + API 보안~~ | **완료** |
| ~~6~~ | ~~**14**~~ | ~~ONNX fall_classifier + 앙상블 + Safe-Zone CRUD~~ | **완료** |
| ~~7~~ | ~~**15**~~ | ~~통계 API + StatsView.tsx + PDF 리포트 + FHIR 연동~~ | **완료** |

---

## 남은 향후 과제

아래 항목들은 Phase 16 이후에 구현 예정입니다:

| 순위 | 기능 | 설명 | 영향도 |
|------|------|------|--------|
| ~~0~~ | ~~AIHub 낙상 데이터셋 딥러닝~~ | ~~22,672클립 실제 낙상 데이터로 Transformer 재학습~~ | **완료** (Phase 16, F1=0.8798) |
| **1** | **Safe-Zone 감지 연동** | **zone 데이터를 낙상 감지 파이프라인에 연결 → 위험구역 진입 시 즉시 경고 (예방적 기능)** | **핵심** |
| 2 | SMS 에스컬레이션 | Twilio API 기반 30초/60초 SMS 알림 | 중요 (추후 확장) |
| 3 | **IoT 스마트 경광등** | **REST/MQTT Webhook으로 병실 경광등 자동 점등** | **중요 (추후 확장)** |
| 4 | Redis 메시지 버퍼 | 수평 확장을 위한 메시지 브로커 | 확장성 |
| ~~5~~ | ~~E2E 테스트 (Playwright)~~ | ~~자동화된 브라우저 테스트~~ | **완료** (Phase 19) |
| ~~6~~ | ~~얼굴 블러~~ | ~~스냅샷 저장 시 개인정보 보호~~ | **완료** (Phase 19) |
| ~~7~~ | ~~GDPR 동의 UI~~ | ~~개인정보보호법 준수 UI~~ | **완료** (Phase 19) |
| 8 | Redis 기반 전역 레이트 리밋 | 전체 API 엔드포인트 보호 | 보안 |
| ~~9~~ | ~~ReportView 프론트엔드~~ | ~~PDF 리포트 UI~~ | **완료** (Phase 19) |
| 10 | 이메일 알림 발송 | 관리자 이메일 리포트 | 리포팅 |
| 11 | FHIR Bundle/Patient 매핑 | 완전한 FHIR 지원 | EMR 연동 |
| 12 | Telegram Bot | 선택적 모니터링 채널 | 부가 |
| 13 | 행동 패턴 분석 | 장시간 미움직임, 비정상 보행 | 예방 |

---

## 기술 스택 변경 요약

| 영역 | 현재 | 목표 (완료됨) |
|------|------|------|
| AI 감지 | YOLO11 Pose + ByteTrack + MediaPipe ROI | (완료) |
| 영상 | MJPEG + WebRTC (go2rtc WHEP) + RTSP | (완료) |
| 알림 | WebSocket + Web Audio + Web Push | SMS 추가 예정 |
| DB | SQLite (개발) / PostgreSQL (Docker) | (완료) |
| 배포 | Docker Compose + Nginx + go2rtc + certbot (SSL) | (완료) |
| 프론트엔드 | PWA (오프라인 + 홈화면 설치) | (완료) |
| 인증 | HttpOnly 쿠키 + JWT (Access 8h + Refresh 7d) | (완료) |
| 확장 | 단일 인스턴스 | Redis Pub/Sub 추가 예정 |

---

## 참고 자료

### 낙상 감지 AI
- [Hybrid YOLOv8 + MediaPipe Fall Detection (ScienceDirect, 2025)](https://www.sciencedirect.com/science/article/pii/S2215016125004674)
- [Modified YOLOv8s + AlphaPose (Scientific Reports, 2025)](https://www.nature.com/articles/s41598-025-86429-6)
- [Pose-Based Fall Detection on Standard CPUs (arXiv, 2025.03)](https://arxiv.org/abs/2503.19501)
- [Next-gen Fall Detection with Transformers (PMC, 2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC12107650/)
- [3D Pose + TCN Fall Detection 99.87% (Scientific Reports, 2025)](https://www.nature.com/articles/s41598-025-11325-y)
- [Best Pose Estimation Models (Roboflow, 2025)](https://blog.roboflow.com/best-pose-estimation-models/)

### YOLO11 + ByteTrack
- [Ultralytics YOLO Tracking Docs](https://docs.ultralytics.com/modes/track/)
- [YOLO11 Object Tracking Guide (Ultralytics)](https://www.ultralytics.com/blog/how-to-use-ultralytics-yolo11-for-object-tracking)
- [YOLO11 + ByteTrack (Medium, 2025)](https://medium.com/rectlabs/the-perfect-duo-learning-real-time-object-tracking-with-yolov11-and-bytetrack-1aa5532ca8f7)

### WebRTC / 영상 스트리밍
- [WebRTC Latency Comparison (nanocosmos)](https://www.nanocosmos.net/blog/webrtc-latency/)
- [go2rtc - Universal Camera Streaming (GitHub)](https://github.com/AlexxIT/go2rtc)
- [MOQ vs WebRTC 2026 (Red5)](https://www.red5.net/blog/moq-vs-webrtc/)
- [HLS vs MJPEG Comparison (VideoSDK)](https://www.videosdk.live/developer-hub/hls/hls-vs-mjpeg)
- [RTSP → WebRTC Pipeline (kaanlabs)](https://kaanlabs.com/low-latency-webcam-to-browser-streaming-with-rtsp-webrtc/)

### 의료 모니터링 시스템
- [AI-Powered Surveillance in Healthcare (Wowza, 2026)](https://www.wowza.com/blog/the-future-of-connected-care-surveillance-and-real-time-monitoring-in-remote-healthcare)
- [Real-Time Alerts in Patient Care (PubNub, 2025)](https://www.pubnub.com/blog/how-real-time-alerts-improve-patient-engagement-and-treatment-adherence/)
- [Nurse Call + Mobile Alerts (Critical Alert)](https://www.specialcaresys.com/hospitals-clinics/wired-nurse-call/)

### FastAPI 프로덕션 배포
- [FastAPI Production Best Practices (Render, 2025)](https://render.com/articles/fastapi-production-deployment-best-practices)
- [WebSockets at Scale with FastAPI (Medium, 2025)](https://medium.com/@bhagyarana80/websockets-at-scale-with-fastapi-and-uvicorn-workers-building-real-time-systems-that-dont-break-ac2dada6cae9)
- [Scale FastAPI WebSocket Servers (Medium, 2025)](https://hexshift.medium.com/how-to-scale-fastapi-websocket-servers-without-losing-state-6462b43c638c)
- [FastAPI Production Patterns (orchestrator.dev, 2025)](https://orchestrator.dev/blog/2025-1-30-fastapi-production-patterns/)

### PWA + 푸시 알림
- [FCM Push Notifications in PWA (Coffee Byte, 2026.01)](https://blog.coffeeinc.in/complete-guide-push-notifications-in-pwa-with-firebase-cloud-messaging-a515965372f7)
- [vite-plugin-pwa (GitHub)](https://github.com/vite-pwa/vite-plugin-pwa)
- [PWA Push Notifications Guide (Pretius, 2025)](https://pretius.com/blog/pwa-push-notifications)
- [Firebase Web Push Docs (2026.01)](https://firebase.google.com/docs/cloud-messaging/web/get-started)

### Docker 배포
- [FastAPI Docker Official Docs](https://fastapi.tiangolo.com/deployment/docker/)
- [React Vite + Docker + Nginx (2025)](https://www.buildwithmatija.com/blog/production-react-vite-docker-deployment)
- [Full-Stack FastAPI + React + Nginx (Medium, 2025)](https://vardhmanandroid2015.medium.com/beginners-guide-for-containerizing-application-deploying-a-full-stack-fastapi-and-react-app-001f2cac08a8)

---

*이 문서는 2026년 2월 기준 최신 기술 동향을 반영하여 작성되었습니다. (Phase 21 발표 시연 품질 개선 완료: 2026-02-04, V4 벤치마크 확정: 2026-02-08)*
