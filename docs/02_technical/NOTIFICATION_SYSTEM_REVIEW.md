# SENTIO 알림 시스템 설계 검토 보고서

> **문서 상태**: 참고용 설계 문서 (Phase 9-15 전체 구현 완료).
> 현재 구현된 알림 시스템: WebSocket 실시간 알림 + Web Push (VAPID) + Refresh Token 자동 갱신 + 감사 로그.
> 이 문서는 SMS 에스컬레이션, Redis 메시지 버퍼 등 **미구현 향후 과제**의 설계 참고용으로 유지됩니다.
> 확장 로드맵은 [ENHANCEMENT_PLAN.md](./ENHANCEMENT_PLAN.md)를 참조하세요.

## 1. 개요

본 문서는 SENTIO 요양병원 낙상 감지 시스템의 다중 채널 알림 시스템을 의료 현장 관점에서 검토한 결과입니다.

**검토일**: 2026-01-30
**프로젝트**: SENTIO AI
**목적**: 요양병원 환경에서 10초 골든타임 내 의료진 알림 보장

---

## 2. 에스컬레이션 시간 기준 검토

### 현재 구현된 기준 (Phase 24 업데이트)
```
[실제 낙상 (front/back/side_fall)]
  즉시: DANGER 알림 (모든 채널) ← WARNING 단계 건너뜀

[전조/저확신]
  0~1.5초: MONITORING (내부 추적)
  1.5초+: WARNING 알림 (대시보드 + 알림음)
  5초+: DANGER 알림 (모든 채널)

[고확신 (confidence ≥ 0.8)]
  즉시: WARNING 알림
  5초+: DANGER 알림 (모든 채널)

30초+: 2차 알림 (관리자 호출, 미확인 시)
```

### 의료 현장 적절성 분석

#### ✅ 장점
1. **실제 낙상 즉시 대응**: AI가 front/back/side_fall로 분류 시 대기 없이 즉시 DANGER → 골든타임 10초 전부를 의료진 대응에 활용
2. **전조 감지 사전 경고**: pre_impact 전조 단계에서 미리 주의 알림 → 예방적 대응 가능
3. **오탐 방지**: 7단계 필터(앙상블 이중검증, grace frames, 가시성 체크 등)를 통과한 결과만 알림
4. **계층적 대응**: 낙상 유형별 차등 에스컬레이션으로 상황에 맞는 대응

#### ⚠️ 기존 우려사항 해결 현황

| 시나리오 | 기존 우려 | 현재 해결 상태 |
|----------|--------|-----------|
| **급성 낙상** (의식 소실) | 3초 대기는 너무 김 | ✅ **해결**: 실제 낙상 즉시 DANGER (0초) |
| **천천히 쓰러짐** (어지러움) | 10초 전에 감지 필요 | ✅ **해결**: pre_impact 전조 1.5초 → WARNING 5초 → DANGER |
| **밤 시간대** | 의료진 부족 | ⬜ 향후: 시간대별 동적 임계값 조정 |
| **침대 옆 낙상** | DANGER 즉시 필요 | ✅ **해결**: fall_type 분류로 즉시 DANGER |

### 개선안

#### 옵션 A: 시간대별 동적 조정
```python
class TimeBasedEscalation:
    """시간대별 에스컬레이션 정책"""

    DAY_SHIFT = {    # 07:00~19:00 (의료진 충분)
        "warning": 3.0,
        "danger": 10.0,
        "escalate": 30.0
    }

    NIGHT_SHIFT = {  # 19:00~07:00 (의료진 부족)
        "warning": 1.0,   # 더 빠른 감지
        "danger": 5.0,
        "escalate": 15.0
    }
```

#### 옵션 B: 공간 기반 에스컬레이션
```python
class ZoneBasedEscalation:
    """구역별 에스컬레이션 정책"""

    HIGH_RISK_ZONES = {  # 계단, 화장실, 복도
        "warning": 0.5,   # 즉시 경고
        "danger": 3.0,
        "escalate": 10.0
    }

    SAFE_ZONES = {       # 대기실, 침대 근처
        "warning": 3.0,
        "danger": 10.0,
        "escalate": 30.0
    }
```

