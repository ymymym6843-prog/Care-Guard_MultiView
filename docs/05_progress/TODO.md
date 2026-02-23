# SENTIO TODO 목록

> 최종 업데이트: 2026-02-12
> 기준: V4 확장 벤치마크 확정 (424영상, F1 94.9) + Phase 36 다중 카메라 최적화 완료

---

## 완료된 주요 마일스톤

- [x] Phase 1-8: MVP 풀스택 (FastAPI + React + MediaPipe + 4조건 낙상 감지 + JWT + 테스트)
- [x] Phase 9: Docker + PWA + Web Push (VAPID)
- [x] Phase 10: YOLO11 다중 인원 추적 (ByteTrack)
- [x] Phase 11: WebRTC 스트리밍 (go2rtc WHEP)
- [x] Phase 12: HTTPS + Gunicorn 배포
- [x] Phase 13: 감사 로깅 + Refresh Token + 보안 강화
- [x] Phase 14: ONNX Transformer 분류기 + Safe-Zone
- [x] Phase 15: 통계 대시보드 + FHIR EMR 연동 + IoT Webhook
- [x] Phase 16: AIHub 낙상 데이터셋 ML 학습 (F1=0.8798, Acc=88.4%, ONNX 배포)
- [x] Phase 17: 인프라 안정화 + 보안 (HttpOnly 쿠키, Alembic, CI/CD)
- [x] Phase 18: ML 모델 고도화 (4클래스 분류, 데이터 증강, 앙상블 가중치, K-Fold CV, 벤치마크) + 코드리뷰 9건 수정
- [x] Phase 19: 리포팅 + 개인정보보호 + i18n + E2E 테스트
- [x] **Phase 20: 5클래스 ML 파이프라인 (완료)** — Pre-VFall 추출 완료, AIHub 추출 진행 중
- [x] **Phase 21: 발표 시연 품질 개선 (완료)** — 메트릭 수정, fall_type별 차등 알림, TTS 음성 알림, 174개 테스트, 벤치마크
- [x] **Phase 27: COCO 17점 키포인트 지원 + 낙상 감지 정확도 개선 (완료)** — Quick Recovery Detection, Multi-frame Accumulation, Controlled Movement Post-Fall, 261개 테스트 통과
- [x] **Phase 28: 파이프라인 제어 + 이벤트 DB 기록 (완료)** — 개발/데모 모드 pause/resume, EventRecorder DB 저장, 외장 웹캠 지원
- [x] **Phase 29: 알림 자동복구 + 다국어 UI 완성 (완료)** — WARNING/DANGER 자동 리셋, 보행도구 info-only, Header 알림 확인, 다국어 완성, 263개 테스트
- [x] **Phase 30: AI 모델 관리 시스템 (완료)** — 모델 목록/교체/업로드 API, 모델 설명 UI, GRU 분류기 별도 섹션, YOLO26 정보 안내
- [x] **Phase 31: UI/UX 전체 폴리싱 + i18n 완성 (완료)** — 276개 i18n 키, 20+ 컴포넌트 한/영 전환, Logo 공유 컴포넌트, 반응형/사이드바 영속화, 브라우저 테스트 5건 수정
- [x] **Phase 32: 오탐지/미탐지 보고 관리 파이프라인 (완료)** — CRUD API + 통계 요약 API + 현황 위젯 + 임계치 알림 + 이미지 첨부/미리보기
- [x] **Phase 33: 안정성 개선 + 다중 카메라 격리 (완료)** — 파이프라인 freeze 버그 수정, 다중 카메라 독립 AI 처리, 267개 테스트 전체 통과
- [x] **Phase 34: Safe-Zone 파이프라인 연동 (완료)** — ZoneChecker 서비스 (Ray-casting, 30초 캐시), 감지 파이프라인 연결 (exclusion/safe/danger), 카메라 미리보기 오버레이, 281개 테스트 전체 통과
- [x] **Phase 35: 다중공간(Multi-Room) 시스템 (완료)** — Room CRUD + 카메라 배정 + 공간별 필터링 (대시보드/통계/리포트/이벤트), 294개 테스트 전체 통과
- [x] **Phase 36: 다중 카메라 성능 최적화 (완료)** — 카메라별 독립 리셋 (reset_camera), per-camera YOLO ByteTrack 격리, 플레이리스트 모드 최적화, 2대 vs 3대 성능 비교 테스트

