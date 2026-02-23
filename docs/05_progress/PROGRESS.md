# SENTIO 프로젝트 진행 상황 보고서

> 최종 업데이트: 2026-02-13 (Phase 37 ONNX CPU 자동 최적화)

---

## 전체 요약

| 항목 | 상태 |
|------|------|
| 완성도 | **V4 확정** (Recall 95.2%, Precision 94.6%, F1 94.9 — 424개 영상 확장 벤치마크) |
| Phase 완료 | 37 Phase 완료 (Phase 1-37: MVP → Pilot-Ready → 다중공간 → ONNX CPU 자동 최적화) |
| Backend 파일 | 44+ Python 모듈 (테스트 포함) |
| Frontend 파일 | 46+ TSX/TS 모듈 |
| 문서 파일 | 8개 (활성) + 4개 (아카이브) |
| 학습 스크립트 | 5개 (extract_landmarks, extract_prevfall_landmarks, train_v2, data_preprocessing, download) |
| 디버그/분석 | `scripts/debug_frame_capture.py` — 프레임별 낙상 감지 분석 + 스크린샷 저장 + CSV 로그 |
| 단위 테스트 | **294개** (단위 테스트 + API 통합 + 다중인원 통합 17개 + 보행도구 감지 테스트 + 앙상블 프로필 19개 + zone_checker 14개 + rooms 13개) — 전체 통과 |
| 성능 벤치마크 | 5인 동시 감지 P95 = 3.07ms (30 FPS 예산 33.3ms 대비 **9.2%** 사용) |
| Docker | docker-compose.yml + SSL 오버라이드 (PostgreSQL + Nginx + FastAPI + go2rtc) |
| PWA | vite-plugin-pwa + Service Worker + 오프라인 배너 |
| 푸시 알림 | Web Push (VAPID) 기반 구독/전송 구현 완료 |
| AI 파이프라인 | YOLO11 + COCO 17점 KeypointAdapter + **GRU ONNX 앙상블 (ML 100%)** — **Binary 분류 (Fall/Normal)** + 보행도구 YOLO 감지 + **ONNX CPU 자동 최적화 (Phase 37)** |
| 인증 | HttpOnly 쿠키 기반 (XSS 방어) + Bearer 폴백 |
| DB 마이그레이션 | Alembic (async 엔진, SQLite batch mode) |
| CI/CD | GitHub Actions (backend pytest + frontend tsc/build) |
| 영상 프로토콜 | MJPEG + WebRTC (go2rtc WHEP) + RTSP |
| EMR 연동 | HL7 FHIR R4 Observation 리소스 |
| ML 학습 데이터 | AIHub 665,574 시퀀스 (30프레임×99특징) — GRU 모델 학습 완료 |
| 다중공간 | Room CRUD + 카메라 배정 + 공간별 필터링 (대시보드/통계/리포트/이벤트) |
| 다중 카메라 | 카메라별 독립 리셋 + 플레이리스트 모드 + per-camera YOLO 트래커 격리 |

---

## Phase별 완료 현황

### Phase 1-6: 기본 인프라 ~ 문서화 (완료)

초기 인프라부터 문서화까지 전체 구축 완료.

### Phase 7: 보안 강화 + 로그인 UI (완료)

**보안 수정 5건:**

| # | 항목 | 수정 내용 |
|---|------|-----------|
| 1 | JWT_SECRET_KEY 기본값 | 빈 문자열 기본값 + 런타임 랜덤 생성 + warnings 경고 |
| 2 | DEBUG 기본값 | `True` -> `False` |
| 3 | Settings API 인증 | PUT `/api/settings`에 `Depends(require_auth)` 추가 |
| 4 | MJPEG 스트림 인증 | query parameter `token` 필수 |
| 5 | WebSocket 인증 | query parameter `token` 필수, 미인증 시 4001 코드 |

**호환성 수정:**

| 문제 | 해결 |
|------|------|
| passlib + bcrypt 호환 불가 | passlib 제거, bcrypt 직접 사용 |
| mediapipe 0.10.30+ `mp.solutions.pose` 삭제 | PoseLandmarker Tasks API로 전체 재작성 |

**프론트엔드 로그인 시스템:**

| 파일 | 내용 |
|------|------|
| `LoginPage.tsx` (신규) | 로그인 폼 (OAuth2 form-data POST) |
| `App.tsx` | 토큰 없으면 로그인, 있으면 대시보드 |
| `Header.tsx` | 로그아웃 버튼 추가 |
| `useWebSocket.ts` | WS URL을 Vite 프록시 경유로 변경, 토큰 없으면 연결 안 함 |
| `lib/auth.ts` (신규) | localStorage 토큰 관리 + withTokenParam 유틸리티 |

### Phase 8: 테스트 + 보안 강화 (완료)

**단위 테스트 (63개, 전체 통과):**

| 파일 | 테스트 수 | 내용 |
|------|----------|------|
| `test_fall_detector.py` | 16 | 13조건 감지, 쿨다운, 상태 전환, per-person 추적, 히스토리 maxlen |
| `test_alert_manager.py` | 24 | 상태 머신, 타이머, acknowledge, 콜백, 프론트엔드 상태 매핑 |
| `test_auth.py` | 23 | bcrypt 해싱, JWT 발급/검증, 만료, 잘못된 시그니처, 에지 케이스 |

### Phase 9: Docker + PWA + PersonTracker (완료)

| 항목 | 내용 |
|------|------|
| Docker Compose | PostgreSQL + Nginx + FastAPI + frontend build 서비스 |
| PWA | vite-plugin-pwa + Service Worker + 오프라인 배너 |
| Push 알림 | Web Push (VAPID) 구독/전송 |
| PersonTracker | multi-person 추적 기반 (per-person fall detection) |

### Phase 10: YOLO11 다중 인원 추적 (완료)

| 파일 | 변경 |
|------|------|
| `multi_person_detector.py` (신규) | YOLO11s-pose + ByteTrack 감지기 (lazy-load, 싱글톤) |
| `bytetrack.yaml` (신규) | ByteTrack 추적 설정 (track_high_thresh=0.5, track_buffer=30) |
| `requirements.txt` | `ultralytics>=8.3.0` 추가 |
| `pose_service.py` | `process_roi_sync()` 추가 (ROI 크롭 → MediaPipe 33점, IMAGE 모드) |
| `monitoring_orchestrator.py` | 하이브리드 파이프라인 재작성 |
| `Dockerfile` | YOLO 모델 빌드 타임 다운로드 |
| `MetricsCard.tsx` | 인원별 상태 카드 표시 |

**파이프라인:**
```
[YOLO 모드] Camera → YOLO11 (N명 bbox+track_id) → 각 ROI → MediaPipe (33점) → FallDetector → Alert
[폴백 모드] Camera → MediaPipe (5명 제한) → PersonTracker → FallDetector → Alert
```

### Phase 11: WebRTC + RTSP 카메라 (완료)

| 파일 | 변경 |
|------|------|
| `go2rtc/go2rtc.yaml` (신규) | 스트림 설정 (MJPEG → WebRTC 변환) |
| `docker-compose.yml` | go2rtc 서비스 추가 (alexxit/go2rtc) |
| `nginx.conf` | `/webrtc/` 프록시 블록 추가 |
| `camera.py` | RTSP URL, 인증 정보, stream_protocol 필드 확장 |
| `WebRTCPlayer.tsx` (신규) | WHEP 기반 WebRTC 플레이어 + MJPEG 폴백 |

### Phase 12: Gunicorn + HTTPS (완료)

| 파일 | 변경 |
|------|------|
| `Dockerfile` | `--proxy-headers`, `--max-requests 1000` Gunicorn 설정 |
| `nginx-ssl.conf` (신규) | HTTPS: TLS 1.2+, HSTS, 보안 헤더, ACME challenge |
| `docker-compose.ssl.yml` (신규) | certbot 서비스 + SSL 볼륨 마운트 (오버라이드 파일) |

### Phase 13: 보안 컴플라이언스 (완료)

| 파일 | 변경 |
|------|------|
| `audit_log.py` (신규) | INSERT-only 감사 로그 모델 |
| `audit_service.py` (신규) | 감사 로깅 서비스 (exception-safe) |
| `core/auth.py` | `create_refresh_token()` 추가 (7일 만료, type=refresh) |
| `auth.py` 라우트 | `POST /api/auth/refresh` 엔드포인트 |
| `lib/auth.ts` | 자동 토큰 갱신 인터셉터 (`apiCall()` 래퍼) |
| `push_subscription.py` | `datetime.utcnow()` → `datetime.now(timezone.utc)` 수정 |

### Phase 14: AI 고도화 (완료)

| 파일 | 변경 |
|------|------|
| `fall_classifier.py` (신규) | GRU ONNX 분류기 (30프레임 시퀀스, Binary 분류) |
| `fall_detector.py` | 앙상블 스코어링 (ML 100% 최적, 설정 가능 가중치) |
| `safe_zone.py` (신규) | SafeZone 모델 (폴리곤 좌표, zone_type, is_active) |
| `zones.py` (신규) | Safe-Zone CRUD API (admin 전용 쓰기) |
| `SafeZoneEditor.tsx` (신규) | Canvas 폴리곤 드래그 에디터 |

### Phase 15: 통계 + EMR 연동 (완료)

| 파일 | 변경 |
|------|------|
| `stats.py` (신규) | 일별/시간대별/인원별/요약 통계 API |
| `StatsView.tsx` (신규) | Recharts 기반 통계 대시보드 (일별 차트, 시간대별 히트맵, 요약 카드) |
| `report_service.py` (신규) | PDF 리포트 생성 (reportlab, JSON 폴백) |
| `fhir_service.py` (신규) | HL7 FHIR R4 Observation 리소스 변환 + 전송 |
| `Sidebar.tsx` | "통계" 네비게이션 항목 추가 |
| `MainLayout.tsx` | StatsView 라우트 + UserManagement (admin) |
| `package.json` | `recharts ^2.15.0` 의존성 추가 |

### Phase 16: AIHub 낙상 데이터셋 ML 학습 (완료)

**학습 데이터:**
- AIHub 낙상사고 위험동작 영상 2,000건 처리 (실패 0건)
- MediaPipe 33점 랜드마크 추출 → 30프레임 슬라이딩 윈도우
- 총 20,983 시퀀스 생성 (Fall=4,500, Normal=16,483)
- 클래스 균형: 언더샘플링 → 9,000 시퀀스 (Fall 4,500 / Normal 4,500)

**모델 아키텍처:**
- FallDetectionTransformer: Input(30, 99) → Linear(99→128) → PositionalEncoding → TransformerEncoder(2 layers, 4 heads) → GlobalAvgPool → FC(128→64→1) → Sigmoid
- 파라미터: 286,337개 (~1,117 KB)

