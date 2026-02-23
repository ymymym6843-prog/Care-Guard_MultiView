# SENTIO AI

요양병원 대기실 낙상·이상움직임 감지 웹 애플리케이션

## 개요

SENTIO는 요양병원의 대기실에서 실시간 카메라 영상을 분석하여 노인 및 환자의 낙상 및 이상 움직임을 감지하는 AI 기반 모니터링 시스템입니다. YOLO11 기반 다중 인원 감지, AI 앙상블 낙상 분류, WebRTC 스트리밍, 통계 대시보드, EMR/FHIR 연동을 통해 빠르고 정확한 위험 감지 및 알림을 제공합니다.

## 주요 기능

- **실시간 카메라 영상 분석**: YOLO11s-pose 기반 다중 인원 감지 (4모델 벤치마크 검증, GPU/CPU 자동 최적화)
- **AI 앙상블 낙상 감지**: 13가지 규칙 기반 + GRU 딥러닝 이중 판정 앙상블 (설정 가능 가중치) — Binary 분류 (Fall/Normal), **F1 94.9 (424개 영상 검증)**
- **다중 인원 추적**: ByteTrack 기반 개인별 track_id 유지
- **확률 기반 차등 알림 시스템**: 확신도 0.50~0.69 → WARNING (이상 자세 감지) → 0.70+ → DANGER (낙상 확인, 0.5초 지연) + Web Push + 알림음 + **TTS 음성 알림** + 진동
- **WebRTC 영상 스트리밍**: go2rtc WHEP 기반 (MJPEG 폴백)
- **통계 대시보드**: 일별/시간대별 차트, 요약 카드 (Recharts)
- **Safe-Zone 관리**: Canvas 폴리곤 에디터로 안전/위험 구역 설정
- **EMR 연동**: HL7 FHIR R4 Observation 리소스 변환
- **HttpOnly 쿠키 인증**: Access 8시간 + Refresh 7일 자동 갱신 (XSS 방어)
- **IoT 디바이스 연동**: Webhook 기반 경광등/스마트 알림장치 제어 (HMAC 서명)
- **다중 카메라 선택**: 런타임 카메라 전환 (연결된 카메라 자동 탐색, 드롭다운 선택, 카메라별 독립 AI 파이프라인)
- **다중공간(Multi-Room) 관리**: 공간별 카메라 배정, 사이드바 드롭다운으로 공간 전환, 공간별 독립 대시보드/통계/리포트/이벤트 필터링
- **오탐지 보고 관리**: 오탐/미탐 보고 CRUD + 통계 요약 + 임계치 알림 (모델 개선 파이프라인)
- **감사 로그**: INSERT-only audit trail
- **PWA**: 오프라인 지원 + 홈 화면 설치
- **Docker 배포**: Docker Compose (PostgreSQL + Nginx + go2rtc + certbot)

## 기술 스택

| 분야 | 기술 |
|------|------|
| Backend | FastAPI, Python 3.11+, SQLAlchemy |
| AI/CV | YOLO11s-pose (ultralytics) + GRU 앙상블 분류기 + ONNX Runtime (GPU/CPU 자동 최적화) |
| Streaming | MJPEG + WebRTC (go2rtc) |
| Frontend | React 18, TypeScript, Vite 6, Tailwind CSS 4 |
| Charts | Recharts |
| State Management | Zustand |
| UI Components | Radix UI, Lucide Icons |
| Database | PostgreSQL + SQLAlchemy |
| EMR | HL7 FHIR R4 (httpx) |
| IoT | Webhook + HMAC-SHA256 (httpx) |
| Authentication | HttpOnly Cookie + JWT + bcrypt |
| DB Migration | Alembic (async, SQLite batch mode) |
| CI/CD | GitHub Actions (pytest + tsc + vite build) |
| Container | Docker Compose + Nginx + go2rtc + certbot |
| Fonts | Pretendard, Noto Sans KR |

## 프로젝트 구조

```
sentio/
├── .github/
│   └── workflows/
│       └── ci.yml                   # GitHub Actions CI/CD
├── backend/
│   ├── alembic.ini                  # Alembic DB 마이그레이션 설정
│   ├── migrations/                  # Alembic 마이그레이션 디렉터리
│   │   ├── env.py
│   │   └── script.py.mako
│   └── app/
│       ├── main.py                  # FastAPI 애플리케이션 진입점
│       ├── config.py                # 설정 및 환경 변수 (쿠키 설정 포함)
│       ├── api/routes/              # REST API 엔드포인트
│       │   ├── auth.py              # 로그인/회원가입/로그아웃 (쿠키 기반)
│       │   ├── zones.py             # Safe-Zone 관리
│       │   ├── stats.py             # 통계 데이터
│       │   ├── models.py            # AI 모델 관리
│       │   ├── rooms.py             # 공간 관리 + 카메라 배정
│       │   └── false_reports.py     # 오탐지 보고 관리
│       ├── core/                    # 인증, DB, 로깅, 예외 처리
│       ├── services/                # 비즈니스 로직
│       │   ├── multi_person_detector.py    # YOLO11 + MediaPipe
│       │   ├── fall_classifier.py          # 앙상블 낙상 분류
│       │   ├── audit_service.py            # 감사 로그
│       │   ├── report_service.py           # 리포트 생성
│       │   ├── fhir_service.py             # FHIR 변환
│       │   └── iot_service.py              # IoT Webhook 연동
│       └── models/                  # SQLAlchemy ORM 모델
│           ├── audit_log.py
│           ├── safe_zone.py
│           └── room.py              # 공간/카메라 매핑 모델
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── RoomManager.tsx      # 공간 관리 UI
│       │   ├── layout/
│       │   │   ├── RoomSelector.tsx # 공간 전환 드롭다운
│       │   ├── Stats/               # 통계 컴포넌트
│       │   ├── Dashboard/
│       │   │   ├── WebRTCPlayer.tsx
│       │   │   └── SafeZoneEditor.tsx
│       │   ├── RegisterPage.tsx
│       │   └── UserManagement.tsx
│       ├── hooks/                   # 커스텀 훅
│       │   ├── useRooms.ts          # 공간 목록 조회
│       ├── store/                   # Zustand 상태 관리
│       └── styles/                  # 전역 CSS
├── docs/                            # 프로젝트 문서
├── go2rtc/
│   └── go2rtc.yaml                  # WebRTC 스트리밍 설정
├── nginx/                           # Reverse Proxy 설정
├── scripts/
│   ├── generate_secrets.py          # JWT/VAPID 키 생성 스크립트
│   └── training/                    # ML 학습 파이프라인
│       ├── extract_landmarks.py     # 영상 → 랜드마크 추출
│       └── train_transformer.py     # Transformer 학습 + ONNX 변환
├── docker-compose.yml               # 개발 환경
├── docker-compose.ssl.yml           # 프로덕션 환경 (HTTPS)
└── .env.example                     # 환경 변수 템플릿
```

