import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

// 로고 컨셉 1: Neural Shield (Clean Modern)
const NeuralShieldLogo = ({ className }: { className?: string }) => (
    <div className={cn("flex items-center gap-3", className)}>
        <div className="relative w-12 h-12">
            <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-xl">
                <defs>
                    <linearGradient id="shieldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#3b82f6" />
                        <stop offset="100%" stopColor="#06b6d4" />
                    </linearGradient>
                </defs>
                <path d="M50 5 L85 20 V50 C85 75 50 95 50 95 C50 95 15 75 15 50 V20 L50 5 Z"
                    fill="url(#shieldGrad)" />
                <path d="M50 30 L50 70 M30 50 L70 50" stroke="white" strokeWidth="4" strokeLinecap="round" opacity="0.8" />
                <circle cx="50" cy="50" r="10" fill="white" opacity="0.4" />
                <circle cx="30" cy="50" r="3" fill="white" />
                <circle cx="70" cy="50" r="3" fill="white" />
                <circle cx="50" cy="30" r="3" fill="white" />
                <circle cx="50" cy="70" r="3" fill="white" />
            </svg>
        </div>
        <div className="flex flex-col">
            <span className="text-2xl font-black bg-gradient-to-r from-blue-600 to-cyan-500 bg-clip-text text-transparent tracking-tight">
                SENTIO
            </span>
            <span className="text-[10px] font-bold text-slate-400 tracking-[0.2em] uppercase">
                Advanced AI Safety
            </span>
        </div>
    </div>
);

const NeuralShieldFavicon = () => (
    <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
        <svg viewBox="0 0 100 100" className="w-full h-full">
            <path d="M50 5 L85 20 V50 C85 75 50 95 50 95 C50 95 15 75 15 50 V20 L50 5 Z"
                fill="url(#shieldGrad)" />
            <circle cx="50" cy="50" r="15" fill="white" opacity="0.9" />
        </svg>
    </div>
);

// 로고 컨셉 2: Future Vision (High Tech)
const FutureVisionLogo = ({ className }: { className?: string }) => (
    <div className={cn("flex items-center gap-3", className)}>
        <div className="relative w-12 h-12 bg-slate-900 rounded-xl flex items-center justify-center overflow-hidden shadow-2xl ring-1 ring-slate-800">
            <div className="absolute inset-0 bg-blue-500/20 animate-pulse"></div>
            <svg viewBox="0 0 64 64" className="w-8 h-8 relative z-10 text-cyan-400">
                <path d="M32 12 C16 12 4 32 4 32 C4 32 16 52 32 52 C48 52 60 32 60 32 C60 32 48 12 32 12 Z"
                    fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="32" cy="32" r="8" fill="currentColor" fillOpacity="0.2" />
                <path d="M4 32 H10 M54 32 H60 M32 4 V10 M32 54 V60" stroke="currentColor" strokeWidth="2" />
            </svg>
        </div>
        <div>
            <span className="text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-1">
                CARE
                <span className="text-cyan-500">GUARD</span>
            </span>
            <div className="flex items-center gap-1 mt-0.5">
                <div className="h-1 w-1 rounded-full bg-cyan-500"></div>
                <div className="h-0.5 w-full bg-gradient-to-r from-cyan-500 to-transparent"></div>
            </div>
        </div>
    </div>
);

const FutureVisionFavicon = () => (
    <div className="w-12 h-12 bg-slate-900 rounded-lg shadow-sm border border-slate-700 p-2 flex items-center justify-center">
        <svg viewBox="0 0 64 64" className="w-full h-full text-cyan-400">
            <circle cx="32" cy="32" r="28" fill="none" stroke="currentColor" strokeWidth="4" />
            <circle cx="32" cy="32" r="12" fill="currentColor" />
        </svg>
    </div>
);

// 로고 컨셉 3: Organic Care (Human Centric)
const OrganicCareLogo = ({ className }: { className?: string }) => (
    <div className={cn("flex items-center gap-3", className)}>
        <div className="relative w-12 h-12">
            <svg viewBox="0 0 100 100" className="w-full h-full drop-shadow-md">
                <defs>
                    <linearGradient id="warmGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#f43f5e" />
                        <stop offset="100%" stopColor="#fbbf24" />
                    </linearGradient>
                </defs>
                <path d="M50 20 C30 20, 15 40, 15 55 C15 80, 40 95, 50 95 C60 95, 85 80, 85 55 C85 40, 70 20, 50 20"
                    fill="none" stroke="url(#warmGrad)" strokeWidth="10" strokeLinecap="round" />
                <circle cx="50" cy="55" r="14" fill="url(#warmGrad)" />
            </svg>
        </div>
        <div className="flex flex-col justify-center">
            <span className="text-2xl font-serif font-bold text-slate-800 dark:text-slate-100 leading-none">
                Sentio
            </span>
            <span className="text-[10px] font-medium text-rose-500 tracking-wider mt-1">
                HUMAN CENTRIC AI
            </span>
        </div>
    </div>
);