**학습 설정:**
- BCELoss, AdamW (lr=1e-3, weight_decay=1e-4), CosineAnnealingLR, Early Stopping (patience=7, F1 기준)
- 30 에포크 학습, Best Epoch: 25

**최종 성능 (검증 세트):**

| 지표 | 수치 |
|------|------|
| Accuracy | **88.4%** |
| Precision | **0.9341** |
| Recall | **0.8315** |
| F1 Score | **0.8798** |

**산출물:**

| 파일 | 설명 |
|------|------|
| `scripts/training/extract_landmarks.py` (신규) | 영상 → MediaPipe 33점 랜드마크 추출 스크립트 |
| `scripts/training/train_transformer.py` (신규) | Transformer 모델 학습 + ONNX 변환 스크립트 |
| `backend/models/fall_classifier.onnx` | **학습된 ONNX 모델 (1,227 KB)** — 배포 완료 |

**참고**: 이 Transformer 모델은 이후 GRU 모델로 대체되었습니다 (Phase 27 후반). 현재 사용 중인 GRU 모델: AIHub 665,574 샘플, Recall 84.3%, Precision 97.0%.

### Phase 18: ML 모델 고도화 (완료)

**목표**: Binary 분류 → 4-Class 분류 + 전체 데이터셋 지원 + 앙상블 개선

**학습 스크립트 개선:**

| 파일 | 변경 |
|------|------|
| `extract_landmarks.py` | 4클래스 라벨링 (FY→1, BY→2, SY→3, N→0) + 데이터 증강 4종 (jitter, flip, scale, temporal) |
| `train_transformer.py` | 4클래스 아키텍처 (CrossEntropyLoss) + K-Fold CV + per-class 메트릭 + 추론 벤치마크 |
| `requirements.txt` (scripts) | scikit-learn 추가 (classification_report, StratifiedKFold) |

**런타임 업데이트:**

| 파일 | 변경 |
|------|------|
| `fall_classifier.py` | `predict_detailed()` 추가: ONNX 출력 자동 감지 (1/2/4), `FallPrediction` 데이터클래스 |
| `fall_detector.py` | 설정 가능 앙상블 가중치 (`rule_weight`/`ml_weight` property), `fall_type`/`rule_score`/`ml_score` 반환 |
| `monitoring_orchestrator.py` | WebSocket `metrics_update`에 `fall_type`, `rule_score`, `ml_score` 전파 |
| `config.py` | `FALL_RULE_WEIGHT=0.5`, `FALL_ML_WEIGHT=0.5` 환경 변수 추가 |
| `settings_route.py` | 앙상블 가중치 런타임 조정 API (자동 보완 계산) |

**테스트:**

| 파일 | 테스트 수 | 내용 |
|------|----------|------|
| `test_fall_classifier.py` (신규) | 17 | binary sigmoid/softmax 호환, 4클래스 fall_type, 버퍼 관리, 비활성화 동작 |
| `test_fall_detector.py` (수정) | +6 | 앙상블 가중치, fall_type, rule/ml score, 기본 결과 필드, ML 앙상블 통합 테스트 |
| `conftest.py` (수정) | +6 fixture | 4클래스 mock ONNX 출력 |

**ONNX 출력 자동 감지:**
- 출력 1개 → sigmoid binary (기존 모델 호환)
- 출력 2개 → softmax binary [정상, 낙상]
- 출력 4개 → 4클래스 softmax [normal, front_fall, back_fall, side_fall]

**데이터 증강 4종:**
- `augment_jitter()` - 좌표 가우시안 노이즈 (sigma=0.003)
- `augment_horizontal_flip()` - 좌우 반전 (16개 랜드마크 쌍 교환)
- `augment_scale()` - 체형 변화 시뮬레이션 (0.9~1.1배)
- `augment_temporal_noise()` - 프레임 드롭/복제로 시간적 노이즈

**코드리뷰 수정 (Critical 3건 + Warning 6건):**

| # | 심각도 | 파일 | 수정 내용 |
|---|--------|------|-----------|
| C-1 | Critical | `monitoring_orchestrator.py` | `fall_detector.detect()`를 `run_in_executor(_ml_executor)`로 래핑 → ONNX 추론 시 이벤트 루프 블로킹 방지 |
| C-2 | Critical | `core/auth.py` | `payload.get("type") != "access"` 검증 추가 → refresh 토큰으로 access 토큰 대용 방지 |
| C-3 | Critical | `settings_route.py` | 앙상블 가중치 합계 검증 (두 값 동시 전달 시 합 = 1.0 강제) |
| W-1 | Warning | `fall_classifier.py`, `fall_detector.py` | 스레드 안전성 문서화 (ml-worker 스레드 사용 설명) |
| W-2 | Warning | `stream.py` | 정수 카운터 → `asyncio.Semaphore` 기반 MJPEG 동시 연결 제한 (async-safe) |
| W-3 | Warning | `fall_classifier.py` | 예상치 못한 ONNX 출력 차원 시 경고 로그 추가 |
| W-4 | Warning | `test_fall_detector.py` | ML 활성화 상태 앙상블 통합 테스트 추가 (`test_ensemble_weighted_average_with_ml_enabled`) |
| W-5 | Warning | `settings_route.py` | setter 호출 후 `_runtime_settings` 동기화 (`fall_ml_weight` 역산) |
| W-6 | Warning | `monitoring_orchestrator.py` | `.get()` → `[]` 직접 접근으로 일관성 확보 |

**참고**: 4-5클래스 분류는 실험적으로 시도되었으나, 최종적으로 GRU Binary 분류 모델이 채택되었습니다.

### Phase 19: 리포팅 + 개인정보보호 + i18n + E2E 테스트 (완료)

**CSV/Excel 데이터 내보내기:**

| 파일 | 변경 |
|------|------|
| `events.py` | `GET /api/events/export?format=csv|xlsx&days=30` 엔드포인트 추가 |
| `requirements.txt` | `openpyxl>=3.1.0` 추가 |

**얼굴 블러 서비스:**

| 파일 | 변경 |
|------|------|
| `face_blur_service.py` (신규) | Haar Cascade 얼굴 감지 + Gaussian blur (싱글턴, graceful degradation) |
| `config.py` | `FACE_BLUR_ENABLED` 설정 추가 |

**리포트 시스템:**

| 파일 | 변경 |
|------|------|
| `reports.py` (신규) | 리포트 목록/다운로드/수동 생성 API |
| `report_scheduler.py` (신규) | asyncio 기반 일간/주간 자동 리포트 스케줄러 (30초 폴링) |
| `config.py` | `REPORT_SCHEDULE_DAILY`, `REPORT_SCHEDULE_WEEKLY`, `REPORT_OUTPUT_DIR` 설정 추가 |
| `main.py` | reports 라우터 등록 + 스케줄러 lifespan 통합 |
| `ReportView.tsx` (신규) | 리포트 생성/다운로드 + CSV/Excel 내보내기 UI |

**GDPR/개인정보보호 동의:**

| 파일 | 변경 |
|------|------|
| `auth.py` | `POST /api/auth/consent`, `GET /api/auth/consent-status` 엔드포인트 추가 |
| `user.py` | `privacy_consented`, `privacy_consented_at`, `privacy_consent_version` 필드 추가 |
| `config.py` | `PRIVACY_POLICY_VERSION` 설정 추가 |
| `ConsentDialog.tsx` (신규) | 개인정보 수집 동의 다이얼로그 (AlertDialog 기반) |
| `App.tsx` | ConsentDialog 통합 (로그인 후 표시) |

**다국어 지원 (i18n):**

| 파일 | 변경 |
|------|------|
| `i18n/index.ts` (신규) | i18next + react-i18next 설정 (localStorage 언어 저장) |
| `i18n/ko.json` (신규) | 한국어 번역 리소스 |
| `i18n/en.json` (신규) | 영어 번역 리소스 |
| `LanguageSwitcher.tsx` (신규) | 한국어/영어 토글 버튼 (Globe 아이콘) |
| `Header.tsx` | LanguageSwitcher 통합 |
| `main.tsx` | `import './i18n'` 추가 |
| `package.json` | `i18next`, `react-i18next` 의존성 추가 |

**E2E 테스트 (Playwright):**

| 파일 | 변경 |
|------|------|
| `playwright.config.ts` (신규) | Playwright 설정 (Chromium, dev server 자동 시작) |
| `e2e/health.spec.ts` (신규) | 프론트엔드 로딩 + 백엔드 health API 테스트 |
| `e2e/auth.spec.ts` (신규) | 회원가입/로그인 흐름 테스트 |
| `e2e/navigation.spec.ts` (신규) | 사이드바 네비게이션 + 접근성 테스트 |
| `package.json` | `@playwright/test` 추가, `test:e2e` 스크립트 추가 |

**사이드바 + 라우팅:**

| 파일 | 변경 |
|------|------|
| `Sidebar.tsx` | "리포트" 네비게이션 항목 추가 (FileText 아이콘) |
| `MainLayout.tsx` | `reports` activeView 라우트 + ReportView 연결 |

### Phase 21: 발표 시연 품질 개선 (완료)

**목표**: 데모 메트릭 표시 수정 + 낙상 유형별 차등 알림 + TTS 음성 알림 + 테스트 보강

**A. 데모 실시간 메트릭 수정:**

| 파일 | 변경 |
|------|------|
| `connection_manager.py` | `_last_metrics` 캐시 + WebSocket 신규 연결 시 최신 메트릭 즉시 전송 |
| `monitoring_orchestrator.py` | 파이프라인 오류 시에도 기본 메트릭(fps, person_count=0) 브로드캐스트 |

**B. 낙상 유형별 차등 알림:**

| 감지 결과 | 기존 동작 | 변경 후 |
|-----------|-----------|---------|
| pre_impact (전조) | MONITORING → "safe" | MONITORING → **"warning"** |
| 실제 낙상 (front/back/side_fall) | confidence < 0.8이면 MONITORING | **즉시 DANGER** (confidence 무관, WARNING 건너뜀) |
| 전조/고확신 지속 5초 | WARNING → DANGER | WARNING → DANGER (fall_duration 기반) |

| 파일 | 변경 |
|------|------|
| `alert_manager.py` | `fall_type` 파라미터 추가, 실제 낙상 즉시 DANGER (WARNING 건너뜀), MONITORING → "warning" 매핑, fall_duration 기반 WARNING→DANGER 전환, 독립 if 블록으로 캐스케이딩 지원 |
| `monitoring_orchestrator.py` | `fall_type` 전달, `alert_update` 메시지에 fall_type 포함 |
| `useWebSocket.ts` | fall_type 기반 이벤트 로그 세분화 ("경고" vs "주의") |