## 빠른 시작

### 필수 요구사항

- Python 3.11 이상
- Node.js 18 이상
- Docker 및 Docker Compose (Docker 배포 시)
- 웹캠

### Docker로 전체 시스템 실행

```bash
# 환경 변수 설정
cp .env.example .env

# 전체 시스템 시작
docker compose up -d --build

# http://localhost 접속
```

### Backend 설정 (로컬 개발)

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 환경 변수 설정
cp ../.env.example ../.env
# .env 파일에서 필요한 값 수정

# 서버 시작
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

Backend는 `http://0.0.0.0:8001`에서 실행됩니다.

### Frontend 설정 (로컬 개발)

```bash
cd frontend

# 패키지 설치
npm install

# 개발 서버 시작
npm run dev
```

Frontend는 `http://localhost:5173`에서 접근 가능합니다.

### 최초 사용자 등록

브라우저에서 `http://localhost:5173` 접속 시 최초 사용자 등록 페이지가 자동으로 표시됩니다.

### 접속

1. 브라우저에서 `http://localhost:5173` (로컬) 또는 `http://localhost` (Docker)을 열어 로그인 페이지에 접속합니다.
2. 등록한 계정으로 로그인합니다.
3. 대시보드에서 "시작" 버튼을 눌러 카메라 모니터링을 시작합니다.

## 환경 변수

프로젝트 루트의 `.env` 파일에서 다음 변수를 설정합니다. `.env.example`을 참고하세요.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| HOST | 0.0.0.0 | 서버 호스트 주소 |
| PORT | 8001 | 서버 포트 번호 |
| DEBUG | false | 디버그 모드 활성화 |
| DATABASE_URL | (변경 필요) | PostgreSQL 연결 URL |
| FRONTEND_URL | http://localhost:5173 | CORS 허용 Frontend URL |
| JWT_SECRET_KEY | (변경 필요) | JWT 서명용 시크릿 키 (반드시 변경) |
| INTERNAL_STREAM_KEY | (변경 필요) | go2rtc 내부 서비스 인증 키 |
| FALL_WARNING_SECONDS | 3.0 | 주의 알림 활성화 시간 (초) |
| FALL_DANGER_SECONDS | 0.5 | DANGER 전환 지연 시간 (초) |
| FALL_DANGER_CONFIDENCE | 0.70 | DANGER 전환 확신도 임계값 |
| VAPID_PRIVATE_KEY | (변경 필요) | Web Push 개인 키 |
| VAPID_PUBLIC_KEY | (변경 필요) | Web Push 공개 키 |
| FHIR_BASE_URL | (선택) | EMR FHIR 서버 URL |
| FHIR_API_KEY | (선택) | EMR FHIR API 키 |
| IOT_WEBHOOK_URL | (선택) | IoT 디바이스 Webhook URL |
| IOT_WEBHOOK_SECRET | (선택) | IoT Webhook HMAC 서명 키 |

### 보안 주의사항

- `JWT_SECRET_KEY`는 강력한 난수로 설정하고 절대 공개하지 마세요
- `VAPID_PRIVATE_KEY`는 안전한 환경에서만 관리하세요
- `FRONTEND_URL`은 실제 배포 환경의 URL로 수정해야 합니다
- 프로덕션 환경에서는 `DEBUG`를 `false`로 설정하세요
- `FHIR_API_KEY`는 암호화하여 저장하세요
- `IOT_WEBHOOK_SECRET`는 강력한 난수를 사용하세요

## 문서

| 문서 | 설명 |
|------|------|
| [시스템 아키텍처](docs/02_technical/ARCHITECTURE.md) | 시스템 설계, 데이터 흐름, 기술 결정 근거 |
| [API 레퍼런스](docs/02_technical/API.md) | REST API / WebSocket / Push 엔드포인트 상세 |
| [진행 상황](docs/05_progress/PROGRESS.md) | Phase별 완료 현황, 기술 부채, 기술 스택 |
| [확장 계획](docs/ENHANCEMENT_PLAN.md) | Phase 9-15 로드맵 (최신 기술 동향 반영) |
| [디자인 레퍼런스](docs/SENTIO_디자인_레퍼런스.md) | UI/UX 가이드 및 구현 현황 |

## 라이선스

MIT License - 자유로운 사용, 수정, 배포 가능합니다.
