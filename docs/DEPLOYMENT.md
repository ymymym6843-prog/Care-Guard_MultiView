# Sentio 프로덕션 배포 가이드

> 최종 업데이트: 2026-02-10

## 📋 배포 전 체크리스트

### 필수 설정

- [ ] `DEBUG=false` 설정
- [ ] `DEV_AUTO_LOGIN=false` 설정  
- [ ] `JWT_SECRET_KEY`를 강력한 난수로 변경
- [ ] `COOKIE_SECURE=true` 설정 (HTTPS 필수)
- [ ] `PORT=8001` 확인
- [ ] 데이터베이스를 PostgreSQL로 변경
- [ ] VAPID 키 생성 (`python scripts/generate_secrets.py`)

### 성능 최적화

- [ ] `OVERLAY_ENABLED=false` 설정 (20-30% 성능 향상)
- [ ] `YOLO_USE_GPU=true` 설정 (CUDA 사용 가능 시)
- [ ] `MULTI_CAMERA_ENABLED` 필요 여부 확인

### 보안

- [ ] `.env` 파일을 `.gitignore`에 추가
- [ ] 모든 비밀 키를 안전하게 보관
- [ ] HTTPS 인증서 설정 완료
- [ ] 방화벽 규칙 구성

---

## 🚀 배포 절차

### 1. 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (위 체크리스트 항목 적용)
nano .env
```

**필수 변경 항목**:
```bash
DEBUG=false
DEV_AUTO_LOGIN=false
JWT_SECRET_KEY=<강력한-난수-32자-이상>
COOKIE_SECURE=true
DATABASE_URL=postgresql+asyncpg://user:password@localhost/sentio
```

### 2. 데이터베이스 마이그레이션

```bash
cd backend

# 마이그레이션 실행
alembic upgrade head

# 검증
alembic current
```

### 3. Docker 배포

#### 개발 환경
```bash
docker compose up -d --build
```

#### 프로덕션 환경 (HTTPS)
```bash
# SSL 인증서 준비 (Let's Encrypt)
# nginx/certs/ 디렉터리에 인증서 배치

# 프로덕션 Docker Compose로 실행
docker compose -f docker-compose.ssl.yml up -d --build

# 로그 확인
docker compose logs -f
```

### 4. 수동 배포 (Docker 없이)

#### Backend

```bash
cd backend

# 가상 환경 활성화
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 패키지 설치
pip install -r requirements.txt

# Gunicorn으로 실행 (프로덕션)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

#### Frontend

```bash
cd frontend

# 패키지 설치
npm install

# 프로덕션 빌드
npm run build

# 빌드된 파일을 웹 서버에 배포
# dist/ 디렉터리를 Nginx, Apache 등에 서빙
```

#### Nginx 설정 예시

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend
    location / {
        root /path/to/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 🔍 배포 후 검증

### 1. 서버 상태 확인

```bash
# Health check
curl https://your-domain.com/health

# 예상 응답
{
  "status": "healthy",
  "service": "SENTIO WAITING AI",
  "version": "1.0.0"
}
```

### 2. 로그 확인

```bash
# Docker 환경
docker compose logs backend
docker compose logs frontend

# 수동 배포 환경
tail -f backend/logs/app.log
```

### 3. 기능 테스트

- [ ] 로그인/로그아웃 정상 작동
- [ ] WebSocket 연결 확인
- [ ] 카메라 피드 스트리밍 확인
- [ ] 낙상 감지 테스트 (데모 비디오)
- [ ] 알림 수신 확인
- [ ] 통계 대시보드 로딩 확인

---

## 🔧 트러블슈팅

### WebSocket 연결 실패

**증상**: "연결 끊김" 상태 지속

**해결 방법**:
1. Nginx WebSocket 프록시 설정 확인
2. 방화벽에서 WebSocket 포트 (8001) 오픈
3. `FRONTEND_URL` 환경 변수가 올바른지 확인

### 성능 저하

**증상**: 카메라 피드가 느림, 랜드마크 오버레이 지연

**해결 방법**:
1. `OVERLAY_ENABLED=false` 설정 (20-30% 향상)
2. GPU 사용 가능 시 `YOLO_USE_GPU=true`
3. 다중 카메라 모드 비활성화 고려

### 인증 오류

**증상**: 로그인 후 즉시 로그아웃됨

**해결 방법**:
1. `COOKIE_SECURE` 설정과 HTTPS 사용 여부 일치 확인
2. `COOKIE_DOMAIN` 설정 확인
3. 브라우저 쿠키 허용 설정 확인

---

## 📊 모니터링

### 로그 관리

프로덕션 환경에서는 로그 수집 및 분석 도구 사용 권장:

- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Datadog** APM
- **Sentry** (에러 추적)

### 성능 모니터링

```bash
# CPU/메모리 사용량 확인
docker stats

# 시스템 리소스 모니터링
htop
```

### 백업

```bash
# 데이터베이스 백업 (PostgreSQL)
pg_dump -U sentio_user sentio > backup_$(date +%Y%m%d).sql

# Docker 볼륨 백업
docker run --rm -v sentio_db_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/db_backup.tar.gz /data
```

---

## 🔄 업데이트 및 유지보수

### 애플리케이션 업데이트

```bash
# 저장소에서 최신 코드 가져오기
git pull origin main

# Docker 환경
docker compose down
docker compose up -d --build

# 마이그레이션 실행 (필요 시)
docker compose exec backend alembic upgrade head
```

### 환경 변수 변경

환경 변수 변경 후 반드시 서비스 재시작:

```bash
docker compose restart
```

---

## 📞 지원

문제 발생 시:
1. 로그 파일 확인
2. GitHub Issues에 버그 리포트
3. 문서 참조: [ARCHITECTURE.md](ARCHITECTURE.md), [API.md](02_technical/API.md)

---

**보안 알림**: 절대로 `.env` 파일이나 비밀 키를 Git에 커밋하지 마세요!
