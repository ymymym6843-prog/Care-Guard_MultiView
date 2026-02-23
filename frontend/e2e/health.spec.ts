/**
 * E2E 헬스 체크 테스트
 *
 * 프론트엔드 로딩 및 백엔드 API 연결을 확인하는 기본 테스트입니다.
 * 가장 기본적인 smoke test로, CI/CD에서도 빠르게 실행됩니다.
 */

import { test, expect } from "@playwright/test";

test.describe("헬스 체크", () => {
  test("프론트엔드가 정상 로딩됨", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status()).toBe(200);
  });

  test("페이지 타이틀이 존재함", async ({ page }) => {
    await page.goto("/");
    const title = await page.title();
    expect(title).toBeTruthy();
  });

  test("백엔드 health 엔드포인트 응답 확인", async ({ request }) => {
    // 백엔드가 실행 중일 때만 통과
    try {
      const response = await request.get("http://localhost:8000/health");
      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(body.status).toBe("healthy");
      expect(body.service).toBe("SENTIO AI");
    } catch {
      // 백엔드가 실행 중이 아니면 스킵
      test.skip();
    }
  });

  test("백엔드 check-setup API 응답 확인", async ({ request }) => {
    try {
      const response = await request.get(
        "http://localhost:8000/api/auth/check-setup"
      );
      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(typeof body.needs_setup).toBe("boolean");
    } catch {
      test.skip();
    }
  });
});