**C. TTS 음성 알림:**

| 파일 | 변경 |
|------|------|
| `monitoring.ts` | `ttsEnabled` 설정 추가 |
| `useAlertSound.ts` | Web Speech API `speakAlert()` 함수 + 알림 레벨 변경 시 TTS 발화 (한국어) |
| `SettingsCard.tsx` | TTS 활성화 토글 UI |

**D. 테스트 보강 (174개 전체 통과):**

| 파일 | 변경 |
|------|------|
| `test_alert_manager.py` | 29개 테스트로 재작성 (fall_type 분기, 고확신 bypass, MONITORING→"warning" 매핑 등 5개 신규) |
| `test_fall_detector.py` | autouse fixture 2개 (`_disable_grace_period`, `_mock_posture_classifier`) |
| `test_posture_classifier.py` | shoulder_tilt_delta 프레임 수 수정 (3→5) |
| `test_multi_person_integration.py` (신규) | **17개 통합 테스트** (7개 클래스: 독립 상태 추적, 알림 진행, 추적기 안정성, 혼합 낙상 타입, 버퍼 정리, 동시 낙상, 쿨다운) |

**E. 성능 벤치마크:**

| 파일 | 변경 |
|------|------|
| `scripts/benchmark_pipeline.py` (신규) | 합성 + 전체 파이프라인 벤치마크 (FallDetector + AlertManager + PostureClassifier) |

벤치마크 결과 (합성 모드):
| 인원 수 | P50 | P95 | P99 |
|---------|-----|-----|-----|
| 1인 | 1.81ms | 2.19ms | 2.60ms |
| 3인 | 2.14ms | 2.71ms | 2.93ms |
| 5인 | 2.49ms | 3.07ms | 3.35ms |

**F. Safe-Zone 미연결 문제 확인:**

코드 분석 결과 Safe-Zone UI + CRUD는 완전히 동작하지만, 낙상 감지 파이프라인(`fall_detector.py`, `monitoring_orchestrator.py`)에서 zone 데이터를 전혀 참조하지 않음을 확인. zone 데이터는 DB에 저장만 되고 감지 시 활용되지 않는 상태.

---

### Phase 22: 보행도구 인식 + 착석 오탐 제거 (완료)

**목표**: YOLO 보행도구 감지 + MediaPipe 휴리스틱 하이브리드, 착석 ML 노이즈 스코어 억제

**A. 보행도구 인식 (Walking Aid Detection):**

| 파일 | 상태 | 변경 |
|------|------|------|
| `walking_aid_detector.py` (신규) | 신규 | WalkingAidDetector (YOLO) + MediaPipeWalkingAidHeuristic + WalkingAidStateTracker |
| `config.py` | 수정 | WALKING_AID_* 설정 6개 추가 (모델 경로, 신뢰도, 확립/분실 프레임, 매칭 거리, 휴리스틱) |
| `monitoring_orchestrator.py` | 수정 | 보행도구 YOLO 병렬 실행 + MediaPipe 휴리스틱 + 상태 추적 + 브로드캐스트 |
| `alert_manager.py` | 수정 | walking_aid_missing 알림 지원 |
| `test_walking_aid_detector.py` (신규) | 신규 | 보행도구 감지 단위 테스트 |

**보행도구 감지 파이프라인:**
```
Camera → YOLO (person detection) ─┬─ YOLO (walking aid detection) ─┐
                                   └─ MediaPipe (33 landmarks) ──────┤
                                                                      ↓
                                                  WalkingAidStateTracker
                                                  (person-aid 매칭, 확립/분실 판정)
                                                          ↓
                                                  AlertManager (aid_missing → "주의")
```

**3가지 감지 모드:**
- **YOLO 기반**: 학습된 ONNX 모델로 walker/cane/crutch/wheelchair 감지
- **MediaPipe 휴리스틱**: 양손 위치 + 어깨 너비 비교로 보행도구 사용 추정 (YOLO 보완)
- **Graceful degradation**: 모델 파일 없으면 휴리스틱만 동작, 서버 정상 기동

**B. 착석 ML 노이즈 스코어 억제:**

| 문제 | 원인 | 해결 |
|------|------|------|
| 착석자가 노란색/주황색 바운딩 박스 표시 (score=0.25~0.64) | ML 모델이 착석 자세를 back_fall로 오인 (0.5~0.99 출력) | 착석 + 조건 미충족 + 미감지 시 ML 기여분 제거 |

**수정 내용 (`fall_detector.py`):**
```python
# 착석 ML 노이즈 스코어 억제
if (posture == PostureType.SITTING
        and not seated_any_specific
        and not is_fall_detected
        and not state.is_fallen):
    score = rule_score * self._rule_weight
```

**개선 결과 (영상 분석):**

| 영상 | 대상 | 수정 전 score | 수정 후 score | 오탐 프레임 |
|------|------|--------------|--------------|------------|
| wheelchair_test | person_2 (착석) | 0.237~0.327 (YELLOW) | 0.000 (GREEN) | 91 → **0** |
| crutch_test | person_2 (착석) | 0.489~0.638 (ORANGE) | 0.000~0.150 (GREEN) | 90+ → **0** |
| crutch_test | person_3 (착석) | 0.279~0.530 (ORANGE) | 0.000~0.150 (GREEN) | 70+ → **0** |
| 실제 낙상 감지 | 모든 영상 | 정상 감지 | 정상 감지 유지 | 0 (변화 없음) |

**C. 디버그 프레임 분석 스크립트:**

| 파일 | 설명 |
|------|------|
| `scripts/debug_frame_capture.py` (신규) | 영상 프레임별 낙상 감지 분석 + 어노테이션 스크린샷 저장 + CSV 로그 |

- 매 15프레임 정기 캡처 + 낙상/score 급변 시 즉시 캡처
- CSV: frame, time, person_id, posture, score, rule_score, ml_score, conditions, visibility
- 바운딩 박스 + 랜드마크 + 보행도구 표시 어노테이션

---

### Phase 27: COCO 17점 키포인트 지원 + 낙상 감지 정확도 개선 (완료)

**목표**: COCO 17-keypoint → MediaPipe 33-point 어댑터 + 낙상 미탐/오탐 개선

**A. COCO 17점 키포인트 어댑터:**

| 파일 | 변경 |
|------|------|
| `keypoint_adapter.py` (신규) | KeypointAdapter 클래스 (COCO 17점 → MediaPipe 33점 변환, visibility 보존) |
| `multi_person_detector.py` | YOLO 키포인트 → KeypointAdapter 적용, MediaPipe 33점 포맷으로 통일 |
| `test_keypoint_adapter.py` (신규) | COCO-MediaPipe 변환 단위 테스트 (매핑, visibility, 에러 처리) |

**B. Quick Recovery Detection (빠른 회복 감지):**

| 파일 | 변경 |
|------|------|
| `fall_detector.py` | lying < 10프레임 + standing >= 5프레임 → 의도적 눕기로 판정, 낙상 미감지 |

**적용 시나리오:**
- 요가 동작 (누웠다가 빠르게 일어남)
- 운동 루틴 (버피, 푸시업 등)
- 바닥에서 물건 집기

**C. Multi-frame Accumulation Detection (다중 프레임 누적 감지):**

| 파일 | 변경 |
|------|------|
| `fall_detector.py` | 저가시성(0.3-0.5) 영상에서 lying 누적 30프레임 → 낙상 감지 (AIHub C1/C4/C8 카메라 대응) |

**적용 시나리오:**
- AIHub C1 카메라 (저조도, 가시성 0.35~0.45)
- AIHub C4 카메라 (측면 카메라, 부분 가림)
- AIHub C8 카메라 (천장 카메라, 어안 왜곡)

**D. Controlled Movement Post-Fall (낙상 후 제어된 움직임 감지):**

| 파일 | 변경 |
|------|------|
| `fall_detector.py` | lying 30프레임 누적 시 속도 분산 분석 (분산 < 0.02 → 낙상, 분산 >= 0.02 → 의도적 움직임) |

**적용 시나리오:**
- 낙상 후 구르기/탈출 시도 (분산 높음 → 미감지)
- 실제 낙상 후 정지 상태 (분산 낮음 → 감지)

**E. Trip Fall Boost (넘어지기 낙상 감지 개선):**

| 파일 | 변경 |
|------|------|
| `fall_detector.py` | Trip Fall 특수 조건 (급격한 무릎 굽힘 + 높이 하강 + 수평 속도) → 즉시 감지 |

**개선 결과:**

| 영상 | 기존 감지 | Phase 27 감지 | 개선폭 |
|------|----------|--------------|--------|
| FY_front_fall_trip.mp4 | 0프레임 (미탐) | 38프레임 | **+38 (NEW)** |
| N_normal_standing_03.mp4 | 65프레임 (오탐) | 14프레임 | **-51 (78% 감소)** |

**F. 전체 테스트 결과:**

| 항목 | 수치 |
|------|------|
| 단위 테스트 | **261개 통과** (Phase 22: 174개 → Phase 27: 261개, +87개) |
| 데모 영상 | **24개 100% Recall 유지** (낙상 영상 모두 감지) |
| 오탐 감소 | N_normal_standing_03.mp4 65 → 14프레임 (78% 감소) |
| 미탐 개선 | FY_front_fall_trip.mp4 0 → 38프레임 (NEW) |

**G. AIHub 카메라 대응:**

| 카메라 | 특징 | 개선 방법 |
|--------|------|----------|
| C1 | 저조도 (가시성 0.35~0.45) | Multi-frame Accumulation (30프레임 누적) |
| C4 | 측면 카메라 (부분 가림) | Multi-frame Accumulation (30프레임 누적) |
| C8 | 천장 카메라 (어안 왜곡) | Multi-frame Accumulation (30프레임 누적) |

---

### Phase 27 후반: GRU ML 통합 + 앙상블 최적화 (완료)

**목표**: GRU 모델 학습 + 앙상블 가중치 최적화 + 논문 비교 분석

**A. GRU 모델 학습:**

| 항목 | 값 |
|------|-----|
| 학습 데이터 | AIHub **665,574개 시퀀스** (30프레임 × 99특징) |
| 모델 아키텍처 | GRU (Gated Recurrent Unit) |
| 파일 | `backend/models/fall_classifier_gru.onnx` (1.87 MB) |
| 입력 | (1, 30, 99) float32, 이름: `keypoints_sequence` |
| 출력 | (1,) sigmoid binary 확률 |
| 성능 (단독) | Recall 84.3%, Precision 97.0%, Accuracy 95.8% |