#### 옵션 C: 하이브리드 (권장)
```python
@dataclass
class EscalationPolicy:
    """동적 에스컬레이션 정책"""

    base_warning: float = 2.0    # 기본 3초 → 2초 단축
    base_danger: float = 8.0     # 기본 10초 → 8초 단축
    base_escalate: float = 20.0  # 기본 30초 → 20초 단축

    # 상황별 계수
    night_multiplier: float = 0.5   # 밤에는 절반으로
    high_risk_zone_multiplier: float = 0.3
    history_multiplier: float = 0.7  # 낙상 이력자는 더 빠르게
```

---

## 3. WebSocket 메시지 포맷 검토

### 현재 제안 포맷
```json
{
  "type": "alert",
  "level": "danger",
  "timestamp": "2024-01-15T14:32:15.123Z",
  "payload": {
    "event_id": "evt_abc123",
    "title": "낙상 감지",
    "message": "대기실에서 낙상이 감지되었습니다",
    "camera_id": "cam_01",
    "person_id": 1,
    "duration": 12.5,
    "confidence": 0.92,
    "snapshot_url": "/api/events/evt_abc123/snapshot"
  }
}
```

### 누락된 필드 및 개선안

#### 🔴 필수 추가 필드
```typescript
interface AlertPayload {
  // 기존 필드
  event_id: string;
  title: string;
  message: string;
  camera_id: string;
  person_id: number;
  duration: number;
  confidence: number;
  snapshot_url: string;

  // ⭐ 추가 필요 필드
  location: {
    zone_name: string;           // "대기실", "복도-A", "화장실-1층"
    zone_type: "waiting" | "corridor" | "bathroom" | "room";
    coordinates: { x: number; y: number };  // 화면 좌표
    floor?: number;              // 층수 (다층 병원)
  };

  patient_info?: {               // 프라이버시 고려 옵션
    bed_number?: string;         // 병상 번호
    risk_level: "low" | "medium" | "high";  // 낙상 위험도
    has_fall_history: boolean;   // 이전 낙상 이력
  };

  medical_context: {
    is_first_alert: boolean;     // 첫 알림인지 재알림인지
    previous_event_id?: string;  // 연관 이벤트 ID
    estimated_severity: "minor" | "moderate" | "severe";
  };

  action_required: {
    priority: "low" | "medium" | "high" | "critical";
    suggested_action: string;    // "즉시 확인", "관찰 필요"
    estimated_response_time: number;  // 예상 도착 시간(초)
  };

  media: {
    snapshot_url: string;
    video_clip_url?: string;     // 5초 전후 영상
    pose_skeleton_url?: string;  // 스켈레톤 오버레이
  };

  acknowledgement?: {
    ack_id?: string;             // 확인 ID
    ack_required_by: string;     // ISO timestamp
    auto_escalate_after: number; // 초 단위
  };
}
```

#### 메시지 타입 확장
```typescript
type MessageType =
  | "alert"                // 낙상 알림
  | "alert_ack"           // 알림 확인
  | "alert_resolve"       // 사건 해결
  | "status_update"       // 상태 업데이트
  | "connection"          // 연결 상태
  | "heartbeat"           // 연결 유지
  | "system_message";     // 시스템 메시지
```

---

## 4. Web Push (VAPID) 우선순위

### MVP(최소 기능 제품)에 필요한 것

#### ✅ 필수: WebSocket + Web Push (VAPID)
**이유**:
1. WebSocket: 대시보드 실시간 업데이트 (1순위)
2. Web Push (VAPID): 의료진 모바일 앱 푸시 (2순위)
3. 두 채널만으로도 골든타임 대응 가능

#### ⏸️ 선택: Telegram
**장점**:
- 구현 간단 (Telegram Bot API)
- 별도 앱 설치 불필요
- 이미지 첨부 간편

**단점**:
- 의료 현장에서 Telegram 사용률 낮음
- 개인정보보호법 이슈 (제3국 서버)
- 기관 방화벽 차단 가능

**권장**: Phase 4 (고도화) 단계로 미루고, MVP는 WebSocket + Web Push (VAPID)에 집중

