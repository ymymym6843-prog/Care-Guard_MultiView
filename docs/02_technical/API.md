# SENTIO API 문서

## 기본 정보

- Base URL: `http://localhost:8001` (개발), `http://localhost:8000` (Docker)
- 인증: HttpOnly 쿠키 (기본) / Bearer JWT Token (폴백)
- Content-Type: `application/json`

## 인증 (Auth)

### GET /api/auth/check-setup
초기 설정 필요 여부를 확인합니다. (인증 불필요, 공개)

**Response** (200):
```json
{ "needs_setup": true }
```

> 데이터베이스에 사용자가 없는 경우 true를 반환합니다.

### POST /api/auth/login
로그인하여 HttpOnly 쿠키로 인증 토큰을 설정합니다.

> **레이트 리밋**: IP당 60초 내 최대 5회 시도. 초과 시 `429 Too Many Requests` 반환.

**Request** (form-data):
| Field | Type | Description |
|-------|------|-------------|
| username | string | 사용자명 |
| password | string | 비밀번호 |

**Response** (200):

응답 헤더에 `Set-Cookie`로 인증 쿠키가 설정됩니다:
- `access_token`: HttpOnly, SameSite=Lax, Path=/, max-age=28800 (8시간)
- `refresh_token`: HttpOnly, SameSite=Lax, Path=/api/auth, max-age=604800 (7일)

```json
{
  "status": "ok",
  "user": {
    "username": "admin",
    "full_name": "관리자",
    "role": "admin"
  }
}
```

### POST /api/auth/register
새 사용자를 등록합니다.

> **보안**: 첫 번째 등록 사용자는 자동으로 `admin` 역할이 부여됩니다. 이후 등록은 관리자 인증이 필요합니다.

**Request**:
```json
{
  "username": "nurse01",
  "password": "securepass",
  "full_name": "김간호사",
  "role": "staff"
}
```

**Response** (200):
```json
{ "status": "created", "username": "nurse01", "role": "staff" }
```

### POST /api/auth/logout
로그아웃합니다. 인증 쿠키를 삭제합니다.

**Response** (200):
```json
{ "status": "logged_out" }
```

> 응답 헤더에 `Set-Cookie`로 `access_token`, `refresh_token` 쿠키가 만료(`max-age=0`)됩니다.

### GET /api/auth/me
현재 로그인한 사용자 정보를 반환합니다. (인증 필수)

**인증**: HttpOnly 쿠키 자동 전송 또는 `Authorization: Bearer <token>` 헤더

**Response** (200):
```json
{
  "username": "admin",
  "full_name": "관리자",
  "role": "admin",
  "is_active": true
}
```

### GET /api/auth/users
모든 사용자를 조회합니다. (관리자 전용)

**인증**: HttpOnly 쿠키 자동 전송 또는 `Authorization: Bearer <token>` 헤더

**Response** (200):
```json
[
  {
    "username": "admin",
    "full_name": "관리자",
    "role": "admin",
    "is_active": true
  }
]
```

### POST /api/auth/refresh
Access Token을 갱신합니다.

> refresh_token 쿠키에서 자동 추출됩니다.

**Response** (200): 갱신된 access_token, refresh_token 쿠키 설정

---

## 카메라 (Cameras)

### GET /api/cameras/status
카메라 상태를 조회합니다.

**Response** (200):
```json
{
  "is_running": true,
  "camera_id": "cam0",
  "fps": 28.5,
  "resolution": "1280x720"
}
```

### POST /api/cameras/start
카메라 모니터링을 시작합니다.

**Response** (200):
```json
{ "status": "started", "camera_id": "cam0" }
```

### POST /api/cameras/stop
카메라 모니터링을 중지합니다.

**Response** (200):
```json
{ "status": "stopped" }
```

### GET /api/cameras/available
사용 가능한 카메라 목록을 조회합니다.

**Response** (200):
```json
{
  "cameras": [
    { "id": "cam0", "name": "내장 웹캠", "resolution": "1280x720" },
    { "id": "cam1", "name": "외장 웹캠", "resolution": "1920x1080" }
  ]
}
```

### POST /api/cameras/switch
카메라를 전환합니다.

**Request**:
```json
{ "camera_id": "cam1" }
```

**Response** (200):
```json
{ "status": "switched", "camera_id": "cam1" }
```

---

## 이벤트 (Events)

