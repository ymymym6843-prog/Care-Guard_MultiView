# SENTIO WAITING AI 개발 로드맵

> 최종 업데이트: 2026-02-08

---

## 구현 현황

| 단계 | 내용 | 상태 |
|------|------|------|
| Phase 1 | Backend 인프라 (FastAPI, DB, Auth, Camera, Pose, Fall Detection, Alert) | **완료** |
| Phase 2 | REST API + WebSocket (이벤트, 카메라, 설정, 모니터링 WS) | **완료** |
| Phase 3 | Frontend 통합 (React, Zustand, 대시보드, 알림, 이벤트 로그) | **완료** |
| Phase 4 | UI/UX 보완 (Pretendard 폰트, 접근성, Vibration API, 긴급 알림 확대) | **완료** |
| Phase 5 | Backend 모듈화 (로깅, 예외 체계, 설정 중앙화, 오케스트레이터 분리) | **완료** |
| Phase 6 | 문서화 (README, ARCHITECTURE, API 문서) | **완료** |
| Phase 7 | 보안 강화 + 로그인 UI (JWT 기본값 수정, 전 엔드포인트 인증, 로그인 페이지) | **완료** |
| Phase 8 | 단위 테스트 + 카메라 API 인증 + 코드 리뷰 + 보안 수정 | **완료** |
| Phase 9 | Docker 배포 + PWA + 푸시 알림 (docker-compose, Service Worker, VAPID Push) | **완료** |
| Phase 10 | 다중 인원 추적 (YOLO11s-pose + ByteTrack) | **완료** |
| Phase 11 | 영상 스트리밍 고도화 (WebRTC + RTSP 카메라) | **완료** |
| Phase 12 | 보안 컴플라이언스 (감사 로깅, Refresh Token, HTTPS) | **완료** |
| Phase 13 | AI 고도화 (GRU 분류기, Safe-Zone 관리) | **완료** |
| Phase 14 | 통계 및 EMR 연동 (대시보드, PDF 리포트, HL7 FHIR) | **완료** |
| Phase 15 | 최종 통합 + 테스트 + 문서 업데이트 | **완료** |
| Phase 16 | AIHub 낙상 데이터셋 ML 학습 + ONNX 배포 | **완료** |
| Phase 17 | 인프라 안정화 + 보안 (HttpOnly 쿠키, Alembic, CI/CD) | **완료** |
| Phase 18 | ML 모델 고도화 + 코드리뷰 (4클래스 분류, 데이터 증강, K-Fold CV) | **완료** |
| Phase 19 | 리포팅 + 개인정보 + i18n + E2E (CSV/Excel, 얼굴 블러, 다국어) | **완료** |
| Phase 20 | 5클래스 ML + Pre-impact 전조 감지 (Pre-VFall 데이터셋) | **완료** |
| Phase 21 | 발표 시연 품질 개선 (3단계 차등 알림, TTS 한국어 음성) | **완료** |
| Phase 22 | 보행도구 인식 + 착석 오탐 제거 (YOLO + MediaPipe 하이브리드) | **완료** |
| Phase 23 | Privacy-First + Skeleton Blackbox (Non-Storage, 원본 비저장) | **완료** |
| Phase 24 | 다중인원 대시보드 + 파이프라인 시각화 (인물별 상태 모니터링) | **완료** |
| Phase 25 | 전조 감지 조기 경고 + 카메라 상태 동기화 + 보행도구 정확도 개선 | **완료** |
| Phase 26 | 앙상블 가중치 최적화 + 규칙확장 13조건 (C1-C7 + N1-N6) | **완료** |
| Phase 27 | COCO 17점 키포인트 지원 + 낙상 감지 정확도 개선 (Quick Recovery, Multi-frame Accum, Controlled Movement) | **완료** |
| Phase 28 | 파이프라인 제어 + 이벤트 DB 기록 | **완료** |
| Phase 29 | 알림 자동복구 + 다국어 UI 완성 | **완료** |
| Phase 30 | AI 모델 관리 시스템 | **완료** |
| V4 확정 | V4 확장 벤치마크 확정 (Recall 95.2%, Precision 94.6%, F1 94.9, 424영상) | **완료** |
| Phase 31 | UI/UX 전체 폴리싱 + i18n 완성 (276개 키, 20+ 컴포넌트) | **완료** |

---

## 프로젝트 개요

### 프로젝트명
**SENTIO WAITING AI** - 요양병원 대기실 낙상/이상움직임 감지 웹 애플리케이션

### 핵심 목표
- 카메라 영상을 실시간으로 분석하여 낙상 및 이상 움직임 감지
- 3단계 알림 시스템 (전조 주의 → 낙상 경고 → 실제 낙상 즉시 위험)
- 웹 기반 대시보드로 실시간 모니터링
- HttpOnly 쿠키 인증 기반 보안 접근 제어 (Access 8h + Refresh 7d)
- PWA 기반 모바일 접근 + 푸시 알림
- 다중 인원 동시 추적 (YOLO11 + ByteTrack)
- WebRTC 저지연 스트리밍

### 기술 스택 (현재 구현)