#### ⏸️ 선택: SMS
**장점**:
- 100% 도달률
- 앱 설치 불필요

**단점**:
- 비용 발생 (건당 15~20원)
- 이미지 전송 불가
- 지연 가능 (3~5초)

**권장**: 2차 에스컬레이션(30초 후) 수단으로만 사용

### 우선순위 결론

| 단계 | 채널 | 우선순위 | 구현 시점 |
|------|------|----------|-----------|
| 1차 알림 | WebSocket | 필수 | MVP |
| 1차 알림 | Web Push (VAPID) | 필수 | MVP |
| 2차 알림 | SMS | 권장 | MVP |
| 선택 | Telegram | 선택 | Phase 4 |
| 선택 | Email | 선택 | Phase 5 |

---

## 5. 알림 중복 방지 및 확인(Acknowledge) 시스템

### 중복 방지 전략

#### A. 이벤트 디바운싱
```python
class AlertDebouncer:
    """
    동일 사건 중복 알림 방지

    규칙:
    - 동일 person_id + 동일 zone + 10초 이내 → 중복으로 간주
    - 첫 알림만 전송, 이후는 duration 업데이트만
    """

    def __init__(self, window: float = 10.0):
        self.active_events: Dict[str, Event] = {}
        self.window = window

    def should_send_alert(
        self,
        person_id: int,
        zone: str,
        timestamp: float
    ) -> Tuple[bool, Optional[str]]:
        """
        알림 전송 여부 판단

        Returns:
            (should_send, existing_event_id)
        """
        key = f"{person_id}:{zone}"

        if key in self.active_events:
            event = self.active_events[key]
            if timestamp - event.start_time < self.window:
                return False, event.id  # 중복 - 전송하지 않음

        return True, None  # 새 이벤트 - 전송
```

#### B. 알림 그룹화
```python
class AlertGrouper:
    """
    다수 낙상 시 알림 통합

    예: 3명 동시 낙상 → 개별 알림 3개 X, 통합 알림 1개 O
    """

    def group_concurrent_alerts(
        self,
        alerts: List[Alert],
        time_window: float = 5.0
    ) -> List[GroupedAlert]:
        """시간 윈도우 내 알림 그룹화"""
        pass
```

### 확인(Acknowledge) 시스템 설계

#### C. 확인 플로우
```
1. 알림 발송 (event_id + ack_id 포함)
   ↓
2. 의료진이 "확인" 버튼 클릭
   ↓
3. POST /api/events/{event_id}/acknowledge
   ↓
4. DB에 ack_time, ack_user 저장
   ↓
5. WebSocket으로 모든 클라이언트에 "확인됨" 브로드캐스트
   ↓
6. 해당 이벤트 알림 중단
```

#### D. 확인 데이터 모델
```python
@dataclass
class Acknowledgement:
    ack_id: str
    event_id: str
    ack_by: str          # 확인한 의료진 ID
    ack_at: datetime
    ack_method: str      # "dashboard", "mobile", "tablet"
    response_time: float # 초 단위
    action_taken: str    # "checking_patient", "already_assisted"
    notes: Optional[str]
```

#### E. 미확인 알림 에스컬레이션
```python
class UnacknowledgedEscalator:
    """
    미확인 알림 에스컬레이션

    - 10초 미확인 → 추가 푸시 + 소리 강화
    - 20초 미확인 → 관리자/다른 의료진에게 알림
    - 30초 미확인 → SMS 발송 + 시스템 로그
    """

    async def escalate_unacknowledged(self, event_id: str):
        event = await get_event(event_id)

        if not event.acknowledged:
            elapsed = time.time() - event.created_at.timestamp()

            if elapsed > 10:
                await send_reminder_push(event)

            if elapsed > 20:
                await notify_supervisor(event)

            if elapsed > 30:
                await send_sms(event)
                await log_critical(event)
```

---

## 6. 오프라인/연결 끊김 시 알림 보장 전략

### 문제 시나리오