**B. 앙상블 가중치 벤치마크 (9개 조합):**

| 구성 | Rule:ML | Recall | Precision | F1-Score |
|------|---------|--------|-----------|----------|
| rule_only | 100:0 | 66.7% | 72.7% | 69.6 |
| ensemble_50_50 | 50:50 | 83.3% | 90.9% | 87.0 |
| **ml_only (V1)** | **0:100** | **85.5%** | **94.0%** | **89.5** |

**핵심 발견**: 규칙 60-80% 구간은 간섭 효과로 오히려 성능 저하. **ML 100%가 최적**.

**C. Recall 개선 추이:**

| 단계 | 방법 | Recall | 개선폭 |
|------|------|--------|--------|
| 1 | 13조건 규칙 (5% 기준) | 44.4% | 베이스라인 |
| 2 | 13조건 규칙 (1프레임) | 66.7% | +22.3%p |
| 3 | GRU 15 epoch | 84.3% | +17.6%p |
| 4 | **ML 100% 앙상블 (V1)** | **85.5%** | +1.2%p |
| 5 | **V4 최종 (방안1+2, 224영상)** | **90.9%** | +5.4%p |
| 6 | **V4 확장 벤치마크 (424영상)** | **95.2%** | +4.3%p |

**총 개선**: 44.4% → 95.2% = **+50.8%p 향상**

**D. 논문 비교 분석:**

| 시스템 | Recall | Precision | F1 | GPU 필수 |
|--------|--------|-----------|-----|---------|
| **SENTIO (GRU V4)** | **95.2%** | **94.6%** | **94.9** | **X (CPU)** |
| Ye (YOLOv8+Pose) | 92%* | 미공개 | 미공개 | O |
| Pre-VFall (LSTM) | 89.3% | 94.5% | 91.8 | O |

*Ye 논문의 92%는 Accuracy로 Recall과 직접 비교 불가

**E. 설정 변경:**

| 파일 | 변경 |
|------|------|
| `config.py` | `FALL_RULE_WEIGHT=0.0`, `FALL_ML_WEIGHT=1.0` (ML 100%) |
| `fall_classifier.py` | GRU 모델 우선 로드, CUDA GPU 자동 감지 |

---

### V4 종합 벤치마크 결과 (2026-02-08 확정)

**테스트 규모**: 224개 영상 (AIHub 200개 + 데모 24개)

**V1~V4 버전 비교**:

| 버전 | 설명 | Recall | Precision | F1 | FP | FN |
|------|------|--------|-----------|------|-----|-----|
| V1 (베이스라인) | ML 100% 기본 | 85.5% | 94.0% | 89.5 | 9 | 24 |
| V2 (재학습 모델) | GRU 재학습 + 코드 Fix | 87.9% | 86.3% | 87.1 | 23 | 20 |
| V3 (v1 모델+Fix) | 원본 GRU + 코드 Fix | 85.5% | 96.6% | 90.7 | 5 | 24 |
| **V4 (최종)** | **방안1+2 적용** | **90.9%** | **96.2%** | **93.5** | **6** | **15** |

**V4 카테고리별 성능 (AIHub 200개)**:
- BY (후방 낙상): 48/50 (96%)
- FY (전방 낙상): 47/50 (94%)
- SY (측면 낙상): 43/50 (86%)
- N (정상): 44/50 정상 감지 (6 FP)

**V4 코드 개선 사항**:
- Fix 1: Standing FP Post-EMA 필터 (standing+angle>75°+rule<0.20+score<0.90 → 감지 취소)
- Fix 2: 연속 프레임 완화 (score>=0.70 + ml_raw>=0.60 → 1프레임 즉시)
- Fix 3: 착석 감지 완화 (0.85→0.75 임계값, score cap 면제 확대)
- 방안 1: 벤치마크 판정 기준 1프레임 (실제 운영과 동일)
- 방안 2: Standing FP 필터에 score<0.90 조건 추가 (ML 극고확신 시 필터 면제)

**GRU 재학습 실패 교훈**:
- V2 GRU 재학습(SY 오버샘플링+UP-Fall 데이터)은 검증셋 F1 93.2%였으나 실전 FP 폭증(9→23)
- 교훈: 검증셋 성능 ≠ 실전 성능. 실제 영상 벤치마크가 필수
- 원본 GRU 모델(`fall_classifier_gru.onnx`) 계속 사용, v2는 롤백됨

---

### Phase 28: 파이프라인 제어 + 이벤트 DB 기록 (완료)

**목표**: 개발/데모 모드 파이프라인 일시정지 + 이벤트 DB 저장 + 외장 웹캠 지원

**A. 파이프라인 제어 (개발/데모용):**

| 파일 | 변경 |
|------|------|
| `monitoring_orchestrator.py` | `_paused` 플래그 + `pause()`, `resume()`, `is_paused` 프로퍼티 추가 |
| `stream.py` | `POST /pipeline/pause`, `POST /pipeline/resume`, `GET /pipeline/status` API 엔드포인트 |
| `VideoFeed.tsx` | 시작/중지 버튼에 파이프라인 제어 API 호출 추가 |

**기능:**
- 프론트엔드 "중지" 버튼 → 백엔드 파이프라인 완전 일시정지
- CPU 리소스 절약 (YOLO/MediaPipe 추론 중단)
- 카메라 서비스 + 모니터링 오케스트레이터 동시 제어
- 24시간 운영 환경과 개발/데모 모드 분리

**B. 이벤트 DB 기록:**

| 파일 | 변경 |
|------|------|
| `event_recorder.py` (신규) | EventRecorder 클래스 — warning/danger 이벤트 DB 저장 |
| `main.py` | event_recorder 콜백 등록 (lifespan) |

**기능:**
- warning/danger 알림 발생 시 자동 DB 저장
- 통계 탭 + 리포트 탭 데이터 연동
- 감사 로깅과 별도의 이벤트 이력 관리

**C. 외장 웹캠 지원:**

| 파일 | 변경 |
|------|------|
| `.env` | `CAMERA_INDEX=1` (외장 웹캠 인덱스) |

**D. 포트 통일:**

| 항목 | 값 |
|------|------|
| 백엔드 | 8001 |
| Vite 프록시 | localhost:8001 |

---

### Phase 29: 알림 자동복구 + 다국어 UI 완성 + UX 개선 (완료)

**목표**: 알림 자동 리셋, 보행도구 알림 분리, Pre-impact 임계값 조정, Header 알림 확인 버튼, 다국어 UI 완성

**A. 알림 자동복구 (Alert Auto-Recovery):**

| 파일 | 변경 |
|------|------|
| `alert_manager.py` | WARNING → NORMAL 즉시 복구 (정상 포즈 감지 시), DANGER → NORMAL 5초 자동 리셋 (재낙상 감지 시 타이머 리셋) |
| `test_alert_manager.py` | 자동 복구 테스트 추가 |

**동작:**
- WARNING + 정상 포즈 → 즉시 NORMAL (회복 감지)
- DANGER + 정상 포즈 → 5초 대기 후 NORMAL (자동 리셋)
- 재낙상 감지 시 회복 타이머 리셋

**B. 보행도구 분실 알림 분리 (Info-Only):**

| 파일 | 변경 |
|------|------|
| `alert_manager.py` | 보행도구 분실 → 알림 레벨 변경 없음 (정보 배지만 표시) |
| `test_walking_aid_detector.py` | Info-only 동작 검증 테스트 |

**이유:** 알람 피로(Alarm Fatigue) 방지 — 보행도구 분실은 정보성 표시만, 낙상 알림과 분리

**C. Pre-impact 임계값 조정:**

| 파일 | 변경 |
|------|------|
| `config.py` | `FALL_PRE_IMPACT_THRESHOLD` 0.25 → 0.35 (오탐 감소) |

**D. Header 알림 확인 버튼:**

| 파일 | 변경 |
|------|------|
| `Header.tsx` | 벨 아이콘 onClick → `wsSendAcknowledge()` + `clearAlerts()` + 이벤트 로그 추가 |
| `monitoring.ts` | `wsSendAcknowledge` 콜백 + setter를 zustand 스토어에 추가 |
| `useWebSocket.ts` | `sendAcknowledge`를 zustand 스토어에 등록 (컴포넌트 간 공유) |

**기능:** Header 벨 버튼 클릭 → 즉시 알림 확인 + 비프음 중지 + WebSocket acknowledge 전송

**E. 다국어 UI 완성 (i18n):**

| 파일 | 변경 |
|------|------|
| `Header.tsx` | `useTranslation()` 적용 — 모든 텍스트 다국어 지원 |
| `Sidebar.tsx` | `i18nKey` 기반 네비게이션 항목 다국어 지원 |
| `MainLayout.tsx` | 뷰 제목 다국어 지원 |
| `ko.json` | `header`, `sidebar`, `views` 섹션 추가 |
| `en.json` | 영어 번역 매칭 |

**이전 상태:** LanguageSwitcher만 번역, Header/Sidebar/MainLayout은 하드코딩 한국어
**수정 후:** 전체 UI 한국어↔영어 전환 동작 확인

**F. 테스트 결과:**

| 항목 | 수치 |
|------|------|
| 단위 테스트 | **263개 통과** (Phase 28: 261개 → Phase 29: 263개, +2개) |
| TypeScript 타입 체크 | 통과 |
| 브라우저 테스트 | 한국어↔영어 전환 정상 동작 |

---

### Phase 30: AI 모델 관리 시스템 (완료)

**목표**: AI 모델 관리 UI 및 API, GRU 분류기 별도 표시, YOLO26 정보 안내, 문서 현행화

**A. AI 모델 관리 API:**

| 파일 | 변경 |
|------|------|
| `routes/models.py` | GET /api/models/ (모델 목록), POST /api/models/switch (모델 교체), POST /api/models/upload (파일 업로드) |
| `ModelManager.tsx` | 모델 목록 표시, 상세 정보(속도·정확도·설명), 활성 모델 교체 UI |

**B. 모델 설명 UI 개선:**

| 모델 | 설명 | 배지 |
|------|------|------|
| YOLO11 Nano | ⚡⚡⚡ 가장 빠름, CPU 환경 최적화 | 빠름 |
| YOLO11 Small | ⚡⚡ 빠름, 속도와 정확도 균형 | 추천 |
| GRU 분류기 | 항상 활성화, YOLO와 함께 사용, 오탐 감소 | 분류기 |

**C. GRU 분류기 별도 섹션:**

| 변경 | 이유 |
|------|------|
| YOLO 모델과 GRU 분류기를 별도 섹션으로 UI 분리 | 사용자 혼란 방지 (GRU는 교체 불가, 항상 활성) |
| "낙상 분류 시스템 (항상 활성화)" 섹션 신규 | YOLO 포즈 감지와 낙상 분류를 명확히 구분 |