| 영역 | 기술 | 버전 | 용도 |
|------|------|------|------|
| Backend | FastAPI + Uvicorn | 0.104+ | REST API, WebSocket 서버 |
| AI/CV (감지) | YOLO11s-pose + ByteTrack | ultralytics 8.3+ | 다중 인원 포즈 추정 + 추적 (COCO 17점) |
| AI/CV (정밀) | MediaPipe Tasks API | 0.10.30+ | PoseLandmarker 33개 관절점 (폴백) |
| 키포인트 어댑터 | keypoint_adapter.py | 자체 구현 | COCO 17점 ↔ MediaPipe 33점 변환 |
| AI/ML | ONNX Runtime | - | GRU 분류기 (Binary, ML 100%) |
| 영상 처리 | OpenCV (headless) | 4.8+ | 카메라 연결, 프레임 처리 |
| 스트리밍 | MJPEG + WebRTC | go2rtc WHEP | 저지연 영상 스트리밍 |
| Frontend | React + TypeScript + Vite | 18 / 6 | 대시보드 UI |
| 실시간 통신 | WebSocket | FastAPI 내장 | 양방향 데이터 스트리밍 |
| 상태 관리 | Zustand | 5+ | 클라이언트 상태 |
| UI 컴포넌트 | Radix UI + Shadcn/ui + Lucide | - | 접근성 내장 컴포넌트 |
| 차트 | Recharts | 2.15+ | 통계 시각화 |
| CSS | Tailwind CSS v4 | 4.0 | 유틸리티 CSS + oklch 색상 |
| Database | SQLite (async) / PostgreSQL | aiosqlite / asyncpg | 이벤트 로그 저장 |
| 인증 | HttpOnly 쿠키 + JWT + bcrypt | python-jose | 사용자 인증/권한 (Access 8h + Refresh 7d, XSS 방어) |
| DB 마이그레이션 | Alembic | 1.13+ | 점진적 DB 스키마 버전 관리 (async, SQLite batch) |
| CI/CD | GitHub Actions | - | 자동 테스트 (pytest + tsc + vite build) |
| 감사 | INSERT-only audit trail | - | 보안 감사 로깅 |
| 폰트 | Pretendard + Noto Sans KR | Variable | 한국어 최적화 |
| PWA | vite-plugin-pwa | - | Service Worker, 오프라인 지원 |
| 푸시 알림 | Web Push (VAPID) | pywebpush | 백그라운드 푸시 알림 |
| 인물 추적 | YOLO11 + ByteTrack / IoU PersonTracker (폴백) | ultralytics / 자체 구현 | 프레임 간 인물 ID 유지 |
| EMR | HL7 FHIR R4 | httpx | EMR/HIS 연동 (선택적) |
| PDF | reportlab | - | PDF 리포트 생성 (선택적) |
| 컨테이너 | Docker Compose + Nginx + go2rtc + certbot | - | 프로덕션 배포 + HTTPS |

#### YOLO11 선택 근거

##### 성능 비교 (YOLOv8 vs YOLO11)

| 지표 | YOLOv8 | YOLO11 | 차이 | 의미 |
|------|--------|--------|------|------|
| mAP (COCO) | 기준선 | +1~2% | 정확도 향상 | 겹치는 환자, 낙상 감지 개선 |
| **CPU 추론 속도** | 기준선 | **~30% 빠름** | **중요** | **저사양 PC 실시간 처리 가능** |
| **파라미터 수** | 100% | **78%** | **22% 감소** | **메모리 절약 + MediaPipe 동시 실행** |
| GPU 지연 | 기준선 | 더 낮음 | 소폭 개선 | 고사양 환경 추가 최적화 |
| C2PSA 모듈 | 없음 | **추가** | 신규 | 중첩 객체 감지 향상 |
| C3k2 블록 | 없음 | **추가** | 신규 | 효율적 특징 추출 |

##### YOLO11 채택 이유 (6가지)

1. **CPU 30% 속도 향상**
   - GPU 없는 요양병원 일반 PC에서 실시간 처리 가능 (필수 요구사항)
   - 대부분 요양병원은 고사양 서버 구축 불가능
   - 기존 CCTV 인프라 활용 가능

2. **22% 파라미터 감소**
   - YOLO11s-pose 모델 (~19MB)
   - MediaPipe 33점 분석과 동시 실행 시 메모리 여유 확보
   - 제한적 리소스 환경에서 안정성 향상

3. **C2PSA 공간 주의 모듈**
   - 겹치는 환자/작은 객체(바닥에 넘어진 환자) 감지 향상
   - 병실에서 보호자와 환자가 겹칠 때 정확한 감지
   - 좁은 공간에서의 낙상 감지율 35% 향상

4. **C3k2 효율적 블록**
   - 특징 추출 효율화로 정확도+속도 동시 개선
   - 모션 보상 강화로 추적 안정성 향상

5. **API 호환성 (100%)**
   - ultralytics 라이브러리 동일
   - YOLOv8 코드와 100% 호환
   - 기존 구현 코드 변경 최소화

6. **small 변형(yolo11s-pose) 최적화**
   - CPU 전용 실시간 처리에 최적화된 경량 모델
   - 엣지 디바이스(Jetson Nano, Raspberry Pi) 확장 가능

##### 참고

2026년 1월 YOLO26도 출시되었으나, YOLO11은 다음과 같은 장점이 있습니다:
- 충분한 검증과 안정성 확보 (프로덕션 레디)
- 다양한 실증 데이터 축적
- 커뮤니티 지원 및 문서화 완성도
- 성숙한 에코시스템 (ONNX 변환, 최적화 도구 등)

---

## 프로젝트 구조 (실제)

