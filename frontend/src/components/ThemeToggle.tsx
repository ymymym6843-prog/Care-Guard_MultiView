import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { useTheme } from "@/hooks/useTheme";

/**
 * 다크모드 전환 토글 버튼
 * 
 * 라이트/다크 모드를 전환하며, localStorage에 설정을 저장합니다.
 */
export function ThemeToggle() {
    const { theme, toggleTheme } = useTheme();

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={toggleTheme}
                        className="relative"
                        aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
                    >
                        <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
                        <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
                    </Button>
                </TooltipTrigger>
                <TooltipContent>
                    <p>{theme === "dark" ? "라이트 모드" : "다크 모드"}</p>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