### Phase 33 안정성 개선 + 다중 카메라 격리 성과

- **파이프라인 freeze 수정**: `asyncio.to_thread()` 내부 네이밍 충돌로 인한 AI 파이프라인 정지 문제 해결
- **다중 카메라 독립 AI 처리**: 카메라별 독립 FallDetector/FallClassifier 인스턴스 할당, 상태 격리 보장
- **MonitoringOrchestrator 리팩토링**: 카메라별 독립적인 AI 파이프라인 관리, 카메라 추가/제거 시 자동 리소스 정리
- **WebSocket 연결 안정화**: 다중 카메라 환경에서 connection_manager 개선
- **테스트 현행화**: AlertManager 상태 머신 변경에 맞춰 26개 실패 테스트 수정, **267개 전체 통과**
- **TypeScript 에러 수정**: 프론트엔드 타입 에러 정리

### Phase 32 오탐지 보고 관리 파이프라인 성과

- **보고 CRUD API**: POST/GET/DELETE /api/false-reports/ + GET /{id}/image (이미지 조회)
- **통계 요약 API**: GET /api/false-reports/summary (총건수, 오탐/미탐 분류, 이번 주 건수, needs_attention 플래그)
- **임계치 알림**: 보고 10건 이상 시 POST 응답에 alert 메시지 포함 → info 토스트 표시
- **프론트엔드 위젯**: 요약 카드 3개 (총 보고/오탐지/미탐지) + needs_attention 시 orange 강조 배너
- **이미지 관리**: 보고 시 스크린샷 첨부 가능 + 목록에서 인라인 미리보기
- **다국어**: falseReport.summary.* 번역 키 5개 추가 (ko/en)

### V4 확장 벤치마크 확정 (2026-02-09)

SENTIO 낙상 감지 시스템 V4가 424개 영상으로 확장 검증 완료되었습니다.

**V4 확장 벤치마크 (424개 영상, 최종)**:
| 지표 | 값 |
|------|-----|
| **Recall** | **95.2%** |
| **Precision** | **94.6%** |
| **F1-Score** | **94.9** |
| FP (오탐) | 17건 |
| FN (미탐) | 15건 |

**카테고리별 성능 (424개 영상)**:
| 카테고리 | 감지율 | 감지/전체 |
|---------|--------|----------|
| BY (후방) | **99%** | 99/100 |
| FY (전방) | **97%** | 97/100 |
| SY (측면) | **91%** | 91/100 |
| N (정상) | 83% | 83/100 (17 FP) |

**참고**: 224개 영상 기준 Recall 90.9%, Precision 96.2%, F1 93.5

**사용 모델**: GRU ONNX (`fall_classifier_gru.onnx`, 1.9MB, Binary 분류)

### Phase 29 알림 자동복구 + 다국어 UI 성과

- **알림 자동복구**: WARNING 즉시 복구, DANGER 5초 자동 리셋 (재낙상 시 타이머 리셋)
- **보행도구 분리**: 보행도구 분실 → 정보 배지만 (알람 피로 방지)
- **Header 알림 확인**: 벨 버튼 클릭 → 즉시 acknowledge + 비프음 중지
- **다국어 UI 완성**: Header/Sidebar/MainLayout 전체 한국어↔영어 전환
- **테스트**: 263개 전체 통과

### Phase 30 AI 모델 관리 시스템 성과

- **AI 모델 관리 API**: GET /api/models/ (모델 목록), POST /api/models/switch (모델 교체), POST /api/models/upload (파일 업로드)
- **모델 설명 UI**: YOLO11 Small (⚡⚡ 기본값), YOLO11 Nano (⚡⚡⚡ 경량), GRU 분류기 (항상 활성화) 상세 정보
- **GRU 분류기 분리**: YOLO 포즈 감지 모델과 낙상 분류 시스템을 별도 섹션으로 UI 개선
- **YOLO26 정보 안내**: 최신 YOLO26 버전 출시 (CPU 43% 성능 향상, NMS-Free) + 안정성 검증 대기 중 메시지
- **문서 현행화**: ARCHITECTURE.md + API.md 업데이트, 불필요한 파일(process_logo.py) 정리
- **코드베이스 정리**: 미사용 import 제거, TypeScript 컴파일 에러 0개

