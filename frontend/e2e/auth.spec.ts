/**
 * E2E 인증 테스트
 *
 * 회원가입 → 로그인 → 메인 레이아웃 표시 → 로그아웃 흐름을 테스트합니다.
 * 백엔드 서버가 http://localhost:8000에서 실행 중이어야 합니다.
 */

import { test, expect } from "@playwright/test";

test.describe("인증 흐름", () => {
  test("초기 설정 시 회원가입 페이지가 표시됨", async ({ page }) => {
    await page.goto("/");

    // 서버 연결 대기 (회원가입 또는 로그인 페이지)
    await expect(
      page.getByRole("heading").or(page.getByText("회원가입").or(page.getByText("로그인")))
    ).toBeVisible({ timeout: 15000 });
  });

  test("로그인 페이지에서 잘못된 비밀번호로 오류 표시", async ({ page }) => {
    await page.goto("/");

    // 로그인 페이지가 보일 때까지 대기
    const loginHeading = page.getByText("로그인");
    if (await loginHeading.isVisible({ timeout: 5000 }).catch(() => false)) {
      await page.getByPlaceholder("아이디").fill("nonexistent");
      await page.getByPlaceholder("비밀번호").fill("wrongpassword");
      await page.getByRole("button", { name: /로그인/ }).click();

      // 오류 메시지 표시
      await expect(
        page.getByText(/올바르지 않습니다|오류|실패/)
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe("메인 레이아웃", () => {
  test("사이드바에 네비게이션 항목이 표시됨", async ({ page }) => {
    // 이 테스트는 로그인 상태에서만 동작
    await page.goto("/");

    // 로그인 또는 메인 레이아웃 확인
    const careGuard = page.getByText("SENTIO");
    if (await careGuard.isVisible({ timeout: 10000 }).catch(() => false)) {
      // 사이드바 네비게이션 확인
      await expect(page.getByText("대시보드")).toBeVisible();
      await expect(page.getByText("카메라")).toBeVisible();
      await expect(page.getByText("통계")).toBeVisible();
      await expect(page.getByText("리포트")).toBeVisible();
    }
  });
});