```
sentio/
├── .github/
│   └── workflows/
│       └── ci.yml                    # GitHub Actions CI/CD
├── backend/
│   ├── alembic.ini                    # Alembic DB 마이그레이션 설정
│   ├── migrations/                    # Alembic 마이그레이션
│   │   ├── env.py                     # async 엔진, SQLite batch mode
│   │   ├── script.py.mako             # 마이그레이션 템플릿
│   │   └── versions/                  # 버전별 마이그레이션 파일
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 앱 + lifespan 관리
│   │   ├── config.py                  # Pydantic Settings (환경변수)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py            # 로그인(쿠키)/회원가입/로그아웃/토큰갱신
│   │   │       ├── cameras.py         # 카메라 목록/시작/중지
│   │   │       ├── events.py          # 이벤트 CRUD + 페이지네이션
│   │   │       ├── push.py            # 푸시 알림 구독 관리 (VAPID)
│   │   │       ├── settings_route.py  # 런타임 설정 (인증 필수)
│   │   │       ├── stats.py           # 통계 조회 (시간대별, 트렌드)
│   │   │       ├── stream.py          # MJPEG 비디오 스트림 (쿠키/토큰)
│   │   │       ├── ws.py              # WebSocket 모니터링 (쿠키/토큰)
│   │   │       └── zones.py           # Safe-Zone 관리 (CRUD)
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                # JWT 토큰 + HttpOnly 쿠키 + bcrypt
│   │   │   ├── connection_manager.py  # WebSocket 연결 풀 + 브로드캐스트
│   │   │   ├── database.py            # SQLAlchemy async 엔진
│   │   │   ├── exceptions.py          # 커스텀 예외 계층
│   │   │   └── logging_config.py      # 서비스별 named logger
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py                # 사용자 모델
│   │   │   ├── event.py               # 이벤트 로그 모델
│   │   │   ├── camera.py              # 카메라 설정 모델
│   │   │   ├── push_subscription.py   # 푸시 구독 모델 (endpoint, keys)
│   │   │   ├── audit_log.py           # 감사 로그 모델 (INSERT-only)
│   │   │   └── safe_zone.py           # Safe-Zone 모델
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── camera_service.py      # OpenCV 웹캠 (전용 스레드)
│   │   │   ├── pose_service.py        # MediaPipe PoseLandmarker Tasks API
│   │   │   ├── fall_detector.py       # 4조건 낙상 감지 + 쿨다운
│   │   │   ├── alert_manager.py       # 상태 머신 (5단계)
│   │   │   ├── monitoring_orchestrator.py  # 파이프라인 오케스트레이터
│   │   │   ├── person_tracker.py      # IoU 기반 프레임 간 인물 추적 (폴백)
│   │   │   ├── multi_person_detector.py # YOLO11s-pose + ByteTrack 다중 인원
│   │   │   ├── fall_classifier.py     # GRU 기반 시계열 분류기 (선택적)
│   │   │   ├── push_service.py        # Web Push 알림 (VAPID)
│   │   │   ├── audit_service.py       # 감사 로깅 서비스
│   │   │   ├── report_service.py      # PDF 리포트 생성 (선택적)
│   │   │   ├── fhir_service.py        # HL7 FHIR 연동 (선택적)
│   │   │   └── iot_service.py         # IoT Webhook 디바이스 알림 (선택적)
│   │   └── utils/
│   │       └── __init__.py
│   ├── tests/
│   │   ├── test_fall_detector.py      # 16개 테스트
│   │   ├── test_alert_manager.py      # 24개 테스트
│   │   ├── test_auth.py               # 23개 테스트
│   │   ├── test_api_auth.py           # 10개 API 통합 테스트 (쿠키 기반)
│   │   ├── test_api_events.py         # 8개 API 통합 테스트
│   │   ├── test_api_stats.py          # 6개 API 통합 테스트
│   │   └── test_person_tracker.py     # 12개 테스트
│   ├── models/                        # AI 모델 파일
│   │   └── fall_classifier.onnx      # GRU 낙상 분류기 (1,227KB, 학습 완료)
│   ├── Dockerfile                     # Backend Docker 이미지
│   ├── requirements.txt               # Python 의존성
│   └── pytest.ini                     # 테스트 설정
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # 루트 (인증 래퍼)
│   │   ├── main.tsx                   # React 진입점
│   │   ├── sw-custom.ts               # 커스텀 Service Worker (Push 핸들링)
│   │   ├── vite-env.d.ts              # Vite 타입 선언
│   │   ├── components/
│   │   │   ├── LoginPage.tsx          # 로그인 페이지
│   │   │   ├── RegisterPage.tsx       # 회원가입 페이지
│   │   │   ├── UserManagement.tsx     # 사용자 관리 (관리자 전용)
│   │   │   ├── OfflineBanner.tsx      # 오프라인 상태 인디케이터
│   │   │   ├── Alerts/
│   │   │   │   └── DangerAlertDialog.tsx  # 긴급 알림 모달
│   │   │   ├── Dashboard/
│   │   │   │   ├── DashboardView.tsx  # 메인 대시보드
│   │   │   │   ├── VideoFeed.tsx      # MJPEG + 프라이버시 모드
│   │   │   │   ├── WebRTCPlayer.tsx   # WebRTC WHEP 플레이어
│   │   │   │   ├── StatusCard.tsx     # 알림 상태 카드
│   │   │   │   ├── MetricsCard.tsx    # 실시간 수치
│   │   │   │   ├── EventLog.tsx       # 이벤트 이력 (ARIA live)
│   │   │   │   ├── SettingsCard.tsx   # 감지 설정
│   │   │   │   ├── SafeZoneEditor.tsx # Safe-Zone 편집기
│   │   │   │   ├── AlertSoundControl.tsx  # 알림음 제어
│   │   │   │   └── ConnectionStatus.tsx   # 연결 상태 배지
│   │   │   ├── Stats/
│   │   │   │   └── StatsView.tsx      # 통계 대시보드 (Recharts)
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx         # 헤더 + 로그아웃
│   │   │   │   ├── MainLayout.tsx     # 앱 셸
│   │   │   │   └── Sidebar.tsx        # 접이식 사이드바
│   │   │   └── ui/                    # Radix UI 기반 컴포넌트 (14개)
│   │   ├── hooks/
│   │   │   ├── useWebSocket.ts        # WS 연결 + 지수 백오프 재연결
│   │   │   ├── useAlertSound.ts       # Web Audio + Vibration API
│   │   │   ├── useSkeletonRenderer.ts # Canvas 2D 스켈레톤
│   │   │   ├── useEventLog.ts         # 이벤트 로그 관리
│   │   │   ├── useAcknowledge.ts      # 알림 확인
│   │   │   └── usePushNotifications.ts # Push 구독 (VAPID)
│   │   ├── lib/
│   │   │   ├── auth.ts                # HttpOnly 쿠키 인증 (apiCall, checkAuth, logout)
│   │   │   └── utils.ts               # Tailwind merge
│   │   ├── store/
│   │   │   └── monitoring.ts          # Zustand 단일 스토어
│   │   └── styles/
│   │       └── globals.css            # Tailwind v4 + CSS 변수 + oklch
│   ├── Dockerfile                     # Frontend Docker 이미지
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts                 # Vite + 프록시 + PWA 설정
│
├── nginx/
│   ├── nginx.conf                     # Nginx 리버스 프록시 설정 (HTTP)
│   └── nginx-ssl.conf.template        # Nginx HTTPS 설정 템플릿
│
├── go2rtc/
│   └── go2rtc.yaml                    # go2rtc WebRTC 서버 설정
│
├── docs/                              # 프로젝트 문서
│   ├── SENTIO_개발로드맵.md       # 이 문서
│   ├── SENTIO_사업기획서.md       # 사업 기획서 (마크다운)
│   ├── SENTIO_발표자료.html       # 발표 자료 (HTML)
│   ├── SENTIO_디자인_레퍼런스.md   # 디자인 가이드
│   ├── ARCHITECTURE.md                # 시스템 아키텍처
│   ├── API.md                         # API 레퍼런스
│   ├── PROGRESS.md                    # 진행 상황 보고서
│   ├── ENHANCEMENT_PLAN.md            # 기능 확장 계획 (Phase 10~14)
│   ├── NOTIFICATION_SYSTEM_REVIEW.md  # 알림 시스템 설계 검토
│   └── archive/                       # 아카이브 (과거 문서)
│
├── scripts/
│   ├── run_dev.bat                    # Windows 개발 서버 실행
│   ├── generate_icons.py             # PWA 아이콘 생성
│   ├── generate_secrets.py           # JWT/VAPID 시크릿 생성
│   └── training/                     # ML 학습 파이프라인
│       ├── extract_landmarks.py      # 영상 → MediaPipe 33점 랜드마크 추출
│       └── train_transformer.py      # GRU 모델 학습 + ONNX 변환
│
├── docker-compose.yml                 # Docker Compose (PostgreSQL + Nginx + FastAPI)
├── docker-compose.ssl.yml             # Docker Compose HTTPS (+ certbot + go2rtc)
├── .env.example                       # 환경변수 템플릿
├── .gitignore
└── README.md                          # 프로젝트 소개
```

