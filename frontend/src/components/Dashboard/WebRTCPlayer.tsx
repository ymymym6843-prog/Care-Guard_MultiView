/**
 * WHEP 기반 WebRTC 플레이어
 *
 * go2rtc의 WHEP 엔드포인트를 통해 WebRTC 스트림을 재생합니다.
 * 연결 실패 시 MJPEG 폴백 URL을 사용합니다.
 */

import { useRef, useEffect, useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface WebRTCPlayerProps {
  streamName?: string;
  fallbackUrl?: string;
  className?: string;
}

export function WebRTCPlayer({
  streamName = "camera_default",
  fallbackUrl,
  className,
}: WebRTCPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [status, setStatus] = useState<"connecting" | "connected" | "fallback" | "error">("connecting");

  const connect = useCallback(async () => {
    try {
      setStatus("connecting");

      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      pcRef.current = pc;

      pc.addTransceiver("video", { direction: "recvonly" });
      pc.addTransceiver("audio", { direction: "recvonly" });

      pc.ontrack = (event) => {
        if (videoRef.current && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0];
          setStatus("connected");
        }
      };

      pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === "failed" || pc.iceConnectionState === "disconnected") {
          setStatus("fallback");
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // WHEP 엔드포인트로 SDP 교환
      const whepUrl = `/webrtc/api/webrtc?src=${encodeURIComponent(streamName)}`;
      const res = await fetch(whepUrl, {
        method: "POST",
        headers: { "Content-Type": "application/sdp" },
        body: offer.sdp,
      });

      if (!res.ok) {
        throw new Error(`WHEP failed: ${res.status}`);
      }

      const answerSdp = await res.text();
      await pc.setRemoteDescription(new RTCSessionDescription({
        type: "answer",
        sdp: answerSdp,
      }));
    } catch {
      setStatus("fallback");
    }
  }, [streamName]);

  useEffect(() => {
    connect();

    return () => {
      if (pcRef.current) {
        pcRef.current.close();
        pcRef.current = null;
      }
    };
  }, [connect]);

  // WebRTC 연결 실패 시 MJPEG 폴백
  if (status === "fallback" && fallbackUrl) {
    return (
      <img
        src={fallbackUrl}
        alt="카메라 피드 (MJPEG 폴백)"
        className={cn("w-full h-full object-cover", className)}
      />
    );
  }

  return (
    <div className={cn("relative w-full h-full", className)}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="w-full h-full object-cover"
      />
      {status === "connecting" && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
          <p className="text-white text-sm animate-pulse">WebRTC 연결 중...</p>
        </div>
      )}
      {status === "error" && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50">
          <p className="text-danger text-sm">연결 실패</p>
        </div>
      )}
    </div>
  );
}
