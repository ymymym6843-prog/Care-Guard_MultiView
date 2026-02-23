import { cn } from "@/lib/utils";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  showText?: boolean;
  orientation?: "vertical" | "horizontal";
  className?: string;
}

const sizeMap = {
  sm: "h-10 w-10",
  md: "w-16 h-16",
  lg: "w-24 h-24",
};

const textSizeMap = {
  sm: "text-xl",
  md: "text-2xl",
  lg: "text-3xl",
};

const trackingMap = {
  sm: "tracking-[0.15em]",
  md: "tracking-tight",
  lg: "tracking-tight",
};

function SentioPulseIcon({ size }: { size: "sm" | "md" | "lg" }) {
  const id = `sentio-${size}`;
  return (
    <div className={cn("relative", sizeMap[size])}>
      <svg
        viewBox="0 0 100 100"
        className={cn("w-full h-full", size === "lg" ? "drop-shadow-xl" : "drop-shadow-md")}
      >
        <defs>
          <linearGradient id={`${id}-grad`} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
        </defs>
        {/* Concentric pulse waves */}
        <circle cx="50" cy="50" r="42" fill="none" stroke={`url(#${id}-grad)`} strokeWidth="2" opacity="0.2" />
        <circle cx="50" cy="50" r="32" fill="none" stroke={`url(#${id}-grad)`} strokeWidth="2.5" opacity="0.4" />
        <circle cx="50" cy="50" r="22" fill="none" stroke={`url(#${id}-grad)`} strokeWidth="3" opacity="0.6" />
        {/* Core sensor */}
        <circle cx="50" cy="50" r="12" fill={`url(#${id}-grad)`} />
        <circle cx="50" cy="50" r="5" fill="white" opacity="0.9" />
        {/* 4-directional sensing lines */}
        <line x1="50" y1="8" x2="50" y2="20" stroke={`url(#${id}-grad)`} strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="50" y1="80" x2="50" y2="92" stroke={`url(#${id}-grad)`} strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="8" y1="50" x2="20" y2="50" stroke={`url(#${id}-grad)`} strokeWidth="2" strokeLinecap="round" opacity="0.5" />
        <line x1="80" y1="50" x2="92" y2="50" stroke={`url(#${id}-grad)`} strokeWidth="2" strokeLinecap="round" opacity="0.5" />
      </svg>
    </div>
  );
}

export function Logo({
  size = "md",
  showText = true,
  orientation = "vertical",
  className,
}: LogoProps) {
  const isHorizontal = orientation === "horizontal";

  return (
    <div
      className={cn(
        "flex items-center",
        isHorizontal ? "flex-row gap-3" : "flex-col gap-2",
        className,
      )}
    >
      <SentioPulseIcon size={size} />
      {showText && (
        <div className={cn("flex flex-col", !isHorizontal && "items-center")}>
          <span
            className={cn(
              "font-black bg-gradient-to-r from-indigo-500 to-cyan-500 bg-clip-text text-transparent leading-none",
              textSizeMap[size],
              trackingMap[size],
            )}
          >
            SENTIO
          </span>
          <span
            className={cn(
              "text-[10px] font-bold text-muted-foreground tracking-[0.25em] uppercase",
              isHorizontal && "pl-0.5",
            )}
          >
            Sense &middot; Protect &middot; Care
          </span>
        </div>
      )}
    </div>
  );
}
