/**
 * HttpOnly 쿠키 기반 인증 유틸리티
 *
 * 토큰은 서버가 Set-Cookie로 관리하며, 브라우저가 자동 전송합니다.
 * localStorage는 사용하지 않습니다.
 */

/**
 * 서버에 인증 상태를 확인합니다.
 * 쿠키가 유효하면 사용자 정보를, 아니면 null을 반환합니다.
 */
export async function checkAuth(): Promise<{ username: string; role: string } | null> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000); // 2초 타임아웃

    const res = await fetch("/api/auth/me", {
      credentials: "include",
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!res.ok) {
      // 401이면 리프레시 시도
      if (res.status === 401) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
          const retry = await fetch("/api/auth/me", { credentials: "include" });
          if (retry.ok) return retry.json();
        }
      }
      return null;
    }
    return res.json();
  } catch (e) {
    console.error("Auth check failed:", e);
    return null;
  }
}

/**
 * 로그아웃 API 호출 (서버에서 쿠키 삭제)
 */
export async function logout(): Promise<void> {
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });
  } catch {
    // 네트워크 오류 무시
  }
}

/**
 * 리프레시 토큰으로 새 액세스 토큰을 발급받습니다.
 * 쿠키 기반이므로 별도의 토큰 전달 없이 서버가 쿠키를 읽습니다.
 */
let _refreshing: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  if (_refreshing) return _refreshing;

  _refreshing = (async () => {
    try {
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      return res.ok;
    } catch {
      return false;
    } finally {
      _refreshing = null;
    }
  })();

  return _refreshing;
}

/**
 * 개발 모드 자동 로그인 시도.
 * 서버에서 DEV_AUTO_LOGIN이 활성화되어 있으면 비밀번호 없이 로그인합니다.
 */
export async function devAutoLogin(): Promise<{ username: string; role: string } | null> {
  try {
    const res = await fetch("/api/auth/dev-login", {
      method: "POST",
      credentials: "include",
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.user ?? null;
  } catch {
    return null;
  }
}

/**
 * 인증 쿠키가 자동 전송되는 fetch 래퍼.
 * 401 응답 시 자동으로 토큰 갱신을 시도합니다.
 */
export async function apiCall(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const opts: RequestInit = {
    ...options,
    credentials: "include",
  };

  let res = await fetch(url, opts);

  // 401이면 리프레시 후 재시도
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await fetch(url, opts);
    }
  }

  return res;
}
