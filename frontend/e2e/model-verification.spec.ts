import { test, expect } from '@playwright/test';

test('Verify Model Manager loads models', async ({ page }) => {
    // Capture console logs
    page.on('console', msg => console.log('PAGE LOG:', msg.text()));

    // Monitor network
    page.on('response', async response => {
        if (response.url().includes('/api/models')) {
            console.log(`API RESPONSE: ${response.url()} - ${response.status()}`);
            try {
                const text = await response.text();
                console.log(`API BODY: ${text}`);
            } catch (e) {
                console.log('Could not read body');
            }
        }
        if (response.url().includes('/api/auth/dev-login')) {
            console.log(`LOGIN RESPONSE: ${response.status()}`);
        }
    });

    // 1. Go to login page
    await page.goto('/login');

    // 2. Perform Dev Auto Login if button exists, or login manually
    try {
        await expect(page).toHaveURL(/\/dashboard/, { timeout: 3000 });
    } catch {
        console.log('Attempting dev-login...');
        await page.evaluate(async () => {
            const res = await fetch('/api/auth/dev-login', { method: 'POST' });
            if (res.ok) window.location.href = '/dashboard';
        });
        await page.waitForURL(/\/dashboard/);
    }

    // 3. Navigate to Settings
    await page.goto('/settings'); // Direct navigation is faster/reliable

    // 4. Wait for Model Manager section
    const modelSection = page.locator('h3', { hasText: /AI 모델 관리|AI Model Manager/i });
    await expect(modelSection).toBeVisible();

    // 5. Check for models
    // Wait a bit for fetch
    await page.waitForTimeout(3000);

    // Take screenshot of the whole page
    await page.screenshot({ path: 'model_verification_debug.png', fullPage: true });

    // Check if we see "yolo11n-pose.pt" text
    const modelItem = page.locator('text=yolo11n-pose.pt');

    const isVisible = await modelItem.isVisible();
    console.log(`Model 'yolo11n-pose.pt' visible: ${isVisible}`);

    if (isVisible) {
        await modelItem.screenshot({ path: 'model_item_found.png' });
    } else {
        console.log('Model item NOT found. Taking error screenshot.');
        await page.screenshot({ path: 'model_list_error.png' });
    }

    expect(isVisible).toBeTruthy();
});