### GET /api/events
이벤트 목록을 조회합니다. (인증 필수)

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| page | int | 페이지 번호 (기본값: 1) |
| size | int | 페이지 크기 (기본값: 20, 최대: 100) |
| level | string | 필터: warning, danger |
| since | datetime | 시작 시간 (ISO 8601) |
| until | datetime | 종료 시간 (ISO 8601) |
| room_id | int | 공간 ID 필터 |

**Response** (200):
```json
{
  "items": [
    {
      "id": 1,
      "timestamp": "2026-02-10T14:32:15.123Z",
      "alert_level": "danger",
      "person_id": 2,
      "duration": 12.5,
      "confidence": 0.87,
      "fall_type": "back_fall",
      "camera_id": "cam0",
      "room_id": 1
    }
  ],
  "total": 142,
  "page": 1,
  "size": 20
}
```

### POST /api/events/{event_id}/acknowledge
이벤트를 확인 처리합니다.

**Response** (200):
```json
{ "status": "acknowledged", "event_id": 1, "ack_by": "admin" }
```

---

## WebSocket (실시간 모니터링)

### WS /ws/monitoring
실시간 모니터링 데이터 스트림.

**인증**: HttpOnly 쿠키 자동 전송 (same-origin) 또는 `?token=<access_token>` 쿼리 파라미터 폴백

**서버 → 클라이언트 메시지**:

```json
{
  "type": "monitoring_data",
  "camera_id": "cam0",
  "timestamp": "2026-02-10T14:32:15.123Z",
  "persons": [
    {
      "person_id": 1,
      "track_id": 5,
      "alert_level": "normal",
      "posture": "standing",
      "fall_probability": 0.05,
      "rule_score": 0.02,
      "ml_score": 0.05,
      "confidence": 0.05,
      "duration": 0.3,
      "bbox": [100, 50, 300, 450],
      "keypoints": [[x, y, visibility], ...]
    }
  ],
  "fps": 28.5
}
```

**클라이언트 → 서버 메시지**:

```json
{ "type": "acknowledge", "person_id": 1 }
```

---

## 스트리밍 (Stream)

### GET /api/stream/mjpeg/{camera_id}
MJPEG 비디오 스트림. (인증 필수)

**인증**: HttpOnly 쿠키 자동 전송 또는 `?token=<access_token>` 쿼리 파라미터

**Response**: `multipart/x-mixed-replace` MJPEG 스트림

### POST /api/stream/pause
AI 파이프라인을 일시 중지합니다.

**Response** (200):
```json
{ "status": "paused" }
```

### POST /api/stream/resume
AI 파이프라인을 재개합니다.

**Response** (200):
```json
{ "status": "resumed" }
```

---

## Safe-Zone (안전지대)

### GET /api/zones
안전지대 목록을 조회합니다.

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| camera_id | string | 카메라 ID 필터 |

**Response** (200):
```json
[
  {
    "id": 1,
    "camera_id": "cam0",
    "name": "침대 구역",
    "zone_type": "safe",
    "polygon": [[100, 100], [300, 100], [300, 300], [100, 300]],
    "is_active": true
  }
]
```

### POST /api/zones
안전지대를 생성합니다. (관리자 전용)

**Request**:
```json
{
  "camera_id": "cam0",
  "name": "위험 구역",
  "zone_type": "danger",
  "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]]
}
```

Zone 타입:
- `safe`: 안전 구역 (낙상 시에도 알림 허용)
- `danger`: 위험 구역 (즉시 알림)
- `exclusion`: 제외 구역 (감지 완전 스킵)

**Response** (200):
```json
{ "id": 2, "status": "created" }
```

### DELETE /api/zones/{zone_id}
안전지대를 삭제합니다. (관리자 전용)

**Response** (200):
```json
{ "status": "deleted" }
```

---

## 통계 (Stats)

### GET /api/stats/summary
통계 요약을 조회합니다. (인증 필수)

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| days | int | 조회 기간 (기본값: 7) |
| room_id | int | 공간 ID 필터 |

**Response** (200):
```json
{
  "total_events": 142,
  "danger_count": 5,
  "warning_count": 37,
  "avg_response_time": 8.2,
  "period_days": 7
}
```

### GET /api/stats/daily
일별 이벤트 통계. (인증 필수)

**Response** (200):
```json
[
  { "date": "2026-02-10", "danger": 1, "warning": 5, "total": 6 },
  { "date": "2026-02-09", "danger": 0, "warning": 7, "total": 7 }
]
```

### GET /api/stats/hourly
시간대별 이벤트 빈도. (인증 필수)

**Response** (200):
```json
[
  { "hour": 9, "count": 15 },
  { "hour": 14, "count": 12 }
]
```

---

## 설정 (Settings)

