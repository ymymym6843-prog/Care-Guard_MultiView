/**
 * 스켈레톤 렌더링 훅
 *
 * Canvas 2D에 포즈 좌표로부터 스켈레톤을 그립니다.
 */

import { useCallback, useRef } from "react";

interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility: number;
}

// MediaPipe Pose 33-point connections
const POSE_CONNECTIONS_MP: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], // Upper body
  [11, 23], [12, 24], [23, 24],                       // Torso
  [23, 25], [25, 27], [24, 26], [26, 28],             // Lower body
  [15, 17], [15, 19], [16, 18], [16, 20],             // Hands
  [27, 29], [27, 31], [28, 30], [28, 32],             // Feet
  [0, 1], [1, 2], [2, 3], [3, 7],                     // Face left
  [0, 4], [4, 5], [5, 6], [6, 8],                     // Face right
];

// COCO 17-point skeleton connections
const POSE_CONNECTIONS_COCO: [number, number][] = [
  [0, 1], [0, 2], [1, 3], [2, 4],       // Head
  [5, 6],                                 // Shoulders
  [5, 7], [7, 9],                         // Left arm
  [6, 8], [8, 10],                        // Right arm
  [5, 11], [6, 12],                       // Torso
  [11, 12],                               // Hips
  [11, 13], [13, 15],                     // Left leg
  [12, 14], [14, 16],                     // Right leg
];

export function useSkeletonRenderer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const drawSkeleton = useCallback(
    (landmarks: Landmark[], alertLevel: "safe" | "warning" | "danger" = "safe") => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      // 색상 선택
      const colors = {
        safe: { line: "#00ff80", joint: "#00ccff" },
        warning: { line: "#ffaa00", joint: "#ffcc00" },
        danger: { line: "#ff3333", joint: "#ff6666" },
      };
      const color = colors[alertLevel];

      // 연결선 그리기
      ctx.strokeStyle = color.line;
      ctx.lineWidth = 2;

      // 17개점(COCO) vs 33개점(MediaPipe) 자동 감지
      const connections = landmarks.length <= 17 ? POSE_CONNECTIONS_COCO : POSE_CONNECTIONS_MP;

      for (const [startIdx, endIdx] of connections) {
        if (startIdx >= landmarks.length || endIdx >= landmarks.length) continue;
        const start = landmarks[startIdx] as Landmark | undefined;
        const end = landmarks[endIdx] as Landmark | undefined;
        if (!start || !end) continue;
        if (start.visibility < 0.3 || end.visibility < 0.3) continue;

        ctx.beginPath();
        ctx.moveTo(start.x * w, start.y * h);
        ctx.lineTo(end.x * w, end.y * h);
        ctx.stroke();
      }

      // 관절점 그리기
      ctx.fillStyle = color.joint;
      for (const lm of landmarks) {
        if (lm.visibility < 0.3) continue;
        ctx.beginPath();
        ctx.arc(lm.x * w, lm.y * h, 4, 0, Math.PI * 2);
        ctx.fill();
      }
    },
    [],
  );

  const clearCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, []);

  return { canvasRef, drawSkeleton, clearCanvas };
}