| 상황 | 영향 | 확률 |
|------|------|------|
| 네트워크 일시 끊김 | WebSocket 알림 손실 | 높음 |
| 모바일 앱 백그라운드 | FCM 지연/손실 | 중간 |
| 서버 재시작 | 메모리 내 이벤트 손실 | 낮음 |
| 클라이언트 브라우저 종료 | 알림 수신 불가 | 높음 |

### 해결 전략

#### A. WebSocket 재연결 + 메시지 큐
```typescript
class RobustWebSocketClient {
  private messageQueue: Message[] = [];
  private reconnectAttempts = 0;
  private maxReconnectDelay = 30000; // 30초

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onclose = () => {
      // 지수 백오프로 재연결
      const delay = Math.min(
        1000 * Math.pow(2, this.reconnectAttempts),
        this.maxReconnectDelay
      );

      setTimeout(() => {
        this.reconnectAttempts++;
        this.connect();
      }, delay);
    };

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;

      // 재연결 시 누락 이벤트 요청
      this.requestMissedEvents();
    };
  }

  async requestMissedEvents() {
    const lastEventTime = localStorage.getItem('lastEventTime');
    const response = await fetch(
      `/api/events/missed?since=${lastEventTime}`
    );
    const missedEvents = await response.json();

    missedEvents.forEach(event => {
      this.handleEvent(event);
    });
  }
}
```

#### B. 서버 측 Redis 기반 메시지 버퍼
```python
class MessageBuffer:
    """
    Redis 기반 알림 버퍼링

    - 모든 알림을 Redis에 24시간 보관
    - 클라이언트 재연결 시 미수신 메시지 전송
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.ttl = 86400  # 24시간

    async def buffer_message(
        self,
        channel: str,
        message: dict
    ):
        """메시지 버퍼링"""
        key = f"msg_buffer:{channel}"
        await self.redis.zadd(
            key,
            {json.dumps(message): time.time()}
        )
        await self.redis.expire(key, self.ttl)

    async def get_missed_messages(
        self,
        channel: str,
        since: float
    ) -> List[dict]:
        """특정 시간 이후 메시지 조회"""
        key = f"msg_buffer:{channel}"
        messages = await self.redis.zrangebyscore(
            key, since, "+inf"
        )
        return [json.loads(m) for m in messages]
```

#### C. FCM + 로컬 DB 하이브리드
```python
class HybridNotificationService:
    """
    FCM + SQLite 하이브리드

    플로우:
    1. FCM 전송 시도
    2. 실패 시 로컬 DB에 저장
    3. 백그라운드 작업으로 재시도 (최대 3회)
    4. 모바일 앱 재접속 시 로컬 DB 조회 후 알림 표시
    """

    async def send_with_fallback(
        self,
        token: str,
        notification: dict
    ):
        try:
            result = await self.fcm.send(token, notification)

            if result.success:
                return True
            else:
                await self.store_failed_notification(notification)
                await self.retry_queue.add(notification)

        except NetworkError:
            await self.store_failed_notification(notification)
            await self.retry_queue.add(notification)
```

#### D. 핵심 전략 요약

| 레이어 | 기술 | 보장 수준 |
|--------|------|----------|
| 1. WebSocket | 자동 재연결 + 지수 백오프 | 중간 |
| 2. 메시지 버퍼 | Redis 24시간 보관 | 높음 |
| 3. 미수신 메시지 | REST API 조회 | 높음 |
| 4. FCM 백업 | 로컬 DB + 재시도 큐 | 높음 |
| 5. 최종 안전망 | SMS (30초 미확인 시) | 매우 높음 |

---

## 7. 현재 프론트엔드 Store와의 연동 설계

### 현재 Zustand Store 분석

#### 기존 구조 (C:\Users\dbals\VibeCoding\Care-guard\frontend\src\store\monitoring.ts)
```typescript
// 강점
✅ AlertLevel 타입 정의 (safe, warning, danger)
✅ EventLog 기본 구조
✅ 알림 카운트 및 지속시간 추적
✅ 설정 관리 (fallThresholdTime, dangerThresholdTime)

// 부족한 점
❌ 확인(acknowledge) 상태 관리 없음
❌ 알림 이력 관리 없음
❌ 다중 이벤트 동시 처리 미지원
❌ WebSocket 연결 상태만 있고 재연결 로직 없음
```