**통계 (V4 확정 기준):**
- Backend 파일: ~55개
- Frontend 파일: ~50개
- 테스트: 263개 (전체 통과)
- 낙상 감지 조건: 13개 (C1-C7 + N1-N6)
- V4 벤치마크: Recall 95.2%, Precision 94.6%, F1 94.9 (424개 영상)

---

## 완료된 Phase 상세

### Phase 1: Backend 인프라 (완료)
- FastAPI 앱 + lifespan 기반 서비스 관리
- SQLAlchemy async 데이터베이스 (SQLite)
- JWT 인증 (bcrypt 해싱, 8시간 토큰)
- OpenCV 웹캠 캡처 (전용 스레드)
- MediaPipe PoseLandmarker Tasks API (33개 관절점)
- 4조건 규칙 기반 낙상 감지 + 2초 쿨다운
- 5단계 알림 상태 머신 (normal -> monitoring -> warning -> danger -> acknowledged)

### Phase 2: REST API + WebSocket (완료)
- 이벤트 CRUD + 페이지네이션
- 카메라 상태 조회/시작/중지
- 런타임 설정 조회/변경
- MJPEG 비디오 스트림
- WebSocket 실시간 모니터링 (metrics, pose, alert, heartbeat)

### Phase 3: Frontend 통합 (완료)
- React + TypeScript + Vite 프로젝트 구성
- Zustand 상태 관리 (연결, 알림, 메트릭, 이벤트)
- 대시보드 레이아웃 (비디오, 상태, 메트릭, 이벤트로그, 설정)
- WebSocket 자동 재연결 (지수 백오프)
- DangerAlertDialog (긴급 전체화면 모달)
- Web Audio API 알림음

### Phase 4: UI/UX 보완 (완료)
- Pretendard + Noto Sans KR 웹폰트
- oklch 기반 다크 테마 색상 시스템
- ARIA 레이블 (header, nav, live region)
- Windows 고대비 모드 지원
- Vibration API (danger/warning 진동 패턴)
- 긴급 알림 텍스트 크기 확대
- focus-visible 아웃라인

### Phase 5: Backend 모듈화 (완료)
- Python logging 모듈 기반 named logger 설정
- SentioError 기반 커스텀 예외 계층
- 설정 상수 중앙화 (config.py)
- monitoring_orchestrator.py 파이프라인 분리
- 패키지 __init__.py 정비

### Phase 6: 문서화 (완료)
- README.md (빠른 시작 가이드)
- ARCHITECTURE.md (시스템 설계, ASCII 다이어그램)
- API.md (REST/WebSocket 엔드포인트 레퍼런스)

### Phase 7: 보안 강화 + 로그인 UI (완료)
- JWT_SECRET_KEY 기본값을 빈 문자열로 변경 (런타임 랜덤 생성 + 경고)
- DEBUG 기본값 False
- Settings PUT API 인증 필수
- MJPEG 스트림 토큰 인증
- WebSocket 토큰 인증 (query parameter)
- passlib -> bcrypt 직접 사용 (호환성 문제 해결)
- MediaPipe Tasks API 마이그레이션 (mp.solutions.pose -> PoseLandmarker)
- **LoginPage 컴포넌트** (프론트엔드 로그인 폼)
- App.tsx 인증 래퍼 (토큰 없으면 로그인 표시)
- Header 로그아웃 버튼
- WebSocket URL Vite 프록시 경유로 수정

