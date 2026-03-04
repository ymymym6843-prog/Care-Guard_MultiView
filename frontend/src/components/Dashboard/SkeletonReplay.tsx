/**
 * Skeleton Replay - 사건 리플레이 뷰어
 *
 * Skeleton Blackbox에서 저장된 관절 좌표 JSON을 로드하여
 * Canvas 위에 스켈레톤 애니메이션으로 재생합니다.
 * 원본 영상 없이 비식별 좌표만으로 사고 상황을 재현합니다.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiCall } from "@/lib/auth";

// MediaPipe Pose 연결선 (useSkeletonRenderer와 동일)
const POSE_CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28],
  [15, 17], [15, 19], [16, 18], [16, 20],
  [27, 29], [27, 31], [28, 30], [28, 32],
];

interface IncidentPerson {
  id: string;
  posture: string;
  confidence: number;
  landmarks: number[][]; // [[x, y, z, vis], ...]
}

interface IncidentFrame {
  t: number;
  persons: IncidentPerson[];
}

interface IncidentData {
  incident_id: string;
  triggered_at: string;
  trigger_person: string;
  fps: number;
  total_frames: number;
  frames: IncidentFrame[];
  privacy_notice: string;
}

// 인물별 색상
const PERSON_COLORS = [
  { line: "#00ff80", joint: "#00ccff" },
  { line: "#ff6b6b", joint: "#ff9999" },
  { line: "#ffd93d", joint: "#ffe066" },
  { line: "#6bcb77", joint: "#99e6a0" },
  { line: "#4d96ff", joint: "#80b3ff" },
];

export default function SkeletonReplay() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  const [data, setData] = useState<IncidentData | null>(null);
  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1.0);
  const [error, setError] = useState("");

  // 파일 업로드 핸들러
  const handleFileUpload = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const json = JSON.parse(ev.target?.result as string);
          setData(json);
          setCurrentFrame(0);
          setIsPlaying(false);
          setError("");
        } catch {
          setError("JSON 파일 파싱 실패");
        }
      };
      reader.readAsText(file);
    },
    [],
  );

  // API에서 로드 (향후 사건 목록 UI에서 호출)
  // @ts-expect-error 향후 사건 목록 UI에서 사용 예정
  const _loadFromApi = useCallback(async (incidentId: string) => {
    try {
      const res = await apiCall(`/api/incidents/${incidentId}/replay`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setCurrentFrame(0);
      setIsPlaying(false);
      setError("");
    } catch (err) {
      setError(`API 로드 실패: ${err}`);
    }
  }, []);

  // 프레임 렌더링
  const renderFrame = useCallback(
    (frameIdx: number) => {
      const canvas = canvasRef.current;
      if (!canvas || !data) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;

      // 검은 배경
      ctx.fillStyle = "#111827";
      ctx.fillRect(0, 0, w, h);

      const frame = data.frames[frameIdx];
      if (!frame) return;

      // 각 인물 렌더링
      frame.persons.forEach((person, pIdx) => {
        const colorSet = PERSON_COLORS[pIdx % PERSON_COLORS.length]!;
        const lms = person.landmarks;
        if (!lms || lms.length === 0) return;

        // 낙상 시 빨간색
        const isFallen = person.confidence > 0.5;
        const lineColor = isFallen ? "#ff3333" : colorSet.line;
        const jointColor = isFallen ? "#ff6666" : colorSet.joint;

        // 연결선
        ctx.strokeStyle = lineColor;
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        for (const [sIdx, eIdx] of POSE_CONNECTIONS) {
          if (sIdx >= lms.length || eIdx >= lms.length) continue;
          const s = lms[sIdx];
          const e = lms[eIdx];
          if (!s || !e) continue;
          const sVis = s[3] ?? 1;
          const eVis = e[3] ?? 1;
          if (sVis < 0.3 || eVis < 0.3) continue;

          ctx.beginPath();
          ctx.moveTo((s[0] ?? 0) * w, (s[1] ?? 0) * h);
          ctx.lineTo((e[0] ?? 0) * w, (e[1] ?? 0) * h);
          ctx.stroke();
        }

        // 관절점
        ctx.fillStyle = jointColor;
        for (const lm of lms) {
          const vis = lm[3] ?? 1;
          if (vis < 0.3) continue;
          ctx.beginPath();
          ctx.arc((lm[0] ?? 0) * w, (lm[1] ?? 0) * h, 4, 0, Math.PI * 2);
          ctx.fill();
        }

        // 인물 ID 라벨
        const headLm = lms[0];
        if (headLm && (headLm[3] ?? 1) > 0.3) {
          ctx.fillStyle = isFallen ? "#ff3333" : "#ffffff";
          ctx.font = "12px monospace";
          ctx.fillText(
            `${person.id} (${person.posture})`,
            (headLm[0] ?? 0) * w - 30,
            (headLm[1] ?? 0) * h - 12,
          );
        }
      });

      // 타임스탬프 + 프레임 정보
      ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
      ctx.fillRect(0, h - 30, w, 30);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "13px monospace";
      ctx.fillText(
        `T=${frame.t.toFixed(2)}s  |  Frame ${frameIdx + 1}/${data.total_frames}  |  ${frame.persons.length}명`,
        10,
        h - 10,
      );
    },
    [data],
  );

  // 재생 루프
  useEffect(() => {
    if (!isPlaying || !data) return;

    const fps = data.fps || 30;
    const intervalMs = (1000 / fps) / speed;
    let lastTime = performance.now();

    const animate = (now: number) => {
      if (now - lastTime >= intervalMs) {
        lastTime = now;
        setCurrentFrame((prev) => {
          const next = prev + 1;
          if (next >= data.frames.length) {
            setIsPlaying(false);
            return prev;
          }
          return next;
        });
      }
      animFrameRef.current = requestAnimationFrame(animate);
    };

    animFrameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [isPlaying, speed, data]);

  // 프레임 변경 시 렌더링
  useEffect(() => {
    renderFrame(currentFrame);
  }, [currentFrame, renderFrame]);

  // 낙상 시점 찾기
  const findFallFrame = useCallback(() => {
    if (!data) return -1;
    return data.frames.findIndex((f) =>
      f.persons.some((p) => p.confidence > 0.5),
    );
  }, [data]);

  const totalFrames = data?.frames.length ?? 0;
  const fallFrame = findFallFrame();

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">
          Skeleton Replay
        </h3>
        <div className="flex gap-2">
          <label className="cursor-pointer rounded bg-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-600">
            JSON 파일 업로드
            <input
              type="file"
              accept=".json"
              className="hidden"
              onChange={handleFileUpload}
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="mb-2 rounded bg-red-900/50 px-3 py-1 text-xs text-red-300">
          {error}
        </div>
      )}

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        width={640}
        height={480}
        className="w-full rounded-lg border border-slate-700"
        style={{ aspectRatio: "4/3", background: "#111827" }}
      />

      {data && (
        <>
          {/* 타임라인 바 */}
          <div className="relative mt-2">
            <input
              type="range"
              min={0}
              max={totalFrames - 1}
              value={currentFrame}
              onChange={(e) => {
                setCurrentFrame(Number(e.target.value));
                setIsPlaying(false);
              }}
              className="w-full accent-blue-500"
            />
            {/* 낙상 시점 마커 */}
            {fallFrame >= 0 && totalFrames > 0 && (
              <div
                className="absolute top-0 h-4 w-1 rounded bg-red-500"
                style={{
                  left: `${(fallFrame / totalFrames) * 100}%`,
                }}
                title={`낙상 시점: Frame ${fallFrame}`}
              />
            )}
          </div>

          {/* 컨트롤 */}
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-500"
            >
              {isPlaying ? "Pause" : "Play"}
            </button>

            {/* 프레임 단위 이동 */}
            <button
              onClick={() => setCurrentFrame(Math.max(0, currentFrame - 1))}
              className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
              disabled={isPlaying}
            >
              &lt;
            </button>
            <button
              onClick={() =>
                setCurrentFrame(Math.min(totalFrames - 1, currentFrame + 1))
              }
              className="rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
              disabled={isPlaying}
            >
              &gt;
            </button>

            {/* 속도 조절 */}
            <div className="flex items-center gap-1">
              {[0.5, 1, 1.5, 2].map((s) => (
                <button
                  key={s}
                  onClick={() => setSpeed(s)}
                  className={`rounded px-2 py-0.5 text-xs ${
                    speed === s
                      ? "bg-blue-600 text-white"
                      : "bg-slate-700 text-slate-400 hover:bg-slate-600"
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            {/* 낙상 시점 이동 */}
            {fallFrame >= 0 && (
              <button
                onClick={() => setCurrentFrame(fallFrame)}
                className="rounded bg-red-700 px-2 py-1 text-xs text-red-100 hover:bg-red-600"
              >
                낙상 시점
              </button>
            )}
          </div>

          {/* 메타데이터 */}
          <div className="mt-2 text-xs text-slate-500">
            {data.incident_id} | {data.triggered_at} | {data.total_frames}{" "}
            frames @ {data.fps}fps
            {data.privacy_notice && (
              <span className="ml-2 text-green-500">
                {data.privacy_notice}
              </span>
            )}
          </div>
        </>
      )}

      {!data && (
        <div className="mt-4 text-center text-sm text-slate-500">
          JSON 파일을 업로드하거나 API에서 사건 데이터를 로드하세요.
        </div>
      )}
    </div>
  );
}