**D. YOLO26 정보 안내:**

| 내용 | 설명 |
|------|------|
| YOLO26 버전 출시 | 2026년 1월 출시, CPU 43% 성능 향상, NMS-Free 아키텍처 |
| 안정성 이슈 | 커뮤니티 검증 진행 중, 프로덕션 환경 적용 대기 |
| 향후 계획 | 안정성 확인 후 업그레이드 예정 |

**E. 문서 현행화:**

| 파일 | 변경 |
|------|------|
| `docs/02_technical/ARCHITECTURE.md` | AI 모델 관리 API + ModelManager 컴포넌트 추가 |
| `docs/02_technical/API.md` | Models API 섹션 추가 (3개 엔드포인트 문서화) |
| `docs/05_progress/TODO.md` | Phase 30 완료 마일스톤 + 성과 섹션 추가 |
| `docs/05_progress/PROGRESS.md` | Phase 30 상세 섹션 추가 |

**F. 코드 정리:**

| 작업 | 설명 |
|------|------|
| `process_logo.py` 삭제 | 불필요한 임시 로고 처리 스크립트 제거 |
| `Sidebar.tsx` lint 수정 | 미사용 Separator import 제거 |
| TypeScript 컴파일 | **에러 0개** 확인 완료 |

---


### Phase 20: 5-Class ML 학습 파이프라인 (실험 완료, 미채택)

**목표**: 4-Class → 5-Class 확장 (pre_impact 전조 감지 추가) + Pre-VFall + AIHub 대규모 학습

**참고**: 이 Phase는 실험적으로 진행되었으나, 최종적으로 GRU Binary 분류 모델이 채택되었습니다. 5클래스 분류는 프로덕션에 배포되지 않았습니다.

**5클래스 분류 체계:**

| 클래스 | ID | 설명 |
|--------|-----|------|
| Normal | 0 | 정상 상태 |
| Front Fall | 1 | 전면 낙상 |
| Back Fall | 2 | 후면 낙상 |
| Side Fall | 3 | 측면 낙상 |
| Pre-impact | 4 | 낙상 전조 (실험적) |

**Pre-VFall 데이터셋 추출 (완료):**

| 항목 | 상태 |
|------|------|
| 소스 | Pre-VFall 6개 시나리오 x 18 actors = 286 폴더 (22,504 이미지) |
| 추출 방법 | MediaPipe IMAGE 모드 (33-point 랜드마크) |
| 시퀀스 | **3,659개** (30프레임 윈도우, stride=15) |
| 클래스 분포 | normal=2,145 / front_fall=143 / side_fall=38 / pre_impact=1,333 |
| 성공/실패 | 244 성공 / 42 실패 (MediaPipe 포즈 미감지) |
| 에지 패딩 | 30프레임 미만 클립 → 에지 패딩 적용 (min_frames=10) |
| 산출물 | `D:/PreVFall_Data/landmarks/prevfall_landmarks.npz` (18.0 MB) |

**AIHub 전체 데이터셋 추출 (일부 완료):**

| 항목 | 상태 |
|------|------|
| 소스 | AIHub 낙상사고 위험동작 영상 18,128건 |
| 추출 방법 | MediaPipe VIDEO 모드 + 청크별 저장/재개 |
| 진행률 | ~8.6% (1,560/18,128), 실패 0건 |
| 증강 | jitter, horizontal_flip, scale, temporal_noise (원본당 2~3개 복사본) |
| 산출물 | `D:/AIHub_Fall_Data/landmarks/chunks/chunk_XXXX.npz` (청크별 저장) |

**신규 학습 스크립트:**

| 파일 | 설명 |
|------|------|
| `scripts/training/extract_prevfall_landmarks.py` (신규) | Pre-VFall 이미지 → MediaPipe 33점 추출 (IMAGE 모드, 프레임 갭 감지, 에지 패딩) |
| `scripts/training/train_v2.py` (신규) | 5클래스 학습 스크립트 (Pre-VFall + AIHub 병합, FocalLoss, 클래스 가중치 자동 계산) |
| `scripts/training/data_preprocessing.py` (신규) | OpenPose→MediaPipe 변환, 데이터셋 병합 유틸리티 |

**백엔드 5클래스 지원 업데이트:**

| 파일 | 변경 |
|------|------|
| `fall_classifier.py` | ONNX 출력 5개 지원, v2 모델 우선/v1 폴백, pre_impact 감지 (확률 30%+), `is_pre_impact` 필드 추가 |
| `fall_detector.py` | 쿨다운 2초→5초 (고령자 회복 고려), 체형 각도 계산 수직 기준 수정, 착석 낙상 점수 튜닝, ML override 로직 (rule_score≥0.8 시 ML 억제 방지) |
| `posture_classifier.py` | 체형 각도 계산 acos 기반 수정 (수직 기준: 0°=서있음, 90°=누워있음), 어깨 기울기 부호 포함 (편마비 환자 대응) |
| `config.py` | 쿨다운 5초, 전방 쏠림 임계값 0.15 (척추후만증 오탐 방지), 측면 기울기 임계값 0.12 (편마비 오탐 방지) |

**extract_landmarks.py 개선 (AIHub):**

| 항목 | 변경 |
|------|------|
| 청크별 저장 | 즉시 디스크 기록 → 중단 시 데이터 보존 |
| `--resume` 플래그 | 완료된 청크 건너뛰기 (재개 모드) |
| Shape 검증 | 시퀀스 (30, 99) 형태 검증 |
| 최종 병합 | 청크 파일들 → 통합 NPZ |

### Phase 17: 인프라 안정화 + 보안 (완료)

**Task A: JWT → HttpOnly 쿠키 전환**

| 파일 | 변경 |
|------|------|
| `config.py` | `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN`, `COOKIE_PATH` 설정 추가 |
| `core/auth.py` | 쿠키 우선 토큰 추출, `set_auth_cookies()`, `clear_auth_cookies()` 헬퍼 |
| `auth.py` 라우트 | login → Set-Cookie, refresh → 쿠키 읽기, **logout 엔드포인트 신규** |
| `ws.py` | `websocket.cookies.get("access_token")` 우선, query param 폴백 |
| `stream.py` | `request.cookies.get("access_token")` 우선, query param 폴백 (optional) |
| `test_api_auth.py` | Set-Cookie 헤더 검증으로 전면 재작성 (10개 테스트) |
| `frontend/lib/auth.ts` | localStorage 제거, `credentials: "include"` 기반 전면 재작성 |
| `App.tsx` | `checkAuth()` 서버 확인 방식으로 전환 |
| `LoginPage.tsx` | 토큰 저장 로직 제거 |
| `RegisterPage.tsx` | 토큰 저장 로직 제거 |
| `Header.tsx` | `logout()` API 호출 방식으로 전환 |
| `useWebSocket.ts` | `?token=` 쿼리 파라미터 제거 (쿠키 자동 전송) |
| `VideoFeed.tsx` | `withTokenParam()` 제거, 순수 URL 사용 |

**Task B: Alembic DB 마이그레이션**

| 파일 | 변경 |
|------|------|
| `requirements.txt` | `alembic>=1.13.0` 추가 |
| `alembic.ini` (신규) | Alembic 설정 (script_location = migrations) |
| `migrations/env.py` (신규) | async 엔진, `render_as_batch=True` (SQLite), `compare_type=True` |
| `migrations/script.py.mako` (신규) | 마이그레이션 템플릿 |

**Task C: GitHub Actions CI/CD**

| 파일 | 변경 |
|------|------|
| `.github/workflows/ci.yml` (신규) | push/PR → main 트리거, backend-test (pytest) + frontend-build (tsc + vite) |

---

## 추가 구현 사항 (Phase 9 외 보완)

### Docker End-to-End 수정

| 항목 | 수정 |
|------|------|
| nginx depends_on | frontend-build `service_completed_successfully` + backend `service_healthy` |
| backend healthcheck | `curl http://localhost:8000/health` (10s 간격, 5회 재시도) |
| JWT 기본값 | `.env.docker` 빈 문자열 → 자동 생성, `_INSECURE_DEFAULTS` 세트 확장 |
| 카메라 접근 | `/dev/video0` 디바이스 매핑 주석 추가 |

### 프론트엔드 회원가입 UI

| 파일 | 내용 |
|------|------|
| `RegisterPage.tsx` (신규) | 최초 사용자 등록 폼 + 자동 로그인 |
| `UserManagement.tsx` (신규) | admin 전용 사용자 목록 + 추가 폼 |
| `App.tsx` | `/api/auth/check-setup` 호출 → needs_setup 시 RegisterPage 표시 |
| `auth.py` 라우트 | `GET /check-setup`, `GET /users` 엔드포인트 추가 |

---

## 현재 동작 확인 완료 항목