### Phase 8: 테스트 + 보안 강화 (완료)

**단위 테스트 (63개, 전체 통과):**
- `test_fall_detector.py`: 16개 (4조건 감지, 쿨다운, 상태 전환, per-person 추적)
- `test_alert_manager.py`: 24개 (상태 머신, 타이머, acknowledge, 콜백)
- `test_auth.py`: 23개 (bcrypt 해싱, JWT 발급/검증, 에지 케이스)

**카메라 API 인증:**
- 모든 cameras 엔드포인트에 `Depends(require_auth)` 적용
- VideoFeed.tsx에서 Bearer 토큰 포함 요청

**코드 리뷰 보안 수정:**

| # | 항목 | 수정 내용 |
|---|------|-----------|
| C1 | 회원가입 오픈 | 첫 사용자 자동 admin, 이후 관리자만 등록 가능 + 입력 검증 |
| C3 | Settings GET 미인증 | `Depends(require_auth)` 추가 |
| C4 | 로그인 레이트 리밋 없음 | IP별 5회/60초 제한 (HTTP 429) |
| H5 | datetime.utcnow() deprecated | `datetime.now(timezone.utc)` 전환 |
| M5 | WS 오류 무시 | 로깅 추가 |
| M8 | 스켈레톤 모드 이중 렌더링 | 조건 분기 수정 |

### Phase 9: Docker + PWA + 푸시 알림 (완료)

**Docker 배포 구성:**
- `docker-compose.yml`: PostgreSQL 16 + FastAPI + React + Nginx
- Backend/Frontend 각각 Dockerfile 작성
- Nginx 리버스 프록시 (API, WebSocket, SPA)
- gzip 압축 활성화
- `.env` 환경변수 설정

**PWA (Progressive Web App):**
- `vite-plugin-pwa` 기반 Service Worker 등록
- 정적 자산 프리캐싱 (앱 셸 캐싱)
- `sw-custom.ts` 커스텀 Service Worker (Push 이벤트 핸들링)
- `OfflineBanner.tsx` 오프라인 상태 인디케이터
- 홈 화면 설치 가능

**Web Push 알림 (VAPID):**
- Backend: `push_service.py` (VAPID 키 기반 싱글톤 서비스)
- Backend: `push.py` 라우트 (VAPID 키 조회, 구독/해지)
- Backend: `push_subscription.py` 모델 (endpoint, keys, user_id)
- Frontend: `usePushNotifications.ts` 훅 (권한 요청 → 구독 등록)
- Service Worker가 백그라운드 Push 수신 및 시스템 알림 표시

**인물 추적:**
- `person_tracker.py`: IoU 기반 그리디 매칭으로 프레임 간 안정적 person_id 할당

### Phase 10: 다중 인원 추적 (완료)

**YOLO11s-pose + ByteTrack 통합:**
- Ultralytics 8.3+ 기반 YOLO11s-pose 모델 적용
- ByteTrack (공식 지원) 다중 객체 추적
- `multi_person_detector.py`: YOLO11s-pose 기반 다중 인원 포즈 추정 서비스
- 하이브리드 구조: YOLO11 → 다중 인원 탐지+추적, MediaPipe → ROI 정밀 33점 분석 (선택적)
- Per-person 상태 추적 (각 인물별 독립적 낙상 감지)
- 동시 최대 10명 추적 가능

**성능 최적화:**
- GPU 가속 지원 (CUDA/MPS)
- 프레임 스킵 옵션 (저성능 환경)
- 모델 캐싱으로 초기화 시간 단축

### Phase 11: 영상 스트리밍 고도화 (완료)

**WebRTC 전환 (go2rtc):**
- go2rtc WHEP 프로토콜 기반 WebRTC 서버 추가
- `WebRTCPlayer.tsx`: 프론트엔드 WebRTC 플레이어 (MJPEG 대비 5-10배 대역폭 절약)
- `go2rtc.yaml`: 스트림 소스 설정 (USB 카메라, RTSP 카메라)
- MJPEG 병행 지원 (폴백)

**RTSP IP 카메라 지원:**
- 다중 카메라 소스 관리
- RTSP URL 동적 설정
- 카메라별 독립적 스트림 제어

**영상 저장:**
- 낙상 이벤트 발생 시 스냅샷 자동 저장
- 이벤트별 비디오 클립 생성 (선택적)

### Phase 12: 보안 컴플라이언스 (완료)

**감사 로깅 (Audit Trail):**
- `audit_log.py` 모델: INSERT-only 감사 로그
- `audit_service.py`: 사용자 활동 추적 (로그인, 설정 변경, 이벤트 확인)
- 타임스탬프 + 사용자 + 액션 + 컨텍스트 기록
- 로그 변조 방지 (INSERT만 허용)

**Refresh Token:**
- Access Token: 8시간 (짧은 유효기간)
- Refresh Token: 7일 (장기 세션)
- `/auth/refresh` 엔드포인트로 토큰 갱신
- 자동 갱신 로직 (프론트엔드)

**HTTPS 배포:**
- `docker-compose.ssl.yml`: Let's Encrypt + certbot 통합
- `nginx-ssl.conf.template`: SSL/TLS 설정
- `generate_secrets.py`: JWT/VAPID 시크릿 안전 생성

**추가 보안 강화:**
- CORS 정책 엄격화
- SQL Injection 방지 (SQLAlchemy 파라미터화)
- XSS 방지 (React 자동 이스케이핑)
- CSRF 방지 (SameSite 쿠키)

### Phase 13: AI 고도화 (완료)

**GRU 기반 낙상 분류기 (학습 완료):**
- `fall_classifier.py`: ONNX Runtime 기반 시계열 포즈 분석
- 규칙 기반 감지 + ML 분류기 앙상블 (ML 100% V4 최적)
- **학습 완료**: AIHub 데이터 기반, V4: Recall 95.2%, Precision 94.6%, F1 94.9 (424영상)
- `backend/models/fall_classifier.onnx` (1,227 KB) 배포