### GET /api/settings
현재 감지 설정을 조회합니다. (인증 필수)

**Response** (200):
```json
{
  "fall_warning_seconds": 3.0,
  "fall_danger_seconds": 10.0,
  "fall_danger_confidence": 0.70,
  "fall_rule_weight": 0.0,
  "fall_ml_weight": 1.0,
  "privacy_mode": "skeleton"
}
```

### PUT /api/settings
감지 설정을 변경합니다. (인증 필수)

**Request**:
```json
{
  "fall_warning_seconds": 2.0,
  "fall_danger_confidence": 0.65
}
```

> `fall_rule_weight + fall_ml_weight`의 합계가 반드시 1.0이어야 합니다.

**Response** (200):
```json
{ "status": "updated" }
```

---

## AI 모델 관리 (Models)

### GET /api/models
AI 모델 목록을 조회합니다. (관리자 전용)

**Response** (200):
```json
{
  "models": [
    {
      "name": "fall_classifier_gru.onnx",
      "type": "gru",
      "size_mb": 1.9,
      "is_active": true,
      "description": "GRU Binary 분류기 (Fall/Normal), AIHub 665,574 시퀀스 학습"
    }
  ]
}
```

### POST /api/models/switch
활성 모델을 교체합니다. (관리자 전용)

**Request**:
```json
{ "model_name": "fall_classifier_v2.onnx" }
```

**Response** (200):
```json
{ "status": "switched", "active_model": "fall_classifier_v2.onnx" }
```

---

## 오탐지 보고 (False Reports)

### POST /api/false-reports
오탐지/미탐지를 보고합니다. (인증 필수)

**Request** (multipart/form-data):
| Field | Type | Description |
|-------|------|-------------|
| event_id | int | 관련 이벤트 ID |
| report_type | string | `false_positive` 또는 `false_negative` |
| description | string | 상세 설명 |
| image | file | 스크린샷 첨부 (선택) |

**Response** (200):
```json
{
  "id": 1,
  "status": "created",
  "alert": null
}
```

> 보고 건수가 10건 이상일 때 `alert` 필드에 경고 메시지가 포함됩니다.

### GET /api/false-reports/summary
오탐지 보고 통계 요약. (관리자 전용)

**Response** (200):
```json
{
  "total": 12,
  "false_positive": 8,
  "false_negative": 4,
  "this_week": 3,
  "needs_attention": true
}
```

---

## 공간 관리 (Rooms)

### GET /api/rooms
공간 목록을 조회합니다. (인증 필수)

**Response** (200):
```json
[
  {
    "id": 1,
    "name": "대기실A",
    "description": "1층 정문 근처 대기실",
    "cameras": ["cam0", "cam1"]
  }
]
```

### POST /api/rooms
공간을 생성합니다. (관리자 전용)

**Request**:
```json
{
  "name": "복도",
  "description": "2층 복도"
}
```

**Response** (200):
```json
{ "id": 2, "status": "created" }
```

### PUT /api/rooms/{room_id}/cameras
공간에 카메라를 배정합니다. (관리자 전용)

**Request**:
```json
{ "camera_ids": ["cam0", "cam2"] }
```

**Response** (200):
```json
{ "status": "updated", "room_id": 1 }
```

---

## Web Push (푸시 알림)

### GET /api/push/vapid-key
VAPID 공개 키를 조회합니다. (인증 필수)

**Response** (200):
```json
{ "public_key": "BNHc..." }
```

### POST /api/push/subscribe
푸시 알림 구독을 등록합니다. (인증 필수)

**Request**:
```json
{
  "endpoint": "https://fcm.googleapis.com/...",
  "keys": {
    "p256dh": "...",
    "auth": "..."
  }
}
```

**Response** (200):
```json
{ "status": "subscribed" }
```

### DELETE /api/push/unsubscribe
푸시 알림 구독을 해지합니다. (인증 필수)

**Response** (200):
```json
{ "status": "unsubscribed" }
```

---

## 에러 코드

| HTTP 코드 | 설명 |
|-----------|------|
| 400 | 잘못된 요청 (파라미터 오류) |
| 401 | 인증 필요 (쿠키 만료 또는 없음) |
| 403 | 권한 없음 (관리자 전용 엔드포인트) |
| 404 | 리소스 없음 |
| 422 | 유효성 검사 실패 |
| 429 | 레이트 리밋 초과 |
| 500 | 서버 내부 오류 |

**에러 응답 형식**:
```json
{
  "detail": "인증이 필요합니다.",
  "code": "UNAUTHORIZED"
}
```