| 기능 | 상태 | 비고 |
|------|------|------|
| 백엔드 서버 시작 | 동작 | uvicorn --reload |
| 프론트엔드 서버 시작 | 동작 | Vite HMR |
| 사용자 등록 | 동작 | 첫 사용자 자동 admin, 이후 관리자 인증 |
| 프론트엔드 회원가입 | 동작 | RegisterPage (needs_setup 체크) |
| 로그인 (프론트엔드) | 동작 | LoginPage -> HttpOnly 쿠키 (Set-Cookie) |
| WebSocket 실시간 연결 | 동작 | 쿠키 인증 + 자동 재연결 |
| 웹캠 캡처 | 동작 | OpenCV 전용 스레드 |
| MediaPipe 포즈 추정 | 동작 | ~55 FPS (PoseLandmarker) |
| YOLO11 다중인원 감지 | 동작 | N명 bbox + track_id (선택적) |
| MJPEG 비디오 스트림 | 동작 | 쿠키 인증 (query param 폴백) |
| WebRTC 스트림 | 동작 | WHEP via go2rtc (MJPEG 폴백) |
| 낙상 감지 | 동작 | 앙상블: ML 100% (GRU Binary 분류) — **V4 최종: Recall 95.2%, Precision 94.6%, F1 94.9 (424영상)** |
| 알림 상태 변화 | 동작 | safe -> warning -> danger (fall_type별 차등: 실제 낙상 즉시 warning, pre_impact 주의) |
| 대시보드 실시간 수치 | 동작 | FPS, confidence, head_y 등 |
| 통계 대시보드 | 동작 | 일별/시간대별 차트 + 요약 카드 |
| 이벤트 로그 | 동작 | DB 기록 + 프론트엔드 표시 |
| Safe-Zone 편집 | 동작 | Canvas 폴리곤 에디터 + **MJPEG 카메라 미리보기 오버레이** (Phase 34) |
| Safe-Zone 파이프라인 | 동작 | exclusion=스킵, safe=억제(실제 낙상 통과), danger=기본 (Phase 34) |
| 프라이버시 모드 | 동작 | skeleton / blur / full |
| 긴급 알림 모달 | 동작 | DangerAlertDialog |
| 알림음 | 동작 | Web Audio oscillator + **TTS 음성 알림** (한국어, Web Speech API) |
| 로그아웃 | 동작 | POST /api/auth/logout → 쿠키 삭제 + 로그인 화면 |
| 로그인 레이트 리밋 | 동작 | IP별 5회/60초 |
| 토큰 자동 갱신 | 동작 | HttpOnly 쿠키 기반 refresh (7일 만료) |
| 감사 로그 | 동작 | INSERT-only audit trail |
| FHIR 연동 | 동작 | FHIR_BASE_URL 설정 시 자동 연결 + danger 이벤트 콜백 |
| PDF 리포트 | 동작 | reportlab 설치 시 활성화, 수동/자동 생성 |
| 리포트 스케줄러 | 동작 | 일간/주간 자동 생성 (REPORT_SCHEDULE_DAILY/WEEKLY) |
| CSV/Excel 내보내기 | 동작 | /api/events/export (csv/xlsx) |
| 개인정보 동의 | 동작 | ConsentDialog + consent API |
| 다국어 (i18n) | 동작 | 한국어/영어 전환 (LanguageSwitcher) — **276개 번역 키 전체 완성** (Phase 31) |
| 얼굴 블러 | 구현 | FACE_BLUR_ENABLED 설정 시 활성화 |
| E2E 테스트 | 구현 | Playwright (health/auth/navigation) |
| 알림 자동복구 | 동작 | WARNING 즉시 복구 + DANGER 5초 자동 리셋 (Phase 29) |
| Header 알림 확인 | 동작 | 벨 버튼 클릭 → 즉시 acknowledge + 비프음 중지 (Phase 29) |
| 다국어 UI | 동작 | **전체 20+ 컴포넌트** 한국어↔영어 전환 완성 (Phase 29→Phase 31 완료) |
| 테스트 | 동작 | **267개** (단위 + API 통합 + 다중인원 통합 17개 + 보행도구 감지 + 앙상블 프로필 19개) — 전체 통과 |
| i18n 전체 완성 | 동작 | 276개 번역 키 (ko/en), 20+ 컴포넌트 한/영 전환 완성 (Phase 31) |
| UI/UX 폴리싱 | 동작 | 비밀번호 토글, 로딩 스피너, 반응형 레이아웃, 사이드바 상태 영속화 (Phase 31) |
| go2rtc 내부 인증 | 동작 | INTERNAL_STREAM_KEY 기반 |
| apiCall 자동 갱신 | 동작 | 401 시 쿠키 기반 자동 refresh + 재시도 |
| CI/CD 파이프라인 | 구현 | GitHub Actions (pytest + tsc + vite build) |
| Alembic 마이그레이션 | 구현 | async 엔진 + SQLite batch mode |
| SafeZone 에디터 연결 | 동작 | 사이드바 '카메라' 뷰 |
| WebRTC 모드 토글 | 동작 | VideoFeed MJPEG/WebRTC 전환 |
| 푸시 알림 UI | 동작 | SettingsCard 토글 |
| IoT Webhook 서비스 | 구현 | IOT_WEBHOOK_URL 설정 시 경광등 등 디바이스 연동 |
| 오탐지 보고 관리 | 동작 | CRUD + 통계 요약 API + 현황 위젯 + 임계치 알림 (Phase 32) |
| 이벤트 루프 최적화 | 동작 | 전용 ML 스레드풀 + 15fps 제한 + 프레임 드롭 |
| 보행도구 인식 | 동작 | YOLO + MediaPipe 휴리스틱 하이브리드 (walker/cane/crutch/wheelchair) |
| 착석 오탐 억제 | 동작 | ML 노이즈 스코어 억제 (착석 + 미감지 → ML 기여분 제거) |
| 데모 영상 시연 | 동작 | wheelchair_test.mp4 + crutch_test.mp4 데모 영상 (DEMO_VIDEO_DIR) |
| 다중 카메라 플레이리스트 | 동작 | 카메라별 영상 순환 + 카메라별 독립 리셋 (Phase 36) |
| 카메라별 독립 리셋 | 동작 | reset_camera() — 해당 카메라만 GRU/상태/알림 초기화, 다른 카메라 보존 (Phase 36) |
| **ONNX CPU 자동 최적화** | **동작** | **GPU→.pt(CUDA), CPU→.onnx(2.7배 가속) 자동 선택, 정확도 동일 (Phase 37)** |
| COCO 17점 키포인트 지원 | 동작 | KeypointAdapter (COCO → MediaPipe 33점 변환) |
| Quick Recovery Detection | 동작 | lying < 10프레임 + standing >= 5프레임 → 의도적 눕기 판정 |
| Multi-frame Accumulation | 동작 | 저가시성(0.3-0.5) 30프레임 누적 감지 (AIHub C1/C4/C8) |
| Controlled Movement Post-Fall | 동작 | 속도 분산 분석 (분산 < 0.02 → 낙상, >= 0.02 → 의도적) |
| Trip Fall Boost | 동작 | 넘어지기 낙상 즉시 감지 (급격한 무릎 굽힘 + 높이 하강) |
| 파이프라인 제어 | 동작 | 개발/데모 모드 pause/resume API (`/api/stream/pipeline/*`), **카메라 독립 제어 (Phase 33)** |
| 이벤트 DB 기록 | 동작 | warning/danger 알림 자동 DB 저장 (EventRecorder) |
| 외장 웹캠 지원 | 동작 | CAMERA_INDEX 환경변수로 카메라 선택 |

### Phase 31: UI/UX 전체 폴리싱 + i18n 완성 (완료, 2026-02-09)

**목표**: 발표 시연 품질 확보, 모든 하드코딩 한국어 제거, 20+ 컴포넌트 i18n 처리

**i18n 신규 키 추가 (~60개)**:

| 섹션 | 키 수 | 주요 내용 |
|------|-------|----------|
| `auth.*` | 15개 | 로그인/회원가입 폼 전체 i18n |
| `dashboard.metrics.*` | 10개 | 실시간 측정값, 낙상 확률, 규칙/ML 점수 |
| `dashboard.safeZone.*` | 10개 | Safe-Zone 에디터 UI |
| `dashboard.dangerAlert.*` | 5개 | 위험 다이얼로그 |
| `dashboard.demo.*` | 8개 | 데모 카테고리, 알림 메시지 |
| `report.*` | 12개 | 리포트 생성/다운로드/내보내기 |
| `consent.*` | 12개 | 개인정보 동의서 |
| `common.*` | 2개 | 오프라인 메시지, 단위 |

**컴포넌트 수정 (20+ 파일)**:

| 파일 | 주요 변경 |
|------|----------|
| `LoginPage.tsx` | 하드코딩 credentials 제거, 7개 문자열 i18n, 비밀번호 토글, 로딩 스피너 |
| `RegisterPage.tsx` | 15개 문자열 i18n, 비밀번호 토글, 로딩 스피너 |
| `MetricsCard.tsx` | 8+ 문자열 i18n, Progress bar 애니메이션 |
| `StatusCard.tsx` | 2개 문자열 i18n |
| `VideoFeed.tsx` | 전체화면 i18n, MJPEG onError 핸들러 추가 |
| `EventLog.tsx` | 하드코딩 `"ko-KR"` → 동적 로케일 |
| `DangerAlertDialog.tsx` | 6개 문자열 i18n, 동적 로케일 |
| `ConsentDialog.tsx` | 12개 동의서 내용 i18n |
| `SafeZoneEditor.tsx` | 10개 문자열 i18n, ResizeObserver 반응형 캔버스 |
| `ReportView.tsx` | 10개 toast i18n, 로딩 스피너, 동적 로케일 |
| `DemoVideoCard.tsx` | 데모 이벤트 메시지 i18n |
| `ConnectionStatus.tsx` | 3개 문자열 i18n |
| `OfflineBanner.tsx` | 1개 문자열 i18n |
| `DashboardView.tsx` | `lg:` 브레이크포인트 추가 (1024px 반응형) |
| `MainLayout.tsx` | 사이드바 접힘 상태 localStorage 영속화 |
| `Header.tsx` | 시간 표시 동적 로케일 |
| `SettingsCard.tsx` | warningTime < dangerTime 슬라이더 상호 검증 |
| `Logo.tsx` (신규) | LoginPage/Header SVG 중복 제거 → 공유 컴포넌트 |

**브라우저 테스트 결과 (Playwright)**:

| 테스트 항목 | 결과 | 발견/수정 |
|------------|------|----------|
| 대시보드 한국어 | 통과 | 정상 |
| 대시보드 영어 전환 | 통과 | 정상 |
| 설정 페이지 한/영 | 수정 | `userManagement.*` 키 구조 오류 수정 (dashboard 중첩 → 최상위) |
| 리포트 페이지 영어 | 수정 | 하드코딩 "일" → `t("report.days")` 교체 |
| StatusCard 비활성 상태 | 수정 | `dashboard.video.cameraInactive` 키 누락 추가 |
| TypeScript 컴파일 | 통과 | `tsc --noEmit` 에러 0개 |

**성과 요약**: 276개 i18n 키 전체 정의, 20+ 컴포넌트 한/영 완벽 전환, TypeScript 0 에러

---

### Phase 32: 오탐지/미탐지 보고 관리 파이프라인 (완료, 2026-02-10)

**목표**: 오탐지/미탐지 보고 CRUD + 통계 API + 현황 요약 위젯 + 임계치 초과 알림

**A. 오탐지 보고 CRUD API:**

| 파일 | 변경 |
|------|------|
| `routes/false_reports.py` (신규) | POST/GET/DELETE /api/false-reports/ (생성/목록/삭제), GET /{id}/image (이미지 조회) |
| `models/false_report.py` (신규) | FalseReport 모델 (report_type, notes, image_path, event_id, uploaded_by, created_at) |
| `FalseReportManager.tsx` (신규) | 보고 입력 폼 + 목록 + 페이지네이션 + 이미지 미리보기 + 삭제 |

**B. 보고 통계 요약 API:**

| 파일 | 변경 |
|------|------|
| `routes/false_reports.py` | GET /api/false-reports/summary 엔드포인트 추가 (total, false_positive, false_negative, this_week, needs_attention) |
| `routes/false_reports.py` | POST 응답에 total_reports + alert 필드 추가 (10건 이상 시 경고 메시지) |

**C. 프론트엔드 통계 위젯:**