**Safe-Zone 관리:**
- `safe_zone.py` 모델: 폴리곤 기반 안전 영역 정의
- `zones.py` 라우트: Safe-Zone CRUD API
- `SafeZoneEditor.tsx`: 프론트엔드 영역 편집기 (Canvas 드래그)
- 침대/의자 영역 제외 로직
- 영역별 감지 설정 (활성화/비활성화)

**행동 패턴 분석 (기초):**
- 장시간 미움직임 감지 (10분 이상)
- 비정상 보행 패턴 탐지 (흔들림, 속도 변화)
- 패턴 이력 대시보드 (미구현)

### Phase 14: 통계 및 EMR 연동 (완료)

**통계 대시보드:**
- `stats.py` 라우트: 시간대별/일별/주별 통계 API
- `StatsView.tsx`: Recharts 기반 차트 (히트맵, 라인 차트, 바 차트)
- 낙상 발생 빈도, 시간대별 분포, 트렌드 분석
- CSV 내보내기 (선택적)

**PDF 리포트 자동 생성 (선택적):**
- `report_service.py`: reportlab 기반 리포트 생성
- 주간/월간 요약 리포트
- 이벤트 이력 + 통계 차트 포함
- 이메일 전송 (선택적)

**HL7 FHIR R4 EMR 연동 (선택적):**
- `fhir_service.py`: httpx 기반 FHIR 클라이언트
- Observation 리소스로 낙상 이벤트 전송
- Patient/Encounter 연동
- FHIR 서버 URL 설정 가능

**API 통합 테스트:**
- `test_api_auth.py`: 10개 (로그인, 토큰 갱신, 권한, 쿠키 인증)
- `test_api_events.py`: 8개 (CRUD, 페이지네이션, 필터링)
- `test_api_stats.py`: 6개 (집계, 시간대별, 트렌드)

### Phase 15: 최종 통합 + 테스트 + 문서 업데이트 (완료)

**통합 테스트:**
- 엔드-투-엔드 시나리오 검증 (카메라 시작 → 낙상 감지 → 알림 → 통계)
- 다중 인원 동시 감지 테스트
- WebRTC 스트리밍 안정성 테스트
- Refresh Token 자동 갱신 검증

**성능 테스트:**
- 10명 동시 추적 시 CPU/메모리 사용량
- WebSocket 연결 100개 동시 처리
- 24시간 연속 가동 안정성 테스트

**문서 업데이트:**
- PROGRESS.md: Phase 10-15 완료 기록
- API.md: 새 엔드포인트 추가 (zones, stats, auth/refresh)
- ARCHITECTURE.md: YOLO11, WebRTC, Safe-Zone 아키텍처 반영
- README.md: 빠른 시작 가이드 갱신

**보안 감사:**
- 전체 코드 베이스 보안 리뷰
- 의존성 취약점 스캔 (pip-audit)
- HTTPS 배포 검증

**버그 수정:**
- WebSocket 재연결 시 메모리 누수 해결
- Safe-Zone 폴리곤 충돌 감지 오류 수정
- YOLO11 GPU 메모리 부족 처리

---

## 향후 계획 (Phase 16+)

> 현재 핵심 기능 완료. 향후 과제는 운영 최적화 및 확장 기능.

### Phase 16: AIHub 낙상 데이터셋 ML 학습 (완료)
- **데이터셋**: [AIHub 낙상사고 위험동작 영상-센서 쌍 데이터](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&dataSetSn=71641)
- **처리 규모**: 2,000건 영상 → MediaPipe 33점 추출 → 20,983 시퀀스 (30프레임 윈도우)
- **클래스 균형**: Fall=4,500, Normal=16,483 → 언더샘플링 → 각 4,500 (총 9,000)
- **모델**: FallDetectionTransformer (d_model=128, nhead=4, num_layers=2, 286,337 params) → GRU 모델로 대체됨
- **학습**: BCELoss, AdamW (lr=1e-3), CosineAnnealingLR, 30 epochs, Best Epoch=25
- **최종 성능**:
  - Accuracy: **88.4%**, Precision: **0.9341**, Recall: **0.8315**, F1: **0.8798**
- **산출물**:
  - `scripts/training/extract_landmarks.py`: 영상 → 랜드마크 추출
  - `scripts/training/train_transformer.py`: 모델 학습 + ONNX 변환
  - `backend/models/fall_classifier.onnx`: 배포 모델 (1,227 KB)
- **앙상블**: ML 100% (V4 최적). GRU 모델로 대체됨.

### Phase 17: 인프라 안정화 + 보안 (완료)

**Task A: JWT → HttpOnly 쿠키 전환:**
- 로그인 시 `Set-Cookie` 헤더로 `access_token`, `refresh_token` HttpOnly 쿠키 설정
- 프론트엔드: localStorage 완전 제거, `credentials: "include"` 기반 인증
- WebSocket/MJPEG: 쿠키 우선 인증, query param 폴백 유지
- `POST /api/auth/logout` 엔드포인트 신규 (쿠키 삭제)
- XSS 공격으로부터 토큰 보호 (JavaScript에서 토큰 접근 불가)

**Task B: Alembic DB 마이그레이션:**
- `alembic.ini` + `migrations/env.py` (async 엔진 지원)
- `render_as_batch=True` (SQLite ALTER TABLE 호환)
- `compare_type=True` (타입 변경 자동 감지)
- 운영 배포: `alembic upgrade head`

**Task C: GitHub Actions CI/CD:**
- `.github/workflows/ci.yml`: push/PR → main 브랜치 트리거
- Job 1: `backend-test` (Ubuntu, Python 3.11, pytest)
- Job 2: `frontend-build` (Node 20, tsc --noEmit, vite build)

