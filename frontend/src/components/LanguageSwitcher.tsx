/**
 * 언어 전환 컴포넌트
 *
 * 한국어/영어 토글 버튼
 */

import { Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useTranslation } from "react-i18next";

export function LanguageSwitcher() {
  const { i18n } = useTranslation();
  const currentLang = i18n.language;

  const toggleLanguage = () => {
    const newLang = currentLang === "ko" ? "en" : "ko";
    i18n.changeLanguage(newLang);
    localStorage.setItem("language", newLang);
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={currentLang === "ko" ? "Switch to English" : "한국어로 전환"}
          onClick={toggleLanguage}
        >
          <Globe className="h-5 w-5" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>{currentLang === "ko" ? "English" : "한국어"}</p>
      </TooltipContent>
    </Tooltip>
  );
}