| 파일 | 변경 |
|------|------|
| `FalseReportManager.tsx` | 상단 요약 카드 3개 (총 보고/오탐지/미탐지) + 이번 주 건수 표시 |
| `FalseReportManager.tsx` | needs_attention=true 시 orange 강조 카드 + 모델 개선 검토 배너 |
| `FalseReportManager.tsx` | POST alert 응답 시 info 토스트 표시 (6초 duration) |

**D. 다국어 (i18n):**

| 파일 | 변경 |
|------|------|
| `ko.json` | `falseReport.summary.*` 5개 키 추가 (total, falsePositive, falseNegative, thisWeek, attentionBanner) |
| `en.json` | 영어 번역 매칭 |

**보고 관리 파이프라인 아키텍처:**
```
사용자 → 오탐지/미탐지 보고 제출 (이미지 첨부 가능)
  → DB 저장 (FalseReport 테이블)
    → 전체 건수 체크 (≥10건 시 alert 포함 응답)
  → 관리자 대시보드 → 통계 요약 카드 (총 보고/오탐지/미탐지)
    → needs_attention 배너 (모델 개선 검토 안내)
  → 향후: 수집 데이터 기반 GRU 재학습 파이프라인 연동
```

---

### Phase 33: 파이프라인 안정화 + 다중 카메라 격리 (완료, 2026-02-11)

**목표**: 모니터링 파이프라인 프리즈 치명적 버그 수정, 다중 카메라 독립 제어, 불필요 파일 정리

**A. 파이프라인 프리즈 버그 수정 (Critical):**

| 파일 | 변경 |
|------|------|
| `monitoring_orchestrator.py` | `from app.config import settings` 모듈 레벨 import 추가 (기존: 내부 함수에서만 local import) |
| `monitoring_orchestrator.py` | `_process_yolo_pipeline()` 내 중복 local import 제거 |

**근본 원인:**
- `run_loop()` (line 738)에서 `settings.AI_PROCESS_INTERVAL` 참조
- `settings`가 모듈 레벨에 import되지 않아 **매 루프 NameError 발생**
- outer try/except에 잡혀 1초 sleep → 재시도 → 동일 에러 = **파이프라인 무한 프리즈**
- 서버 시작은 되지만 AI 처리가 전혀 동작하지 않는 증상

**B. 다중 카메라 독립 제어 (파이프라인/카메라 분리):**

| 파일 | 변경 |
|------|------|
| `stream.py` | `pause_pipeline`에서 `camera_service.stop()` 호출 제거 |
| `stream.py` | `resume_pipeline`에서 `camera_service.start()` 호출 제거 |
| `VideoFeed.tsx` | 개별 카메라 중지 시 `/api/stream/pipeline/pause` 호출 제거 |

**이유:**
- 다중 카메라 환경에서 cam0 중지 시 cam1도 중지되는 문제
- 파이프라인 제어(AI 처리 일시정지)와 카메라 제어(영상 캡처 중단)를 분리
- 개별 카메라 start/stop은 `/api/cameras/{id}/start|stop`으로 독립 관리

**C. TypeScript 수정:**

| 파일 | 변경 |
|------|------|
| `DashboardView.tsx` | `cameras[0].id` → `cameras[0]?.id ?? ""` (optional chaining) |

**D. 불필요 파일 정리:**

| 파일 | 처리 |
|------|------|
| `backend/verify_login.py` | 삭제 (하드코딩된 비밀번호 포함 디버그 스크립트) |
| `Care-guard sample.png` | 삭제 (불필요 샘플 이미지) |
| `dashboard-test.png`, `dashboard-final-test.png` | 삭제 (Playwright 테스트 스크린샷) |
| `frontend/playwright-report/` | 삭제 (테스트 리포트 아티팩트) |
| `frontend/test-results/` | 삭제 (테스트 결과 아티팩트) |
| `.gitignore` | 테스트 스크린샷 패턴 추가 |

**E. 브라우저 검증 결과 (Playwright):**

| 항목 | 결과 |
|------|------|
| YOLO + GPU 감지 | NVIDIA RTX 4050, ~27 FPS |
| 2대 카메라 동시 처리 | cam0 + cam1 정상 동작 |
| 낙상 감지 | ML 99%, angle 8° → DANGER 알림 정상 |
| 개별 카메라 중지/시작 | 다른 카메라에 영향 없음 |
| 전역 시작/중지 | 모든 카메라 동시 제어 정상 |
| 이벤트 로그 | 낙상 이벤트 기록 정상 |

---

### Phase 34: Safe-Zone 파이프라인 연동 (완료, 2026-02-11)

**목표**: DB에 저장된 Safe-Zone을 실제 낙상 감지 파이프라인에 연동, 카메라 미리보기 오버레이

**A. ZoneChecker 서비스 (신규: `zone_checker.py`):**

| 기능 | 설명 |
|------|------|
| Ray-casting | point-in-polygon 알고리즘으로 인물이 zone 내부인지 판별 (O(n)) |
| 기준점 | bbox 하단 중앙 (발 위치): `px=(x1+x2)/2, py=y2` |
| Zone 우선순위 | exclusion(3) > danger(2) > safe(1) — 겹치면 높은 우선순위 |
| 30초 TTL 캐시 | camera_id별 zone 리스트 캐싱, threading.Lock 스레드 안전 |
| DB 실패 방어 | DB 오류 시 빈 리스트 캐싱 (매 프레임 재시도 방지) |
| 캐시 무효화 | CRUD API(POST/PUT/DELETE) 시 자동 캐시 클리어 |

**B. 감지 파이프라인 연동 (`monitoring_orchestrator.py`):**

| Zone 타입 | 동작 |
|-----------|------|
| `exclusion` | 해당 인원 감지 완전 스킵 (`continue`) |
| `safe` | 알림 억제 (`is_fallen=False`), **단 실제 낙상(front/back/side_fall)은 통과** |
| `danger` | 기본 동작 (통과) |
| `None` | zone 미설정 → 기본 동작 |

**C. SafeZoneEditor 카메라 미리보기 (`SafeZoneEditor.tsx`):**

| 기능 | 설명 |
|------|------|
| MJPEG 오버레이 | 카메라 활성 시 실시간 영상 위에 zone 폴리곤 편집 |
| LIVE 뱃지 | 스트림 로드 시 좌상단 LIVE 표시 |
| 카메라 비활성 안내 | `VideoOff` 아이콘 + 안내 메시지 |
| streamKey 리마운트 | 카메라 on/off 시 `<img>` 강제 재연결 |

**D. 테스트 결과:**

| 항목 | 수치 |
|------|------|
| 신규 테스트 | **14개** (point-in-polygon 6개, zone 우선순위 4개, bbox 기준점 2개, 캐시 무효화 2개) |
| 단위 테스트 | **281개 통과** (267 + 14개 추가) |

---

### Phase 35: 다중공간(Multi-Room) 시스템 (완료, 2026-02-12)

**목표**: 카메라를 공간(복도, 대기실 등)별로 배정하고 공간별 독립 모니터링/알림/통계 지원

**A. DB 모델 + 마이그레이션:**

| 항목 | 설명 |
|------|------|
| `Room` 모델 | id, name, description, is_active, created_at |
| `RoomCameraMapping` 모델 | room_id(FK) + camera_id(str) — 런타임 카메라와 공간 연결 |
| `Event.room_id` | nullable int 컬럼 추가 (이벤트에 공간 자동 매핑) |
| Alembic 마이그레이션 | `add_rooms` 리비전 (SQLite batch mode 호환) |