const OrganicCareFavicon = () => (
    <div className="w-12 h-12 bg-white dark:bg-slate-900 rounded-lg shadow-sm border p-2 flex items-center justify-center">
        <svg viewBox="0 0 100 100" className="w-full h-full">
            <path d="M50 10 C30 10, 10 30, 10 50 C10 75, 40 90, 50 90 C60 90, 90 75, 90 50 C90 30, 70 10, 50 10"
                fill="none" stroke="url(#warmGrad)" strokeWidth="15" strokeLinecap="round" />
            <circle cx="50" cy="50" r="18" fill="url(#warmGrad)" />
        </svg>
    </div>
);

export default function LogoShowcase() {
    const [selected, setSelected] = useState<number | null>(null);

    // Force re-render on mount to show updated images
    const [, setTick] = useState(0);
    useEffect(() => {
        const timer = setInterval(() => setTick(t => t + 1), 1000);
        return () => clearInterval(timer);
    }, []);

    const concepts = [
        { id: 1, name: "Neural Shield", desc: "심플하고 신뢰감 있는 방패 & AI 노드 (현재 적용됨)", component: NeuralShieldLogo, favicon: NeuralShieldFavicon },
        { id: 2, name: "Future Vision", desc: "하이테크 모니터링을 강조한 네온 스타일", component: FutureVisionLogo, favicon: FutureVisionFavicon },
        { id: 3, name: "Organic Care", desc: "따뜻한 연결과 케어를 강조한 휴먼 스타일", component: OrganicCareLogo, favicon: OrganicCareFavicon },
    ];

    return (
        <div className="p-8 max-w-6xl mx-auto space-y-8 animate-enter-up">
            <div className="text-center space-y-4">
                <h1 className="text-4xl font-black tracking-tight">Design System & Logo</h1>
                <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                    SENTIO의 새로운 아이덴티티를 선택해 주세요.
                    <br />선택하신 로고에 맞춰 시스템 전반의 <strong>Primary Color</strong>와 <strong>Typography</strong>가 재설정됩니다.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {concepts.map((concept) => (
                    <Card
                        key={concept.id}
                        className={cn(
                            "cursor-pointer transition-all duration-300 hover:shadow-xl hover:-translate-y-1 relative group overflow-hidden border-2",
                            selected === concept.id ? "border-primary ring-2 ring-primary/20 shadow-xl" : "border-transparent hover:border-border"
                        )}
                        onClick={() => setSelected(concept.id)}
                    >
                        {selected === concept.id && (
                            <div className="absolute top-3 right-3 z-10">
                                <div className="bg-primary text-primary-foreground rounded-full p-1 shadow-md">
                                    <Check className="w-4 h-4" />
                                </div>
                            </div>
                        )}
                        <CardHeader className="pb-4">
                            <CardTitle className="text-lg">{concept.name}</CardTitle>
                            <CardDescription className="text-xs">{concept.desc}</CardDescription>
                        </CardHeader>
                        <CardContent className="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-b-lg min-h-[220px] flex flex-col items-center justify-center gap-6">
                            <div className="transform scale-110 transition-transform group-hover:scale-125 duration-500 w-full flex justify-center">
                                <concept.component />
                            </div>

                            {/* Favicon Preview */}
                            <div className="flex flex-col items-center gap-2 mt-4">
                                <span className="text-[9px] text-muted-foreground font-mono uppercase tracking-widest opacity-50">App Icon</span>
                                <concept.favicon />
                            </div>
                        </CardContent>
                    </Card>
                ))}
            </div>

            <div className="flex justify-center pt-12 pb-20">
                <Button
                    size="lg"
                    className={cn(
                        "px-10 h-14 text-lg font-semibold shadow-lg transition-all duration-500",
                        selected ? "w-auto opacity-100 translate-y-0" : "w-auto opacity-50 translate-y-2 pointer-events-none"
                    )}
                    disabled={!selected}
                    onClick={() => alert(`[${concepts.find(c => c.id === selected)?.name}] 디자인을 선택하셨습니다. 시스템에 적용합니다.`)}
                >
                    {selected ? "이 디자인으로 시스템 적용하기" : "마음에 드는 디자인을 선택하세요"}
                </Button>
            </div>
        </div>
    );
}