### 개선된 Store 설계

#### A. 알림 상태 확장
```typescript
// frontend/src/store/notification.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface Alert {
  id: string;
  eventId: string;
  level: AlertLevel;
  title: string;
  message: string;
  timestamp: Date;
  acknowledged: boolean;
  acknowledgedAt?: Date;
  acknowledgedBy?: string;
  location: {
    zoneName: string;
    coordinates: { x: number; y: number };
  };
  media: {
    snapshotUrl: string;
    videoClipUrl?: string;
  };
  priority: "low" | "medium" | "high" | "critical";
  autoEscalateAt?: Date;
}

interface NotificationState {
  // 활성 알림
  activeAlerts: Alert[];

  // 알림 이력 (최대 100개)
  alertHistory: Alert[];

  // 확인되지 않은 알림 수
  unacknowledgedCount: number;

  // 액션
  addAlert: (alert: Omit<Alert, "id" | "timestamp">) => void;
  acknowledgeAlert: (alertId: string, userId: string) => void;
  dismissAlert: (alertId: string) => void;
  clearAllAlerts: () => void;

  // 자동 에스컬레이션 체크
  checkEscalation: () => void;
}

export const useNotificationStore = create<NotificationState>()(
  persist(
    (set, get) => ({
      activeAlerts: [],
      alertHistory: [],
      unacknowledgedCount: 0,

      addAlert: (alert) => {
        const newAlert: Alert = {
          ...alert,
          id: `alert_${Date.now()}_${Math.random().toString(36).slice(2)}`,
          timestamp: new Date(),
          acknowledged: false,
        };

        set((state) => ({
          activeAlerts: [...state.activeAlerts, newAlert],
          unacknowledgedCount: state.unacknowledgedCount + 1,
        }));

        // 음향 알림
        if (newAlert.level === "danger") {
          playDangerSound();
        }
      },

      acknowledgeAlert: (alertId, userId) => {
        const now = new Date();

        set((state) => {
          const alert = state.activeAlerts.find(a => a.id === alertId);

          if (!alert || alert.acknowledged) return state;

          // API 호출
          fetch(`/api/events/${alert.eventId}/acknowledge`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              ack_by: userId,
              ack_at: now.toISOString(),
            }),
          });

          const updatedAlerts = state.activeAlerts.map(a =>
            a.id === alertId
              ? { ...a, acknowledged: true, acknowledgedAt: now, acknowledgedBy: userId }
              : a
          );

          const updatedHistory = [
            ...state.alertHistory,
            updatedAlerts.find(a => a.id === alertId)!,
          ].slice(0, 100);

          return {
            activeAlerts: updatedAlerts,
            alertHistory: updatedHistory,
            unacknowledgedCount: Math.max(0, state.unacknowledgedCount - 1),
          };
        });
      },

      dismissAlert: (alertId) => {
        set((state) => ({
          activeAlerts: state.activeAlerts.filter(a => a.id !== alertId),
        }));
      },

      clearAllAlerts: () => {
        set({ activeAlerts: [], unacknowledgedCount: 0 });
      },

      checkEscalation: () => {
        const { activeAlerts } = get();
        const now = Date.now();

        activeAlerts.forEach(alert => {
          if (!alert.acknowledged && alert.autoEscalateAt) {
            const escalateTime = new Date(alert.autoEscalateAt).getTime();

            if (now >= escalateTime) {
              // 에스컬레이션 트리거
              console.warn(`Alert ${alert.id} escalating!`);
              // SMS 발송 등 추가 조치
            }
          }
        });
      },
    }),
    {
      name: "notification-storage",
      partialize: (state) => ({
        alertHistory: state.alertHistory, // 이력만 localStorage 저장
      }),
    }
  )
);

// 자동 에스컬레이션 체크 (10초마다)
setInterval(() => {
  useNotificationStore.getState().checkEscalation();
}, 10000);
```

---

## 8. 최종 권장 구현 우선순위

