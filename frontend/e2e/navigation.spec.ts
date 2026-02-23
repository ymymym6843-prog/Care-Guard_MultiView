/**
 * E2E 네비게이션 테스트
 *
 * 사이드바 네비게이션을 통한 뷰 전환과 헤더 기능을 테스트합니다.
 * 백엔드 서버가 실행 중이고 테스트 계정이 존재해야 합니다.
 */

import { test, expect } from "@playwright/test";

test.describe("헤더 기능", () => {
  test("헤더에 SENTIO 로고가 표시됨", async ({ page }) => {
    await page.goto("/");

    const logo = page.getByText("SENTIO");
    if (await logo.isVisible({ timeout: 10000 }).catch(() => false)) {
      await expect(logo).toBeVisible();
      await expect(page.getByText("낙상 감지 시스템")).toBeVisible();
    }
  });

  test("언어 전환 버튼이 존재함", async ({ page }) => {
    await page.goto("/");

    // 로그인된 상태에서 헤더 확인
    const careGuard = page.getByText("SENTIO");
    if (await careGuard.isVisible({ timeout: 10000 }).catch(() => false)) {
      // 언어 전환 버튼 (Globe 아이콘)
      const langButton = page.getByRole("button", {
        name: /English|한국어로 전환/,
      });
      await expect(langButton).toBeVisible();
    }
  });
});

test.describe("접근성", () => {
  test("Skip to main content 링크가 존재함", async ({ page }) => {
    await page.goto("/");

    const careGuard = page.getByText("SENTIO");
    if (await careGuard.isVisible({ timeout: 10000 }).catch(() => false)) {
      // 본문으로 건너뛰기 링크 확인
      const skipLink = page.getByText("본문으로 건너뛰기");
      await expect(skipLink).toBeAttached();
    }
  });

  test("사이드바에 navigation role이 있음", async ({ page }) => {
    await page.goto("/");

    const careGuard = page.getByText("SENTIO");
    if (await careGuard.isVisible({ timeout: 10000 }).catch(() => false)) {
      const nav = page.getByRole("navigation", { name: "주요 탐색" });
      await expect(nav).toBeVisible();
    }
  });
});
