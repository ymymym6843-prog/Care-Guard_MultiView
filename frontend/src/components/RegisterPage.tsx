/**
 * 최초 사용자 등록 페이지
 *
 * DB에 사용자가 없을 때 표시됩니다.
 * 첫 번째 등록 사용자는 자동으로 admin 권한을 받습니다.
 * 등록 후 자동 로그인 시 서버가 Set-Cookie로 인증 쿠키를 설정합니다.
 */

import { useState } from "react";
import { UserPlus, Loader2, Eye, EyeOff } from "lucide-react";
import { useTranslation, Trans } from "react-i18next";
import { Logo } from "@/components/ui/Logo";

interface RegisterPageProps {
  onRegisterSuccess: () => void;
}

export function RegisterPage({ onRegisterSuccess }: RegisterPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const { t } = useTranslation();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return;
    }

    if (password.length < 8) {
      setError(t("auth.passwordTooShort"));
      return;
    }

    setLoading(true);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username,
          password,
          full_name: fullName,
        }),
        credentials: "include",
      });

      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? t("auth.registerFailed"));
        return;
      }

      // 등록 성공 후 자동 로그인
      const loginBody = new URLSearchParams();
      loginBody.append("username", username);
      loginBody.append("password", password);

      const loginRes = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: loginBody.toString(),
        credentials: "include",
      });

      if (!loginRes.ok) {
        setError(t("auth.registerSuccessLoginFailed"));
        return;
      }

      onRegisterSuccess();
    } catch {
      setError(t("auth.serverError"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 p-8">
        {/* 로고 */}
        <div className="flex flex-col items-center gap-2">
          <Logo size="lg" className="mb-2" />
          <p className="text-sm text-muted-foreground">
            {t("auth.initialSetup")}
          </p>
        </div>

        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3">
          <p className="text-xs text-muted-foreground text-center">
            {t("auth.noUsersMessage")}
            <br />
          </p>
          <p className="text-xs text-muted-foreground text-center mt-1">
            <Trans i18nKey="auth.firstAccountAdmin" components={{ strong: <strong /> }} />
          </p>
        </div>

        {/* 등록 폼 */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="reg-username" className="text-sm font-medium leading-none">
              {t("auth.labelUsername")}
            </label>
            <input
              id="reg-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              autoComplete="username"
              pattern="^[a-zA-Z0-9_]+$"
              minLength={3}
              maxLength={50}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="admin"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="reg-fullname" className="text-sm font-medium leading-none">
              {t("auth.labelFullName")}
            </label>
            <input
              id="reg-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              maxLength={100}
              autoComplete="name"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              placeholder="홍길동"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="reg-password" className="text-sm font-medium leading-none">
              {t("auth.labelPassword")}
            </label>
            <div className="relative">
              <input
                id="reg-password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 pr-10 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground transition-colors"
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="reg-confirm" className="text-sm font-medium leading-none">
              {t("auth.labelConfirmPassword")}
            </label>
            <div className="relative">
              <input
                id="reg-confirm"
                type={showConfirmPassword ? "text" : "password"}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 pr-10 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground transition-colors"
                aria-label={showConfirmPassword ? "Hide password" : "Show password"}
              >
                {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {error && (
            <p className="text-sm text-danger" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="inline-flex items-center justify-center w-full h-10 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("auth.registerLoading")}
              </>
            ) : (
              <>
                <UserPlus className="h-4 w-4" />
                {t("auth.createAdmin")}
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