**B. 백엔드 API (`/api/rooms`):**

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/rooms` | 공간 목록 (카메라 수 포함) |
| `POST /api/rooms` | 공간 생성 (admin) |
| `PATCH /api/rooms/{id}` | 공간 수정 (admin) |
| `DELETE /api/rooms/{id}` | 공간 삭제 + 매핑 제거 |
| `GET /api/rooms/{id}/cameras` | 해당 공간 카메라 목록 |
| `PUT /api/rooms/{id}/cameras` | 카메라 배정 (전체 교체) |

**C. 기존 API 공간 필터링 확장:**

| API | 추가 파라미터 |
|-----|-------------|
| `GET /api/events` | `room_id` — 해당 공간 카메라의 이벤트만 반환 |
| `GET /api/events/export` | `room_id` — 공간별 내보내기 |
| `GET /api/stats/*` | `room_id` — 일별/시간별/요약 통계 공간 필터 |
| `GET /api/cameras` | `room_id` — 해당 공간 카메라만 반환 |
| `POST /api/reports/generate` | `room_id` — 공간별 리포트 생성 |
| `GET /api/reports/export` | `room_id` — 공간별 리포트 내보내기 |

**D. 프론트엔드 변경:**

| 파일 | 변경 |
|------|------|
| `monitoring.ts` | `rooms`, `selectedRoomId`, `roomCameraIds`, `perCameraFps` 상태 추가 |
| `useRooms.ts` (신규) | `GET /api/rooms` 호출 → store에 rooms 세팅 |
| `RoomSelector.tsx` (신규) | 사이드바 상단 공간 드롭다운 (shadcn Select) |
| `Sidebar.tsx` | RoomSelector 삽입 |
| `DashboardView.tsx` | 공간 선택 시 roomCameraIds 세팅 + 카메라 필터 |
| `MetricsCard.tsx` | roomCameraIds 기반 personMetrics/FPS 필터링 |
| `StatusCard.tsx` | roomCameraIds 기반 dangerPerson/인원수 필터링 |
| `EventLog.tsx` | roomCameraIds 기반 이벤트 필터링 |
| `StatsView.tsx` | `room_id` 쿼리 파라미터 추가 |
| `ReportView.tsx` | `room_id` 쿼리 파라미터 추가 |
| `useWebSocket.ts` | per-camera FPS 저장, personMetrics camera-merge 패턴 |
| `ko.json` / `en.json` | `room.*` 번역 키 추가 |

**E. 핵심 수정 (alert_manager.py):**

- `person_id.rsplit("_person_", 1)[0]`으로 camera_id 추출
- 이벤트 저장 시 `camera_id → room_id` 자동 역매핑

**F. 변경하지 않은 파일 (AI 성능 영향 없음):**

- `fall_detector.py` — person_id 프리픽스로 이미 카메라별 격리
- `person_tracker.py`, `monitoring_orchestrator.py` — `_camera_states`로 이미 격리
- 모든 AI/ML 파일 — F1 94.9 성능 유지

**G. 테스트 결과:**

| 항목 | 수치 |
|------|------|
| 신규 테스트 | **13개** (Room CRUD 4개, Camera 매핑 3개, Events room_id 필터 3개, Stats room_id 필터 3개) |
| 단위 테스트 | **294개 통과** (281 + 13개 추가) |
| TypeScript | 0 에러 |

---

### Phase 36: 다중 카메라 성능 최적화 (완료, 2026-02-12)

**목표**: Docker 다중 카메라 환경에서 감지율 개선 및 카메라 간 상태 오염 방지

**A. 카메라별 독립 리셋 (핵심 개선):**

| 파일 | 변경 |
|------|------|
| `fall_detector.py` | `reset_camera(camera_id)` 추가 — person_id 프리픽스 기반 해당 카메라만 상태 초기화 |
| `fall_classifier.py` | `reset_camera(camera_id)` 추가 — 해당 카메라 GRU 버퍼만 초기화 |
| `alert_manager.py` | `reset_camera(camera_id)` 추가 — 해당 카메라 알림 상태만 초기화 + 전역 상태 재계산 |
| `camera_service.py` | 플레이리스트 전환 시 `reset_all()` → `reset_camera(camera_id)` 변경 |

**근본 원인:**
- 기존: 어떤 카메라의 영상이 전환될 때 `reset_all()`이 모든 카메라의 GRU 버퍼를 초기화
- GRU는 30프레임(~21초 at 1.4fps) 워밍업이 필요한데, 다른 카메라의 버퍼까지 삭제됨
- 3대 카메라 환경에서 각 카메라가 서로의 워밍업을 반복적으로 파괴

**B. 성능 비교 테스트 결과 (2 카메라 vs 3 카메라):**

| 지표 | 2 카메라 | 3 카메라 |
|------|---------|---------|
| FPS/카메라 | 2.0 | 1.4~1.7 |
| YOLO 평균 지연 | 127ms | 157ms |
| 감지율 | 75% | 85.7% |
| False Positive | 8.3% (1건) | 0% |

**C. 테스트 및 분석 스크립트:**

| 파일 | 설명 |
|------|------|
| `scripts/camera_comparison_test.py` (신규) | Docker 로그 파싱 및 다중 카메라 성능 분석 스크립트 |

**D. 시도 후 롤백한 방안:**

| 방안 | 결과 | 롤백 사유 |
|------|------|----------|
| GRU 버퍼 캐싱 (영상 전환 시 이전 버퍼 보존) | FP 0% → 17.6% | 이전 낙상 영상의 패턴이 정상 영상 판정을 오염 |
| Grace period 감소 (캐시 있을 때 2프레임) | 캐싱 의존 | 캐싱 제거 시 함께 롤백 |

**교훈:** GRU 30프레임 워밍업은 근본적 제약. 캐싱으로 우회 시 상태 오염 발생. 카메라별 독립 리셋이 최적 해법.

---

### V4 확장 벤치마크 확정 (424개 영상, 2026-02-09)

V4 코드를 424개 영상(BY 100, FY 100, SY 100, N 100, 데모 24개)으로 확장 검증:

| 지표 | 224개 영상 (구) | **424개 영상 (최종)** |
|------|----------------|---------------------|
| **Recall** | 90.9% | **95.2%** |
| **Precision** | 96.2% | **94.6%** |
| **F1-Score** | 93.5 | **94.9** |
| FP | 6건 | 17건 |
| FN | 15건 | 15건 |

**카테고리별 (424개 영상)**:
| 카테고리 | 감지/전체 | Recall |
|---------|----------|--------|
| BY (후방 낙상) | 99/100 | **99%** |
| FY (전방 낙상) | 97/100 | **97%** |
| SY (측면 낙상) | 91/100 | **91%** |
| N (정상) | 83/100 | 83% (17 FP) |

- V5(5개 파라미터 변경), V5.1(3개 파라미터 변경)을 시도했으나, 두 버전 모두 F1 94.8로 V4(F1 94.9) 대비 성능 개선이 없어 **안정화된 V4를 최종 버전으로 확정**
- **AI 성능 튜닝 종료, 서비스 완성에 집중**

---

## 기술 부채

| 항목 | 심각도 | 설명 |
|------|--------|------|
| ~~JWT in URL query params~~ | ~~중간~~ | **해결됨** (Phase 17에서 HttpOnly 쿠키 전환 완료, query param은 폴백으로 유지) |
| SQLite 단일 파일 | 낮음 | MVP에서는 충분, 운영 시 PostgreSQL 마이그레이션 필요 |
| ~~ONNX 모델 미포함~~ | ~~낮음~~ | **해결됨** (Phase 16에서 AIHub 데이터로 학습 완료, `backend/models/fall_classifier_gru.onnx` 1.87MB 배포) |
| ~~E2E 테스트 없음~~ | ~~중간~~ | **해결됨** (Phase 19에서 Playwright 도입, 3개 테스트 파일) |
| ~~얼굴 블러 미구현~~ | ~~낮음~~ | **해결됨** (Phase 19에서 Haar Cascade + Gaussian blur 구현) |
| ~~Alembic 미구현~~ | ~~중간~~ | **해결됨** (Phase 17에서 Alembic async 환경 구축, SQLite batch mode 지원) |
| Redis 미도입 | 낮음 | 레이트 리밋/메시지 버퍼가 in-memory, 수평 확장 제한 |

---

## 기술 스택 요약

| 영역 | 기술 | 버전 |
|------|------|------|
| Backend | FastAPI + Uvicorn + Gunicorn | 0.104+ |
| AI/CV (포즈) | MediaPipe PoseLandmarker Tasks API | 0.10.30+ |
| AI/CV (감지) | YOLO11s-pose + ByteTrack | 8.3+ |
| AI/ML | ONNX Runtime (GRU 분류기, Binary, **V4 최종 배포됨**) | **Recall 95.2%, Precision 94.6%, F1 94.9** |
| 영상 | OpenCV (headless) | 4.8+ |
| 스트리밍 | MJPEG + WebRTC (go2rtc WHEP) | - |
| Frontend | React + TypeScript + Vite | 18 / 6 |
| 상태 관리 | Zustand | 4.5+ |
| 차트 | Recharts | 2.15+ |
| CSS | Tailwind CSS v4 + oklch | 4.0 |
| UI | Radix UI + Shadcn/ui + Lucide Icons | - |
| DB | SQLite (aiosqlite) / PostgreSQL (asyncpg) | - |
| 인증 | HttpOnly 쿠키 + JWT (python-jose) + bcrypt | 8h + 7d |
| DB 마이그레이션 | Alembic (async, SQLite batch mode) | 1.13+ |
| CI/CD | GitHub Actions (pytest + tsc + vite build) | - |
| 실시간 | WebSocket (FastAPI 내장) | - |
| 푸시 | Web Push (pywebpush + VAPID) | 선택적 |
| PWA | vite-plugin-pwa + Service Worker | - |
| EMR | HL7 FHIR R4 (httpx) | 선택적 |
| PDF | reportlab | 선택적 |
| i18n | react-i18next + i18next | ko/en |
| E2E 테스트 | Playwright (Chromium) | - |
| Excel | openpyxl | 선택적 |
| 컨테이너 | Docker Compose + Nginx + go2rtc + certbot | - |
| 폰트 | Pretendard + Noto Sans KR | Variable |

## 문서 구조

| 문서 | 설명 |
|------|------|
| [README.md](../README.md) | 프로젝트 소개 및 빠른 시작 가이드 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 시스템 아키텍처 및 설계 결정 |
| [API.md](./API.md) | REST API / WebSocket 엔드포인트 레퍼런스 |
| [PROGRESS.md](./PROGRESS.md) | 이 문서 - 진행 상황 보고서 |
| [ENHANCEMENT_PLAN.md](./ENHANCEMENT_PLAN.md) | Phase 9-15 확장 계획 (최신 기술 동향 반영) |
| [TRAINING_GUIDE.md](./TRAINING_GUIDE.md) | ML 학습 파이프라인 가이드 (추출/학습/재개 방법) |
| [NOTIFICATION_SYSTEM_REVIEW.md](./NOTIFICATION_SYSTEM_REVIEW.md) | 알림 시스템 설계 검토 (Phase 11 참고용) |
| [CARE-GUARD_디자인_레퍼런스.md](./CARE-GUARD_디자인_레퍼런스.md) | UI/UX 디자인 가이드 및 구현 현황 |

> 아카이브 문서는 `docs/archive/` 폴더를 참조하세요.

---

### Phase 37: ONNX CPU 자동 최적화 (완료, 2026-02-13)

**목표**: GPU 없는 환경에서도 실시간 처리 가능하도록 YOLO 모델 형식 자동 선택 + GRU 세션 최적화

**A. YOLO 모델 ONNX 변환 및 자동 선택:**

| 파일 | 변경 |
|------|------|
| `multi_person_detector.py` | `_resolve_model_path()` 추가 — GPU→`.pt`(CUDA+FP16), CPU→`.onnx`(onnxruntime) 자동 선택 |
| `models/yolo11s-pose.onnx` | yolo11s-pose.pt를 ONNX opset17로 변환 (38.0MB, 같은 가중치) |
| `models/yolo11n-pose.onnx` | yolo11n-pose.pt를 ONNX opset17로 변환 (11.2MB, 같은 가중치) |

**B. GRU ONNX 세션 최적화:**

| 파일 | 변경 |
|------|------|
| `fall_classifier.py` | SessionOptions 추가 — `ORT_ENABLE_ALL` 그래프 최적화 + CPU 코어 수 기반 스레드 자동 설정 |

**C. CPU 성능 벤치마크 (동일 모델 가중치, 정확도 영향 없음):**

| 형식 | yolo11s-pose CPU 평균 | 배수 |
|------|----------------------|------|
| `.pt` (PyTorch) | 113.9ms | 1x (기존) |
| **`.onnx` (ONNX Runtime)** | **42.5ms** | **2.7x 빠름** |

**핵심 원리:**
- ONNX는 같은 모델 가중치를 다른 실행 엔진(onnxruntime)으로 돌리는 것
- 그래프 최적화(operator fusion, constant folding 등)가 자동 적용
- **정확도 영향 제로** — 동일 입력에 동일 출력 보장
- GPU 환경에서는 기존과 동일하게 `.pt + CUDA + FP16` 사용

**자동 선택 로직:**
```
GPU 있는 PC  → yolo11s-pose.pt   [CUDA + FP16]   ← 기존과 동일
GPU 없는 PC  → yolo11s-pose.onnx [CPU optimized]  ← 2.7배 빨라짐
```

**테스트:** 기존 56개 테스트 전체 통과 (fall_detector 39개 + multi_person_integration 17개)

---

*이 문서는 프로젝트 진행에 따라 지속적으로 업데이트됩니다. (Phase 37 ONNX CPU 자동 최적화 완료: 2026-02-13)*
