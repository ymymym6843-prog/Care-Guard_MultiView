import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

/* ──────────────────────────────────────────────
   Concept A: Sentio Pulse (파동 감지)
   - 동심원 파동 + 중앙 센서 노드
   - "감지하다"의 본질을 파동으로 표현
   ────────────────────────────────────────────── */
const SentioPulseLogo = ({ className }: { className?: string }) => (
  <div className={cn("flex items-center gap-3", className)}>
    <div className="relative w-12 h-12">
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-xl">
        <defs>
          <linearGradient id="pulseGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        {/* 동심원 파동 */}
        <circle cx="50" cy="50" r="42" fill="none" stroke="url(#pulseGrad)" strokeWidth="2" opacity="0.2" />
        <circle cx="50" cy="50" r="32" fill="none" stroke="url(#pulseGrad)" strokeWidth="2.5" opacity="0.4" />
        <circle cx="50" cy="50" r="22" fill="none" stroke="url(#pulseGrad)" strokeWidth="3" opacity="0.6" />
        {/* 중앙 코어 */}
        <circle cx="50" cy="50" r="12" fill="url(#pulseGrad)" />
        <circle cx="50" cy="50" r="5" fill="white" opacity="0.9" />
        {/* 4방향 감지선 */}
        <line x1="50" y1="8" x2="50" y2="20" stroke="url(#pulseGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="50" y1="80" x2="50" y2="92" stroke="url(#pulseGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="8" y1="50" x2="20" y2="50" stroke="url(#pulseGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="80" y1="50" x2="92" y2="50" stroke="url(#pulseGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
      </svg>
    </div>
    <div className="flex flex-col">
      <span className="text-2xl font-black bg-gradient-to-r from-indigo-500 to-cyan-500 bg-clip-text text-transparent tracking-tight leading-none">
        SENTIO
      </span>
      <span className="text-[10px] font-bold text-slate-400 tracking-[0.25em] uppercase mt-0.5">
        Sense &middot; Protect &middot; Care
      </span>
    </div>
  </div>
);

const SentioPulseFavicon = () => (
  <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <defs>
        <linearGradient id="pulseGradF" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="35" fill="none" stroke="url(#pulseGradF)" strokeWidth="4" opacity="0.3" />
      <circle cx="50" cy="50" r="22" fill="none" stroke="url(#pulseGradF)" strokeWidth="5" opacity="0.6" />
      <circle cx="50" cy="50" r="12" fill="url(#pulseGradF)" />
    </svg>
  </div>
);

/* ──────────────────────────────────────────────
   Concept B: Sentio Eye (AI 시선)
   - 눈 형태 + 홍채 안에 AI 노드
   - 24시간 지켜보는 모니터링 상징
   ────────────────────────────────────────────── */
const SentioEyeLogo = ({ className }: { className?: string }) => (
  <div className={cn("flex items-center gap-3", className)}>
    <div className="relative w-12 h-12">
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-xl">
        <defs>
          <linearGradient id="eyeGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="50%" stopColor="#8b5cf6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        {/* 눈 외곽 */}
        <path
          d="M5 50 C5 50, 25 20, 50 20 C75 20, 95 50, 95 50 C95 50, 75 80, 50 80 C25 80, 5 50, 5 50 Z"
          fill="none" stroke="url(#eyeGrad)" strokeWidth="4" strokeLinejoin="round"
        />
        {/* 홍채 */}
        <circle cx="50" cy="50" r="18" fill="url(#eyeGrad)" opacity="0.15" />
        <circle cx="50" cy="50" r="18" fill="none" stroke="url(#eyeGrad)" strokeWidth="3" />
        {/* 동공 */}
        <circle cx="50" cy="50" r="8" fill="url(#eyeGrad)" />
        {/* AI 노드 십자 */}
        <circle cx="50" cy="50" r="3" fill="white" />
        <line x1="50" y1="35" x2="50" y2="42" stroke="url(#eyeGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
        <line x1="50" y1="58" x2="50" y2="65" stroke="url(#eyeGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
        <line x1="35" y1="50" x2="42" y2="50" stroke="url(#eyeGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
        <line x1="58" y1="50" x2="65" y2="50" stroke="url(#eyeGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.6" />
      </svg>
    </div>
    <div className="flex flex-col">
      <span className="text-2xl font-black bg-gradient-to-r from-blue-500 via-violet-500 to-cyan-500 bg-clip-text text-transparent tracking-tight leading-none">
        SENTIO
      </span>
      <span className="text-[10px] font-bold text-slate-400 tracking-[0.25em] uppercase mt-0.5">
        Always Watching Over You
      </span>
    </div>
  </div>
);

const SentioEyeFavicon = () => (
  <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <defs>
        <linearGradient id="eyeGradF" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <path d="M10 50 C10 50, 28 22, 50 22 C72 22, 90 50, 90 50 C90 50, 72 78, 50 78 C28 78, 10 50, 10 50 Z"
        fill="url(#eyeGradF)" opacity="0.15" stroke="url(#eyeGradF)" strokeWidth="4" />
      <circle cx="50" cy="50" r="15" fill="url(#eyeGradF)" />
      <circle cx="50" cy="50" r="5" fill="white" />
    </svg>
  </div>
);

/* ──────────────────────────────────────────────
   Concept C: Sentio Shield (방패 + 감지파)
   - 기존 방패 DNA를 계승하되 감지 파동 추가
   - CARE-GUARD → Sentio로의 자연스러운 전환
   ────────────────────────────────────────────── */
const SentioShieldLogo = ({ className }: { className?: string }) => (
  <div className={cn("flex items-center gap-3", className)}>
    <div className="relative w-12 h-12">
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-xl">
        <defs>
          <linearGradient id="sShieldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#3b82f6" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        {/* 방패 */}
        <path
          d="M50 5 L85 20 V50 C85 75 50 95 50 95 C50 95 15 75 15 50 V20 L50 5 Z"
          fill="url(#sShieldGrad)" opacity="0.9"
        />
        {/* 감지 파동 (방패 안) */}
        <circle cx="50" cy="48" r="28" fill="none" stroke="white" strokeWidth="1.5" opacity="0.15" />
        <circle cx="50" cy="48" r="20" fill="none" stroke="white" strokeWidth="2" opacity="0.25" />
        <circle cx="50" cy="48" r="12" fill="none" stroke="white" strokeWidth="2.5" opacity="0.4" />
        {/* 중앙 센서 코어 */}
        <circle cx="50" cy="48" r="5" fill="white" opacity="0.95" />
        {/* 하단 S 힌트 라인 */}
        <path d="M38 68 Q44 64 50 68 Q56 72 62 68" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
      </svg>
    </div>
    <div className="flex flex-col">
      <span className="text-2xl font-black bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent tracking-tight leading-none">
        SENTIO
      </span>
      <span className="text-[10px] font-bold text-slate-400 tracking-[0.25em] uppercase mt-0.5">
        Advanced AI Safety
      </span>
    </div>
  </div>
);

const SentioShieldFavicon = () => (
  <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <defs>
        <linearGradient id="sShieldGradF" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#06b6d4" />
        </linearGradient>
      </defs>
      <path d="M50 5 L85 20 V50 C85 75 50 95 50 95 C50 95 15 75 15 50 V20 L50 5 Z" fill="url(#sShieldGradF)" />
      <circle cx="50" cy="45" r="14" fill="none" stroke="white" strokeWidth="3" opacity="0.5" />
      <circle cx="50" cy="45" r="6" fill="white" opacity="0.9" />
    </svg>
  </div>
);

/* ──────────────────────────────────────────────
   Concept D: Sentio Abstract (추상 S + 보호 곡선)
   - S자 곡선이 사람을 감싸는 형태
   - 미니멀하면서 따뜻한 느낌
   ────────────────────────────────────────────── */
const SentioAbstractLogo = ({ className }: { className?: string }) => (
  <div className={cn("flex items-center gap-3", className)}>
    <div className="relative w-12 h-12">
      <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-xl">
        <defs>
          <linearGradient id="absGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0ea5e9" />
            <stop offset="50%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        {/* S자 보호 곡선 */}
        <path
          d="M65 15 C85 15, 88 35, 70 42 C52 49, 30 45, 30 55 C30 65, 48 70, 50 70 C52 70, 70 68, 70 80 C70 95, 35 95, 35 85"
          fill="none" stroke="url(#absGrad)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round"
        />
        {/* 사람 형태 (감지 대상) */}
        <circle cx="50" cy="40" r="6" fill="url(#absGrad)" opacity="0.6" />
        <line x1="50" y1="46" x2="50" y2="62" stroke="url(#absGrad)" strokeWidth="3" strokeLinecap="round" opacity="0.6" />
        {/* 감지 점 */}
        <circle cx="72" cy="28" r="3" fill="url(#absGrad)" opacity="0.4" />
        <circle cx="28" cy="78" r="3" fill="url(#absGrad)" opacity="0.4" />
      </svg>
    </div>
    <div className="flex flex-col">
      <span className="text-2xl font-black bg-gradient-to-r from-sky-500 via-indigo-500 to-purple-500 bg-clip-text text-transparent tracking-tight leading-none">
        SENTIO
      </span>
      <span className="text-[10px] font-bold text-slate-400 tracking-[0.25em] uppercase mt-0.5">
        I Sense, Therefore I Protect
      </span>
    </div>
  </div>
);

const SentioAbstractFavicon = () => (
  <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <defs>
        <linearGradient id="absGradF" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0ea5e9" />
          <stop offset="50%" stopColor="#6366f1" />
          <stop offset="100%" stopColor="#a855f7" />
        </linearGradient>
      </defs>
      <path
        d="M62 15 C82 15, 85 35, 68 42 C50 49, 32 45, 32 55 C32 65, 50 72, 50 72 C50 72, 68 68, 68 80 C68 92, 38 92, 38 85"
        fill="none" stroke="url(#absGradF)" strokeWidth="10" strokeLinecap="round"
      />
    </svg>
  </div>
);

/* ──────────────────────────────────────────────
   Showcase Page
   ────────────────────────────────────────────── */
export default function SentioLogoShowcase() {
  const [selected, setSelected] = useState<number | null>(null);

  const concepts = [
    {
      id: 1,
      name: "Sentio Pulse",
      desc: "동심원 파동 + 센서 코어. '감지'의 본질을 시각화",
      tagline: "Sense · Protect · Care",
      colors: "Indigo → Cyan",
      component: SentioPulseLogo,
      favicon: SentioPulseFavicon,
    },
    {
      id: 2,
      name: "Sentio Eye",
      desc: "AI의 눈 모티프. 24시간 지켜보는 모니터링 상징",
      tagline: "Always Watching Over You",
      colors: "Blue → Violet → Cyan",
      component: SentioEyeLogo,
      favicon: SentioEyeFavicon,
    },
    {
      id: 3,
      name: "Sentio Shield",
      desc: "기존 방패 DNA 계승 + 감지 파동 융합. 자연스러운 전환",
      tagline: "Advanced AI Safety",
      colors: "Blue → Cyan (기존 유지)",
      component: SentioShieldLogo,
      favicon: SentioShieldFavicon,
    },
    {
      id: 4,
      name: "Sentio Abstract",
      desc: "S자 곡선이 사람을 감싸는 형태. 미니멀 + 따뜻함",
      tagline: "I Sense, Therefore I Protect",
      colors: "Sky → Indigo → Purple",
      component: SentioAbstractLogo,
      favicon: SentioAbstractFavicon,
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-950 dark:to-slate-900 p-8">
      <div className="max-w-6xl mx-auto space-y-10">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-black tracking-tight text-slate-800 dark:text-white">
            SENTIO Logo Concepts
          </h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            <span className="font-semibold text-indigo-500">Sentio</span> = 라틴어 "감지하다 / 느끼다"
            <br />
            <span className="text-sm">AI 감지 기술 + 감성적 돌봄의 의미를 동시에 담은 4가지 로고 컨셉</span>
          </p>
        </div>

        {/* Logo Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {concepts.map((concept) => (
            <Card
              key={concept.id}
              className={cn(
                "cursor-pointer transition-all duration-300 hover:shadow-xl hover:-translate-y-1 relative group overflow-hidden border-2",
                selected === concept.id
                  ? "border-indigo-500 ring-2 ring-indigo-500/20 shadow-xl"
                  : "border-transparent hover:border-slate-200 dark:hover:border-slate-700",
              )}
              onClick={() => setSelected(concept.id)}
            >
              {selected === concept.id && (
                <div className="absolute top-3 right-3 z-10">
                  <div className="bg-indigo-500 text-white rounded-full p-1 shadow-md">
                    <Check className="w-4 h-4" />
                  </div>
                </div>
              )}

              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{concept.name}</CardTitle>
                  <span className="text-[10px] font-mono text-muted-foreground bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                    {concept.colors}
                  </span>
                </div>
                <CardDescription className="text-xs">{concept.desc}</CardDescription>
              </CardHeader>

              <CardContent className="space-y-6">
                {/* 가로 로고 (밝은 배경) */}
                <div className="bg-white dark:bg-slate-800 rounded-xl p-6 flex items-center justify-center shadow-inner">
                  <concept.component />
                </div>

                {/* 가로 로고 (어두운 배경) */}
                <div className="bg-slate-900 rounded-xl p-6 flex items-center justify-center shadow-inner">
                  <concept.component />
                </div>

                {/* Favicon + 세로 레이아웃 */}
                <div className="flex items-center gap-6 justify-center">
                  <div className="flex flex-col items-center gap-1.5">
                    <span className="text-[9px] text-muted-foreground font-mono uppercase tracking-widest opacity-50">
                      App Icon
                    </span>
                    <concept.favicon />
                  </div>

                  <div className="h-16 w-px bg-slate-200 dark:bg-slate-700" />

                  {/* 세로 레이아웃 미리보기 */}
                  <div className="flex flex-col items-center gap-1.5">
                    <span className="text-[9px] text-muted-foreground font-mono uppercase tracking-widest opacity-50">
                      Vertical
                    </span>
                    <div className="flex flex-col items-center justify-center gap-1 text-center">
                      <div className="w-8 h-8 mx-auto">
                        <concept.favicon />
                      </div>
                      <span className="text-xs font-black bg-gradient-to-r from-indigo-500 to-cyan-500 bg-clip-text text-transparent text-center w-full block">
                        SENTIO
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* 비교 요약 */}
        <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 shadow-lg">
          <h2 className="text-xl font-bold mb-4 text-slate-800 dark:text-white">Concept Comparison</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground border-b dark:border-slate-700">
                <th className="pb-3 font-medium">Concept</th>
                <th className="pb-3 font-medium">Symbol</th>
                <th className="pb-3 font-medium">Tagline</th>
                <th className="pb-3 font-medium">Feeling</th>
              </tr>
            </thead>
            <tbody className="divide-y dark:divide-slate-700">
              <tr className="h-12">
                <td className="font-semibold">A. Pulse</td>
                <td>동심원 파동</td>
                <td className="text-muted-foreground italic">Sense · Protect · Care</td>
                <td>첨단 센서, 레이더</td>
              </tr>
              <tr className="h-12">
                <td className="font-semibold">B. Eye</td>
                <td>AI 눈</td>
                <td className="text-muted-foreground italic">Always Watching Over You</td>
                <td>모니터링, 관찰</td>
              </tr>
              <tr className="h-12">
                <td className="font-semibold">C. Shield</td>
                <td>방패 + 파동</td>
                <td className="text-muted-foreground italic">Advanced AI Safety</td>
                <td>보호, 기존 계승</td>
              </tr>
              <tr className="h-12">
                <td className="font-semibold">D. Abstract</td>
                <td>S자 곡선 + 사람</td>
                <td className="text-muted-foreground italic">I Sense, Therefore I Protect</td>
                <td>따뜻한 포용, 미니멀</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p className="text-center text-sm text-muted-foreground pb-8">
          마음에 드는 컨셉을 선택하면, 해당 디자인으로 시스템 전체 브랜딩을 업데이트합니다.
        </p>
      </div>
    </div>
  );
}
