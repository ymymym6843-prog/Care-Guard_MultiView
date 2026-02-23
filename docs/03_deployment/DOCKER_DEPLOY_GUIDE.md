# SENTIO Docker 배포 가이드

> 버전: 1.0 | 최종 업데이트: 2026-02-12

---

## 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [아키텍처 개요](#2-아키텍처-개요)
3. [설치 및 실행](#3-설치-및-실행)
4. [카메라 연결](#4-카메라-연결)
5. [환경 변수 설정](#5-환경-변수-설정)
6. [주요 명령어](#6-주요-명령어)
7. [GPU 가속 (선택)](#7-gpu-가속-선택)
8. [문제 해결](#8-문제-해결)

---

## 1. 사전 요구사항

| 항목 | 요구사항 |
|------|---------|
| OS | Windows 10/11, macOS, Linux |
| Docker Desktop | v4.0 이상 |
| RAM | 최소 4GB (권장 8GB) |
| 디스크 | 약 5GB (이미지 빌드 포함) |
| 네트워크 | 카메라와 같은 네트워크 |

### Docker Desktop 설치

1. https://www.docker.com/products/docker-desktop/ 접속
2. OS에 맞는 버전 다운로드 및 설치
3. 설치 후 재부팅
4. Docker Desktop 실행 확인 (시스템 트레이에 고래 아이콘)
5. 터미널에서 확인:
   ```bash
   docker --version
   docker-compose --version
   ```

---

## 2. 아키텍처 개요

```
브라우저 (:80)
    │
    └── Nginx (리버스 프록시)
          ├── /           → Frontend (React SPA)
          ├── /api/       → Backend  (FastAPI + AI 낙상감지)
          ├── /ws/        → Backend  (WebSocket 실시간 알림)
          └── /webrtc/    → go2rtc   (WebRTC 영상)
                               │
                          Backend ←── PostgreSQL (이벤트/통계 DB)
                          Backend ←── 카메라 (MJPEG/RTSP URL)
```

### 서비스 구성 (5개)

| 서비스 | 이미지 | 역할 |
|--------|--------|------|
| **db** | postgres:16-alpine | 이벤트, 통계, 공간 데이터 저장 |
| **backend** | python:3.11-slim (빌드) | FastAPI + YOLO11 + GRU 낙상감지 AI |
| **frontend-build** | node:20-alpine (빌드) | React 앱 빌드 → Nginx에 전달 |
| **go2rtc** | alexxit/go2rtc | MJPEG → WebRTC 변환 |
| **nginx** | nginx:alpine | 리버스 프록시, 정적 파일 서빙 |

---

## 3. 설치 및 실행

### 3-1. 코드 클론

```bash
git clone https://github.com/ymymym6843-prog/Care-Guard_MultiView.git
cd Care-Guard_MultiView
```

### 3-2. 카메라 소스 설정

`.env.docker` 파일을 열어 카메라 URL을 설정합니다:

```env
# 모바일 폰 (IP Webcam 앱)
CAMERA_SOURCE=http://192.168.0.15:8080/video

# 또는 다른 PC 웹캠 (webcam_stream.py)
# CAMERA_SOURCE=http://192.168.0.10:8080/video

# 또는 IP 카메라 (RTSP)
# CAMERA_SOURCE=rtsp://admin:password@192.168.0.100:554/stream1
```

> IP 주소는 본인 환경에 맞게 변경하세요.

### 3-3. 실행

```bash
docker-compose up -d
```

- 최초 실행 시 이미지 빌드에 **5~10분** 소요 (YOLO 모델 다운로드 포함)
- 이후 재실행 시 캐시 사용으로 빠르게 시작

### 3-4. 접속

브라우저에서 **http://localhost** 접속

> 포트를 변경한 경우: `http://localhost:설정한포트`

### 3-5. 기본 로그인

| 항목 | 값 |
|------|-----|
| ID | admin |
| PW | admin1234 |

> 최초 로그인 후 비밀번호를 변경하세요.

---

## 4. 카메라 연결

Docker 컨테이너는 격리된 환경이므로 USB 웹캠에 직접 접근할 수 없습니다.
네트워크 카메라(IP 카메라) 또는 모바일/PC를 IP 카메라로 변환하여 사용합니다.

### 4-1. 모바일 폰을 IP 카메라로 사용

#### Android (IP Webcam 앱)

1. Google Play에서 **IP Webcam** 설치
2. 앱 실행 → 아래로 스크롤 → **Start server** 터치
3. 화면에 표시된 IP 확인 (예: `192.168.0.15:8080`)
4. `.env.docker`에 설정:
   ```env
   CAMERA_SOURCE=http://192.168.0.15:8080/video
   ```

#### iPhone (DroidCam 앱)

1. App Store에서 **DroidCam** 설치
2. 앱 실행 → IP 주소 확인
3. `.env.docker`에 설정:
   ```env
   CAMERA_SOURCE=http://아이폰IP:4747/video
   ```

> PC와 모바일이 **같은 Wi-Fi**에 연결되어 있어야 합니다.

### 4-2. 다른 PC의 웹캠을 IP 카메라로 사용

프로젝트에 포함된 `scripts/webcam_stream.py`를 사용합니다.

**다른 PC에서:**

```bash
# opencv-python 설치
pip install opencv-python

# 스트리머 실행
python scripts/webcam_stream.py
```

실행하면 연결 URL이 표시됩니다:

```
==================================================
  SENTIO 원격 웹캠 스트리머
==================================================
[OK] 스트림 시작됨!
  MJPEG 스트림: http://192.168.0.10:8080/video

[SENTIO 연결 방법]
  .env.docker 에서:
  CAMERA_SOURCE=http://192.168.0.10:8080/video
==================================================
```

**옵션:**

```bash
python webcam_stream.py --port 9090         # 포트 변경
python webcam_stream.py --camera 1          # 두번째 웹캠
python webcam_stream.py --width 1280 --height 720  # HD 해상도
```

### 4-3. IP 카메라 (실제 운영 환경)

```env
# RTSP
CAMERA_SOURCE=rtsp://admin:password@192.168.0.100:554/stream1

# MJPEG
CAMERA_SOURCE=http://192.168.0.100:80/video.mjpg
```

### 4-4. 카메라 연결 확인 방법

Docker 실행 전, PC 브라우저에서 카메라 URL에 직접 접속하여 영상이 나오는지 확인:

```
http://카메라IP:포트/video
```

영상이 나오면 Docker에서도 정상 동작합니다.

---

## 5. 환경 변수 설정

`.env.docker` 파일의 모든 설정 항목:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `POSTGRES_PASSWORD` | sentio_secret | DB 비밀번호 (프로덕션에서 변경) |
| `JWT_SECRET_KEY` | (기본키) | JWT 인증 키 (프로덕션에서 변경) |
| `INTERNAL_STREAM_KEY` | (기본키) | 내부 스트림 인증 키 |
| `FRONTEND_URL` | http://localhost | 프론트엔드 URL |
| **`CAMERA_SOURCE`** | (빈값) | **카메라 URL (핵심 설정)** |
| `CAMERA_INDEX` | 0 | CAMERA_SOURCE 미설정 시 웹캠 인덱스 |
| `HTTP_PORT` | 80 | 웹 접속 포트 |
| `DEBUG` | false | 디버그 모드 |
| `FHIR_BASE_URL` | (빈값) | EMR 연동 URL (선택) |
| `FHIR_API_KEY` | (빈값) | EMR API 키 (선택) |
| `VAPID_PRIVATE_KEY` | (빈값) | 푸시 알림 키 (선택) |
| `VAPID_PUBLIC_KEY` | (빈값) | 푸시 알림 공개키 (선택) |

### 프로덕션 보안 설정

프로덕션 환경에서는 반드시 아래 값을 변경하세요:

```env
POSTGRES_PASSWORD=강력한_비밀번호
JWT_SECRET_KEY=랜덤_시크릿_키_64자이상
INTERNAL_STREAM_KEY=랜덤_스트림_키
```

---

## 6. 주요 명령어

```bash
# === 기본 ===
docker-compose up -d              # 시작 (백그라운드)
docker-compose down               # 중지
docker-compose restart             # 재시작

# === 로그 ===
docker-compose logs -f             # 전체 로그
docker-compose logs -f backend     # AI 백엔드 로그만
docker-compose logs -f nginx       # 웹 접근 로그만

# === 빌드 ===
docker-compose up -d --build       # 코드 변경 후 재빌드

# === 상태 확인 ===
docker-compose ps                  # 서비스 상태
docker-compose exec backend curl http://localhost:8000/health  # 헬스체크

# === 데이터 ===
docker-compose down -v             # 중지 + DB 데이터 삭제 (초기화)
```

---

## 7. GPU 가속 (선택)

NVIDIA GPU가 있는 경우 AI 처리 속도를 높일 수 있습니다.

### 사전 요구사항

- NVIDIA 드라이버 설치
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) 설치

### 실행

```bash
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### 설정

`.env.docker`에서:
```env
YOLO_USE_GPU=true
```

---

## 8. 문제 해결

### 영상이 안 나옴

1. 카메라 URL을 PC 브라우저에서 직접 접속해서 확인
   ```
   http://카메라IP:포트/video
   ```
2. PC와 카메라가 같은 네트워크인지 확인
3. 방화벽에서 해당 포트가 열려있는지 확인
4. 백엔드 로그 확인:
   ```bash
   docker-compose logs -f backend | grep -i camera
   ```

### 포트 80 충돌

다른 프로그램이 80번 포트를 사용 중인 경우:
```env
# .env.docker
HTTP_PORT=8080
```
접속: `http://localhost:8080`

### 빌드 실패

```bash
# 캐시 초기화 후 재빌드
docker-compose down
docker system prune -f
docker-compose up -d --build
```

### backend 시작 실패

```bash
# 로그 확인
docker-compose logs backend

# DB 연결 문제인 경우
docker-compose restart db
docker-compose restart backend
```

### 컨테이너에서 카메라 IP 접근 불가

Windows Docker Desktop에서 LAN 접근이 안 되는 경우, `docker-compose.yml`의 backend에 추가:
```yaml
backend:
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

---

## 로컬 실행 vs Docker 실행 비교

| | 로컬 실행 | Docker 실행 |
|---|---|---|
| 명령어 | `uvicorn` + `npm run dev` | `docker-compose up -d` |
| DB | SQLite (파일) | PostgreSQL (컨테이너) |
| 카메라 | USB 웹캠 가능 | 네트워크 카메라만 |
| 설정 | `.env` | `.env.docker` |
| 포트 | 백엔드 8001 + 프론트 5173 | **80번 하나** |
| 코드 | 동일 | 동일 |
| 용도 | 개발/테스트 | 배포/운영 |
