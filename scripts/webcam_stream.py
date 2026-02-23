"""
SENTIO 원격 웹캠 MJPEG 스트리머

다른 PC의 웹캠을 네트워크 IP 카메라로 변환합니다.
SENTIO Docker 환경에서 CAMERA_SOURCE로 사용 가능합니다.

사용법:
    python webcam_stream.py                    # 기본 (카메라0, 포트8080)
    python webcam_stream.py --port 9090        # 포트 변경
    python webcam_stream.py --camera 1         # 두번째 카메라
    python webcam_stream.py --width 1280 --height 720  # 해상도 변경

SENTIO 연결:
    .env.docker에서 CAMERA_SOURCE=http://이PC의IP:8080/video
"""

import argparse
import signal
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import cv2


class CameraCapture:
    """스레드 안전한 카메라 캡처"""

    def __init__(self, camera_index: int, width: int, height: int, fps: int):
        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            print(f"[ERROR] 카메라 {camera_index}을 열 수 없습니다.")
            print("사용 가능한 카메라를 확인하세요.")
            sys.exit(1)

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

        actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[INFO] 카메라 해상도: {actual_w}x{actual_h}")

        self._lock = threading.Lock()
        self._frame = None
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        while self._running:
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    def stop(self):
        self._running = False
        self._thread.join(timeout=2)
        self.cap.release()


camera: CameraCapture | None = None
jpeg_quality = 80


class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/video" or self.path == "/":
            self._stream_mjpeg()
        elif self.path == "/snapshot":
            self._send_snapshot()
        elif self.path == "/status":
            self._send_status()
        else:
            self.send_error(404, "Not Found. Use /video, /snapshot, or /status")

    def _stream_mjpeg(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        encode_params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]

        try:
            while True:
                frame = camera.get_frame()
                if frame is None:
                    time.sleep(0.03)
                    continue

                _, jpg = cv2.imencode(".jpg", frame, encode_params)
                data = jpg.tobytes()

                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(data)}\r\n\r\n".encode())
                self.wfile.write(data)
                self.wfile.write(b"\r\n")
                self.wfile.flush()

                time.sleep(0.033)  # ~30fps
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_snapshot(self):
        frame = camera.get_frame()
        if frame is None:
            self.send_error(503, "Camera not ready")
            return

        _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        data = jpg.tobytes()

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_status(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK - SENTIO Webcam Streamer running")

    def log_message(self, format, *args):
        if "/status" not in str(args):
            print(f"[{self.client_address[0]}] {args[0]}")


class ThreadedHTTPServer(HTTPServer):
    """클라이언트 동시 접속 지원"""
    allow_reuse_address = True

    def process_request(self, request, client_address):
        t = threading.Thread(target=self._handle, args=(request, client_address), daemon=True)
        t.start()

    def _handle(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def get_local_ip():
    """로컬 네트워크 IP 주소 확인"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "확인불가"


def main():
    global camera, jpeg_quality

    parser = argparse.ArgumentParser(description="SENTIO 원격 웹캠 MJPEG 스트리머")
    parser.add_argument("--camera", type=int, default=0, help="카메라 인덱스 (기본: 0)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP 포트 (기본: 8080)")
    parser.add_argument("--width", type=int, default=640, help="영상 너비 (기본: 640)")
    parser.add_argument("--height", type=int, default=480, help="영상 높이 (기본: 480)")
    parser.add_argument("--fps", type=int, default=30, help="카메라 FPS (기본: 30)")
    parser.add_argument("--quality", type=int, default=80, help="JPEG 품질 1-100 (기본: 80)")
    args = parser.parse_args()

    jpeg_quality = args.quality

    print("=" * 50)
    print("  SENTIO 원격 웹캠 스트리머")
    print("=" * 50)
    print(f"[INFO] 카메라 인덱스: {args.camera}")

    camera = CameraCapture(args.camera, args.width, args.height, args.fps)

    local_ip = get_local_ip()
    server = ThreadedHTTPServer(("0.0.0.0", args.port), MJPEGHandler)

    print()
    print(f"[OK] 스트림 시작됨!")
    print(f"  MJPEG 스트림: http://{local_ip}:{args.port}/video")
    print(f"  스냅샷:       http://{local_ip}:{args.port}/snapshot")
    print(f"  상태 확인:    http://{local_ip}:{args.port}/status")
    print()
    print(f"[SENTIO 연결 방법]")
    print(f"  .env.docker 에서:")
    print(f"  CAMERA_SOURCE=http://{local_ip}:{args.port}/video")
    print()
    print("  Ctrl+C로 종료")
    print("=" * 50)

    def shutdown(sig, frame):
        print("\n[INFO] 종료 중...")
        camera.stop()
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