### MVP 핵심
```
주차 1:
□ WebSocket 재연결 로직 구현
□ Redis 메시지 버퍼 구축
□ Notification Store 확장
□ 확인(Acknowledge) 시스템 백엔드 API
□ 확인(Acknowledge) 시스템 프론트엔드

주차 2:
□ Web Push (VAPID) 푸시 알림 연동
□ 시간대별 에스컬레이션 정책
□ 미수신 이벤트 조회 API
□ DangerAlertDialog 개선 (이미지, 카운트다운)
□ 알림 이력 관리
```

### 고도화
```
주차 3:
□ 공간 기반 에스컬레이션
□ SMS 2차 알림 연동
□ 알림 그룹화 (다수 낙상)
□ 알림 통계 대시보드

주차 4:
□ Telegram Bot (선택)
□ 이메일 알림 (선택)
□ 알림 A/B 테스트 도구
□ 성능 최적화 및 로드 테스트
```

---

## 9. 핵심 체크리스트

### 의료 현장 필수 요구사항

- [x] 10초 골든타임 보장
- [ ] 밤/낮 시간대 별 정책 지원
- [x] 확인(Acknowledge) 시스템
- [x] 미확인 알림 자동 에스컬레이션
- [x] 고위험 구역 즉시 알림 (Safe-Zone 기반 구현)
- [ ] 오프라인 복구 시 이벤트 복원 (Redis 미구현)
- [x] 알림 중복 방지
- [x] 다수 낙상 동시 처리 (YOLO11 다중 인원 추적)

### 기술적 안정성

- [x] WebSocket 자동 재연결
- [ ] Redis 메시지 버퍼링 (24시간)
- [x] Web Push 알림 (VAPID)
- [ ] SMS 백업 알림
- [ ] 로컬 DB 캐싱
- [ ] 에러 모니터링 (Sentry)
- [x] API 통합 테스트 (21개)
- [x] apiCall 자동 토큰 갱신
- [x] go2rtc 내부 인증 (INTERNAL_STREAM_KEY)
- [x] IoT Webhook 디바이스 연동 (HMAC-SHA256 서명)

### 사용성

- [x] 알림 우선순위 시각화
- [x] 스냅샷 이미지 포함
- [ ] 영상 클립 재생
- [x] 카운트다운 표시
- [x] 알림 이력 조회
- [ ] 알림 설정 UI

---

## 10. 결론 및 제안

### 주요 개선 필요 사항

1. **에스컬레이션 시간 단축**: 3/10/30초 → 2/8/20초 (밤에는 1/5/15초)
2. **WebSocket 메시지 포맷**: location, medical_context, acknowledgement 필드 추가
3. **MVP 우선순위**: WebSocket + Web Push (VAPID) + SMS만, Telegram은 Phase 4로
4. **확인 시스템**: 백엔드 API + 프론트엔드 Store 통합 필수
5. **오프라인 대응**: Redis 버퍼 + 미수신 이벤트 조회 API 필수

### 제안 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    SENTIO 알림 시스템                    │
└─────────────────────────────────────────────────────────┘

[낙상 감지 엔진]
      │
      ├─> [AlertManager] ─┬─> [Redis 버퍼] (24시간 보관)
                          │
                          ├─> [WebSocket] ────> [대시보드]
                          │         ↑
                          │         └─ 재연결 시 미수신 조회
                          │
                          ├─> [Web Push (VAPID)] > [모바일 앱]
                          │         ↑
                          │         └─ 실패 시 재시도 큐
                          │
                          ├─> [SMS (30초 후)] > [의료진 핸드폰]
                          │
                          └─> [IoT Webhook] ──> [경광등/스마트장치]

[확인 시스템]
  └─> POST /api/events/{id}/acknowledge
        └─> WebSocket 브로드캐스트 "확인됨"
              └─> 모든 클라이언트 알림 해제
```

### 다음 단계

1. 이 검토 보고서를 기반으로 백엔드 NotificationService 구현
2. 프론트엔드 Notification Store 확장
3. 재연결 로직 포함한 WebSocket 훅 개선
4. Redis 메시지 버퍼 구축
5. Web Push (VAPID) 연동 및 테스트

---

**작성자**: Claude Code
**검토 일자**: 2026-01-30
**문서 버전**: 1.0
