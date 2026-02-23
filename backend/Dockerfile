FROM python:3.11-slim

# MediaPipe / OpenCV 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 설치 (레이어 캐시 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# MediaPipe 모델 빌드 타임 다운로드
RUN mkdir -p /app/models && \
    curl -L -o /app/models/pose_landmarker_full.task \
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"

# YOLO11s-pose 모델 빌드 타임 다운로드
RUN python -c "from ultralytics import YOLO; model = YOLO('yolo11s-pose.pt')" && \
    mv yolo11s-pose.pt /app/models/ 2>/dev/null || true

# 소스 코드 복사
COPY . .

EXPOSE 8000

# 싱글 워커 (싱글톤 서비스 유지)
CMD ["gunicorn", "app.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "1", \
     "--bind", "0.0.0.0:8000", \
     "--forwarded-allow-ips", "*", \
     "--max-requests", "1000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