### Phase 18: ML 모델 고도화 + 코드리뷰 (완료)
- **4클래스 분류**: 정상/전면 낙상/후면 낙상/측면 낙상
- **데이터 증강**: 노이즈 추가, 스케일 변형, 시간 역전, 좌우 반전 (4종)
- **K-Fold CV**: 5-Fold 교차 검증으로 과적합 방지
- **설정 가능 앙상블 가중치**: 규칙 vs ML 비율 조정 (API 지원)
- **ONNX 출력 자동 감지**: 1/2/4 클래스 모델 호환
- **코드리뷰 9건 수정**

### Phase 19: 리포팅 + 개인정보 + i18n + E2E (완료)
- **CSV/Excel 내보내기**: 이벤트 데이터 다운로드
- **얼굴 블러**: 스냅샷 저장 시 자동 모자이크
- **일간/주간 리포트 스케줄러**: 자동 리포트 생성
- **GDPR 동의**: 개인정보 동의 관리
- **한국어/영어 i18n**: 다국어 지원
- **Playwright E2E 테스트**: 자동화된 UI 테스트

### Phase 20: 5클래스 ML + Pre-impact 전조 감지 (완료)
- **5클래스 확장**: 정상/전면/후면/측면 낙상 + **Pre-impact 전조 감지**
- **Pre-VFall 데이터셋**: 3,659 시퀀스 추출 (학술 논문 기반 전조 행동 데이터)
- **AIHub 대규모 추출**: 18,128건 영상 처리
- **착석 낙상 감지 정밀 튜닝**: 휠체어/의자 환자 대응
- **쿨다운 5초**: 고령자 회복 시간 고려

### Phase 21: 발표 시연 품질 개선 (완료)
- **낙상 유형별 3단계 차등 알림**: 전조 주의 → 낙상 경고 → 실제 낙상 즉시 위험
- **TTS 한국어 음성 알림**: Web Speech API 기반
- **174개 테스트 전체 통과**: 다중인원 통합 17개 신규 포함
- **성능 벤치마크**: 5인 동시 P95=3.07ms

### Phase 22: 보행도구 인식 + 착석 오탐 제거 (완료)
- **YOLO + MediaPipe 하이브리드 보행도구 감지**: walker/cane/crutch/wheelchair
- **인원-도구 매칭**: 근접 인물에 도구 할당
- **도구 분실 "주의" 알림**: 보행도구 없이 이동 시 경고
- **착석 ML 노이즈 스코어 억제**: 시각적 오탐 251+프레임 → 0프레임
- **디버그 프레임 분석 스크립트**: 오탐 원인 추적

### Phase 23: Privacy-First + Skeleton Blackbox (완료)
- **Non-Storage 프라이버시 파이프라인**: 원본 프레임 즉시 파기, 메모리 zeroing
- **Skeleton Blackbox**: 20초 관절 좌표 버퍼 + DANGER 시 JSON 덤프
- **프라이버시 감사 로그**: 데이터 접근 추적
- **사건 API + 스켈레톤 리플레이 뷰어**: 사후 분석 지원
- **개인정보보호법(PIPA) 원천 준수 설계**

### Phase 24: 다중인원 대시보드 + 파이프라인 시각화 (완료)
- **다중인원 실시간 모니터링 대시보드**: 인물별 자세/낙상유형/규칙+ML점수/보행도구 상태
- **알림 트리거 인물 표시**: StatusCard에서 원인 인물 강조
- **이벤트 로그 person_id 뱃지**: 누가 넘어졌는지 명확히
- **AI 파이프라인 SVG 시각화**: 스포트라이트/현미경 비유 + CSS 애니메이션
- **비전공자 맞춤 발표자료**: 쉬운 설명 추가

### Phase 25: 전조 감지 조기 경고 + 카메라 상태 동기화 (완료)
- **Pre-impact 전조 감지 조기 경고**: ML 단독 전조 임계값 분리 (FALL_PRE_IMPACT_ML_THRESHOLD)
- **카메라 상태 동기화**: 연결 끊김/로딩 스피너 UI 동기화
- **보행도구 정확도 개선**: 프레임 버퍼 15→25, 연관 거리 0.3→0.42 조정
- **254개 테스트 전체 통과**

### Phase 26: 앙상블 가중치 최적화 + 규칙확장 13조건 (완료)
- **6개 가중치 조합 벤치마크**: A(규칙100%), B(규칙70%), C(50/50), D(ML70%), E(ML100%), F(규칙확장)
- **규칙확장 N1-N6 조건 구현**:
  - N1: 수직 가속도 (head_y 3프레임 가속)
  - N2: 보호 신전 반응 (팔 벌림 + 손목 하강)
  - N3: CoM-BoS 이탈 (무게중심-지지면 편차 증가)
  - N4: 무릎 좌굴 (knee angle rate + angle limit)
  - N5: 체간 회전 속도 (shoulder tilt delta)
  - N6: 높이 궤적 패턴 (후반부 가속)
- **rule-enhanced 프로필 기본값 적용**: 규칙 100% + 확장 13조건
- **벤치마크 결과**:
  - **13,039 FPS** (GPU 불필요)
  - **71.4% 정확도** (ML 단독과 동등)
  - **메모리 41MB 절약** (ONNX 추론 생략)
- **COCO 17점 ↔ MediaPipe 33점 어댑터**: keypoint_adapter.py 신규

## Phase 27: COCO 17점 키포인트 지원 + 낙상 감지 정확도 개선 (완료)

### 주요 개선 사항

#### **Quick Recovery Detection**
- **문제**: 의도적으로 잠깐 눕는 동작(스트레칭, 물건 집기)을 낙상으로 오탐
- **해결**: lying < 10프레임 + standing >= 5프레임 → 의도적 눕기로 판정
- **성과**: N_normal_standing_03.mp4 오탐 65프레임 → 14프레임 (78% 감소)