### Phase 28 파이프라인 제어 성과

- **개발/데모 모드**: 프론트엔드 중지 버튼 → 백엔드 파이프라인 완전 일시정지
- **이벤트 DB 기록**: warning/danger 알림 자동 저장 → 통계/리포트 연동
- **외장 웹캠 지원**: CAMERA_INDEX 환경변수로 카메라 선택

### Phase 31 UI/UX 전체 폴리싱 성과

- **i18n 완성**: ~60개 신규 키 추가 (276개 전체), ko.json/en.json 동기화
- **20+ 컴포넌트 수정**: LoginPage, RegisterPage, MetricsCard, SafeZoneEditor, ReportView 등 전체 한/영 전환
- **UI 개선**: 비밀번호 토글(Eye/EyeOff), 로딩 스피너(Loader2), Progress bar 애니메이션
- **반응형**: DashboardView `lg:` 브레이크포인트, SafeZoneEditor ResizeObserver
- **공유 컴포넌트**: Logo.tsx (LoginPage/Header SVG 중복 제거)
- **사이드바 영속화**: localStorage 기반 접힘 상태 유지
- **슬라이더 검증**: warningTime < dangerTime 상호 제약
- **브라우저 테스트**: Playwright로 대시보드/리포트/설정 한/영 전환 검증, 5건 버그 발견 및 수정
- **TypeScript**: `tsc --noEmit` 에러 0개

### Phase 27 GRU ML 통합 + 앙상블 최적화 성과

- **GRU 모델 학습 완료**: AIHub 665,574개 샘플, 30프레임×99특징
- **V4 최종 성능**: Recall **95.2%**, Precision **94.6%**, F1-Score **94.9** (424개 영상 종합)
- **앙상블 벤치마크**: 9개 가중치 조합 테스트, **ML 100%** 최적 확인
- **Recall 개선 추이**: 44.4% → 66.7% → 84.3% → **95.2%** (+50.8%p, V4 최종 424영상)
- **FY_front_fall_trip.mp4 미탐 해결**: 0 → 38프레임 (낙상 감지 성공)
- **N_normal_standing_03.mp4 오탐 감소**: 65 → 14프레임 (정상 동작 오탐 78% 감소)

---

## 향후 확장 계획 (Future Work)

> V4 확정 이후 추가 개선을 위한 과제들입니다.

### 낙상 감지 정확도 고도화
- [ ] 잔여 15 FN 분석 (SY 9개 중 ml=0인 케이스 → GRU negative mining 재학습 필요)
- [ ] 잔여 17 FP 분석 및 개선 (424영상 기준)
- [ ] GRU 모델 재학습 (negative mining 전략)
- [ ] YOLO 트래커 개선 (1프레임 소실 FN 해결)
- [ ] ST-GCN 아키텍처 검토 (측면 낙상 개선)

### 시스템 기능 확장
- [x] Safe-Zone → 감지 파이프라인 연결 **(Phase 34 완료)**
- [ ] SMS 에스컬레이션 (Twilio API)
- [ ] 이메일 알림 발송
- [ ] Telegram Bot 모니터링
- [ ] 행동 패턴 분석 (장시간 미움직임, 비정상 보행)
- [ ] FHIR Bundle/Patient 리소스 매핑

### 인프라 확장
- [ ] Redis 기반 전역 레이트 리밋
- [ ] Redis 메시지 버퍼 (수평 확장)
- [ ] 실제 요양병원 파일럿 배포 (2~3곳 PoC)
- [ ] 24시간 연속 가동 안정성 테스트

### 성능 최적화
- [ ] ONNX INT8 양자화
- [ ] TensorRT GPU 최적화
- [ ] 엣지 디바이스 배포 (Jetson Nano)
- [ ] YOLO26 업그레이드 (안정성 검증 후)

### IoT 확장
- [ ] IoT 스마트 경광등 실물 연동
- [ ] Zigbee/BLE 게이트웨이
- [ ] 모바일 네이티브 앱 (React Native)

---

## 기술 부채

