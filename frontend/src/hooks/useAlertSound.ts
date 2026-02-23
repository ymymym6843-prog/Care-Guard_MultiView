/**
 * 알림 사운드 훅
 *
 * Web Audio API 오실레이터 기반 알림 사운드 + 프리렌더링 TTS 음성
 *
 * TTS 음성 파일 (Edge TTS ko-KR-SunHiNeural 음성):
 *   /audio/alert_warning.mp3  — 전조 감지: "주의! 낙상 위험 감지!"
 *   /audio/alert_fall.mp3     — 실제 낙상: "경고! 낙상 발생!"
 *   /audio/alert_danger.mp3   — 위험 상황: "긴급! 낙상 발생! 즉시 확인하세요!"
 *
 * 브라우저 자동재생 정책:
 *   사용자가 페이지와 상호작용(클릭/키보드) 후에만 오디오 재생 가능.
 *   첫 상호작용 시 AudioContext resume + 무음 재생으로 잠금 해제.
 */

import { useCallback, useEffect, useRef } from "react";
import { useMonitoringStore } from "@/store/monitoring";

// TTS 음성 파일 경로 (Edge TTS ko-KR-SunHiNeural 음성)
const TTS_AUDIO = {
  preImpact: "/audio/alert_warning.mp3",    // 전조: "주의! 낙상 위험 감지!"
  actualFall: "/audio/alert_fall.mp3",      // 실제 낙상: "경고! 낙상 발생!"
  danger: "/audio/alert_danger.mp3",        // 위험: "긴급! 낙상 발생! 즉시 확인하세요!"
} as const;

const ACTUAL_FALL_TYPES = ["front_fall", "back_fall", "side_fall"];

/** 오디오 잠금 해제 상태 (모듈 레벨 — 한 번만 실행) */
let audioUnlocked = false;

function unlockAudio(ctx: AudioContext) {
  if (audioUnlocked) return;
  audioUnlocked = true;

  // AudioContext resume
  if (ctx.state === "suspended") {
    ctx.resume();
  }

  // 무음 재생으로 HTMLAudioElement 잠금 해제
  const silence = new Audio(
    "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=",
  );
  silence.volume = 0;
  silence.play().catch(() => {});
}

export function useAlertSound() {
  const audioCtxRef = useRef<AudioContext | null>(null);
  const isPlayingRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval>>();
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);

  const getAudioContext = useCallback(() => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext();
    }
    return audioCtxRef.current;
  }, []);

  // 사용자 상호작용 시 오디오 잠금 해제
  useEffect(() => {
    const handler = () => {
      const ctx = getAudioContext();
      unlockAudio(ctx);
    };
    // 클릭, 키보드, 터치 모두 감지
    document.addEventListener("click", handler, { once: false });
    document.addEventListener("keydown", handler, { once: false });
    document.addEventListener("touchstart", handler, { once: false });

    return () => {
      document.removeEventListener("click", handler);
      document.removeEventListener("keydown", handler);
      document.removeEventListener("touchstart", handler);
    };
  }, [getAudioContext]);

  /** 프리렌더링된 TTS 음성 파일 재생 */
  const playTtsAlert = useCallback((key: keyof typeof TTS_AUDIO) => {
    // 이전 재생 중지
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current.currentTime = 0;
    }
    const audio = new Audio(TTS_AUDIO[key]);
    audio.volume = 0.85;
    audio.play().catch(() => {
      // 사용자 인터랙션 전이면 차단됨 — 무시
    });
    ttsAudioRef.current = audio;
  }, []);

  /** TTS 음성 중지 */
  const stopTts = useCallback(() => {
    if (ttsAudioRef.current) {
      ttsAudioRef.current.pause();
      ttsAudioRef.current.currentTime = 0;
      ttsAudioRef.current = null;
    }
  }, []);

  const playBeep = useCallback(
    (frequency: number, duration: number, volume: number = 0.3) => {
      try {
        const ctx = getAudioContext();
        if (ctx.state === "suspended") {
          ctx.resume();
        }

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.type = "sine";
        osc.frequency.value = frequency;
        gain.gain.value = volume;

        // 페이드 아웃
        gain.gain.exponentialRampToValueAtTime(
          0.001,
          ctx.currentTime + duration,
        );

        osc.start();
        osc.stop(ctx.currentTime + duration);
      } catch {
        // 오디오 컨텍스트 오류 무시
      }
    },
    [getAudioContext],
  );

  const playWarningSound = useCallback(() => {
    playBeep(800, 0.2, 0.2);
  }, [playBeep]);

  const playDangerSound = useCallback(() => {
    // 긴급 알림: 빠른 반복 비프
    playBeep(1000, 0.15, 0.4);
    setTimeout(() => playBeep(1200, 0.15, 0.4), 200);
    setTimeout(() => playBeep(1000, 0.15, 0.4), 400);
  }, [playBeep]);

  const triggerVibration = useCallback((level: "warning" | "danger") => {
    if (level === "danger") {
      navigator.vibrate?.([200, 100, 200, 100, 400]);
    } else {
      navigator.vibrate?.([100, 50, 100]);
    }
  }, []);

  const startAlertLoop = useCallback(
    (level: "warning" | "danger") => {
      if (isPlayingRef.current) return;
      isPlayingRef.current = true;

      const sound = level === "danger" ? playDangerSound : playWarningSound;
      const interval = level === "danger" ? 2000 : 5000;

      sound();
      triggerVibration(level);
      intervalRef.current = setInterval(() => {
        sound();
        triggerVibration(level);
      }, interval);
    },
    [playWarningSound, playDangerSound, triggerVibration],
  );

  const stopAlertLoop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = undefined;
    }
    isPlayingRef.current = false;
  }, []);

  // 알림 레벨 변화 감시
  useEffect(() => {
    const unsub = useMonitoringStore.subscribe((state, prevState) => {
      const soundEnabled = state.settings.soundEnabled;
      if (!soundEnabled) {
        stopAlertLoop();
        stopTts();
        return;
      }

      if (state.currentAlert !== prevState.currentAlert) {
        const isActualFall = ACTUAL_FALL_TYPES.includes(state.currentFallType);

        stopAlertLoop();
        if (state.currentAlert === "danger") {
          startAlertLoop("danger");
        } else if (state.currentAlert === "warning") {
          // 실제 낙상: danger급 비프음 / 전조: 기존 warning 비프
          startAlertLoop(isActualFall ? "danger" : "warning");
        }

        // TTS 프리렌더링 음성 재생 (3단계)
        if (state.settings.ttsEnabled) {
          if (state.currentAlert === "danger" && prevState.currentAlert !== "danger") {
            playTtsAlert("danger");
          } else if (state.currentAlert === "warning" && prevState.currentAlert === "safe") {
            playTtsAlert(isActualFall ? "actualFall" : "preImpact");
          } else if (state.currentAlert === "safe" && prevState.currentAlert !== "safe") {
            stopTts();
          }
        }
      }
    });

    return () => {
      unsub();
      stopAlertLoop();
      stopTts();
      if (audioCtxRef.current) {
        audioCtxRef.current.close();
        audioCtxRef.current = null;
      }
    };
  }, [startAlertLoop, stopAlertLoop, playTtsAlert, stopTts]);

  return { playWarningSound, playDangerSound, stopAlertLoop };
}