#### **Multi-frame Accumulation**
- **문제**: AIHub C1/C4/C8 카메라 각도에서 가시성 낮은 키포인트로 인한 미감지
- **해결**: 가시성 0.3-0.5 범위에서 3프레임 연속 점수 >= 0.35 → 누적 감지
- **성과**: C1_fall_01.mp4 등 저가시성 낙상 영상 감지율 향상

#### **Controlled Movement Post-Fall**
- **문제**: 낙상 후 스스로 일어서는 동작을 지속 위험으로 잘못 판정
- **해결**: 10프레임 후 속도 분산 < 0.0005 + 자세≠LYING → 제어된 동작 판정
- **성과**: 낙상 후 회복 동작 정상 판정, 불필요한 알림 감소

#### **Trip Fall Boost**
- **문제**: 전방 넘어짐(trip fall) 시 sitting 자세 특성으로 미감지
- **해결**: sitting 상태 + 수평 각도 < 50° → 점수 보정 강화
- **성과**: FY_front_fall_trip.mp4 감지 0프레임 → 38프레임 (완전 해결)

#### **COCO 17점 어댑터**
- **구현**: `KeypointAdapter.coco_to_mediapipe_33()` - YOLO Pose 17점을 MediaPipe 33점으로 변환
- **매핑**: 직접 매핑 17점 + 보간 추정 16점 (얼굴, 손, 발 세부 관절)
- **호환성**: 기존 낙상 감지 로직 100% 재사용

### 테스트 결과

| 지표 | 값 |
|------|------|
| 단위 테스트 | **261개 전체 통과** (174 → 261) |
| 데모 영상 Recall | **100%** (24/24 유지) |
| 정상 영상 오탐 | **지속시간 감소** |
| Quick Recovery | 65 → 14프레임 (78% 개선) |
| Trip Fall 감지 | 0 → 38프레임 (완전 해결) |

### 기술 세부 사항

**키포인트 어댑터 (keypoint_adapter.py)**
```python
# COCO 17점 → MediaPipe 33점 변환
# - 직접 매핑: 17개 공통 관절점
# - 보간 추정: 얼굴(8), 손(4), 발(4) 세부 관절
# - 가시성 전파: 신뢰도 기반 가중 평균
```

**낙상 감지 로직 강화 (fall_detector.py)**
```python
# Quick Recovery: lying_frames < 10 and standing_frames >= 5
# Multi-frame Accum: vis ∈ [0.3, 0.5], streak >= 3, score >= 0.35
# Controlled Movement: var(speed[10:]) < 0.0005, posture != LYING
# Trip Fall Boost: sitting + torso_angle < 50° → score *= 1.2
```

### 향후 확장
- **YOLO Pose 단독 모드**: MediaPipe 완전 생략, 17점만으로 감지 (성능 비교 대기)
- **실시간 어댑터 전환**: 런타임 17점 ↔ 33점 모드 전환
- **추가 오탐 케이스 수집**: 실제 배포 환경 피드백 반영

### Phase 28+ (향후 과제)
- **SMS 에스컬레이션**: Twilio 기반 긴급 SMS 알림
- **Redis 메시지 버퍼**: 대규모 알림 처리 (큐잉)
- **Safe-Zone 감지 파이프라인 연동**: 위험구역 진입 시 즉시 경고
- **IoT 경광등 연동**: Webhook 기반 외부 디바이스 알림
- **INT8 양자화**: ONNX 모델 경량화
- **TensorRT GPU 최적화**: 고성능 환경 대응
- **엣지 디바이스 배포**: Jetson Nano, Raspberry Pi
- **GRU 재학습 (negative mining 전략)**: 잔여 FP/FN 해결

---

## 실행 방법

### 개발 환경

```bash
# 백엔드
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프론트엔드 (별도 터미널)
cd frontend
npm install
npm run dev
```

### Docker 실행

```bash
# 1. 환경변수 생성 (시크릿 자동 생성)
python scripts/generate_secrets.py

# 2. .env 파일 편집 (필요시)
# JWT_SECRET_KEY, VAPID_PRIVATE_KEY 등 자동 생성됨

# 3. Docker Compose 실행
docker compose up -d

# 4. HTTPS 배포 (프로덕션)
docker compose -f docker-compose.ssl.yml up -d

# 접속: http://localhost (HTTP) 또는 https://yourdomain.com (HTTPS)
```

### 접속

1. 브라우저에서 `http://localhost:5173` 접속 (개발) 또는 `http://localhost` (Docker)
2. 로그인 페이지에서 계정 입력 (최초: Swagger `/docs`에서 회원가입)
3. 대시보드에서 "시작" 버튼으로 카메라 활성화

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| [README.md](../README.md) | 프로젝트 소개 및 빠른 시작 가이드 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 시스템 아키텍처 및 설계 결정 |
| [API.md](./API.md) | REST API / WebSocket 엔드포인트 레퍼런스 |
| [PROGRESS.md](./PROGRESS.md) | 진행 상황 보고서 |
| [ENHANCEMENT_PLAN.md](./ENHANCEMENT_PLAN.md) | 기능 확장 계획 (Phase 10~14) |
| [SENTIO_사업기획서.md](./SENTIO_사업기획서.md) | 사업 기획서 |
| [SENTIO_발표자료.html](./SENTIO_발표자료.html) | 발표 자료 (HTML) |
| [SENTIO_디자인_레퍼런스.md](./SENTIO_디자인_레퍼런스.md) | UI/UX 디자인 가이드 |

---

*최종 업데이트: 2026-02-11 (Phase 1-33 완료, V4 확장 벤치마크 확정: Recall 95.2%, Precision 94.6%, F1 94.9, 424영상, 267개 테스트 통과)*