| 항목 | 심각도 | 상태 |
|------|--------|------|
| ~~JWT in URL query params~~ | ~~중간~~ | **해결** (Phase 17, HttpOnly 쿠키 전환 완료) |
| SQLite 단일 파일 (개발) | 낮음 | 부분 해결 — Docker에서 PostgreSQL 사용 중 |
| ~~ONNX 모델 미포함~~ | ~~낮음~~ | **해결** (Phase 16, 1,227KB ONNX 배포) |
| ~~E2E 테스트 없음~~ | ~~중간~~ | **해결** (Phase 19, Playwright + 3 테스트 파일) |
| ~~얼굴 블러 미구현~~ | ~~낮음~~ | **해결** (Phase 19, Haar Cascade + Gaussian blur) |
| ~~Alembic 미구현~~ | ~~중간~~ | **해결** (Phase 17, async 환경 구축) |
| Redis 미도입 | 낮음 | 미해결 — 수평 확장 시 필요 |

---

## ML 학습 파이프라인 참고

> 상세 가이드: [TRAINING_GUIDE.md](./TRAINING_GUIDE.md)

### 실행 방법 (5클래스 v2 학습)

```bash
# Step 1: AIHub 랜드마크 추출 (중단 시 --resume로 재개)
python scripts/training/extract_landmarks.py \
    --data-root D:/AIHub_Fall_Data \
    --output-dir D:/AIHub_Fall_Data/landmarks \
    --max-per-class 0 --chunk-size 500 --resume

# Step 2: Pre-VFall 랜드마크 추출 (이미 완료)
python scripts/training/extract_prevfall_landmarks.py \
    --data-root D:/PreVFall_Data/Pre-VFallp \
    --output-dir D:/PreVFall_Data/landmarks \
    --mode mediapipe --resume

# Step 3: 데이터셋 병합
python scripts/training/data_preprocessing.py \
    --source merge \
    --aihub-npz D:/AIHub_Fall_Data/landmarks/training_landmarks.npz \
    --prevfall-npz D:/PreVFall_Data/landmarks/prevfall_landmarks.npz \
    --output D:/merged_landmarks.npz

# Step 4: 5클래스 모델 학습 + ONNX 변환
python scripts/training/train_v2.py \
    --data D:/merged_landmarks.npz \
    --output backend/models/fall_classifier_v2.onnx \
    --num-classes 5 --epochs 30

# Step 5: 서버 재시작 → v2 모델 자동 로드 (5클래스 자동 감지)
```

### 현재 모델 상태

| 항목 | v1 (배포됨) | v2 (롤백됨) |
|------|------------|-------------|
| 분류 | GRU Binary (Fall/Normal), **V4 확정 모델** | 5클래스 (normal, front_fall, back_fall, side_fall, pre_impact) |
| 학습 데이터 | AIHub 665,574 샘플 (30프레임×99특징) | Pre-VFall 3,659 + AIHub 18,128건 전체 |
| 파일 | `fall_classifier_gru.onnx` (1.9 MB) | `fall_classifier_v2.onnx` (재학습 실패, 롤백) |
| F1 Score | **94.9** (424개 영상 종합) | 87.1 (FP 폭증으로 미사용) |

**참고**: v2 GRU 재학습(SY 오버샘플링+UP-Fall)은 FP 폭증(9→23)으로 롤백. v1 원본 GRU 사용.

### Phase 20 변경 사항

| 항목 | 변경 |
|------|------|
| 분류 | 4클래스 → 5클래스 (pre_impact 전조 감지 추가) |
| 데이터 | AIHub 단독 → Pre-VFall + AIHub 대규모 병합 |
| 추출 | 비디오 전용 → 이미지 + 비디오 (Pre-VFall IMAGE 모드) |
| 에지 패딩 | 30프레임 미만 클립 → 에지 패딩 복원 (min_frames=10) |
| 청크 저장 | 전체 메모리 → 청크별 저장 + `--resume` 재개 지원 |
| 백엔드 | v2 ONNX 우선 로드 / v1 폴백, pre_impact 확률 30%+ 감지 |

---

*이 문서는 프로젝트 진행에 따라 지속적으로 업데이트됩니다. (Phase 36 다중 카메라 최적화 완료: 2026-02-12)*
