import { test } from '@playwright/test';

/**
 * Screenshot Test
 *
 * Takes a screenshot of the landing page for visual verification.
 * Used by CI/CD to capture the frontend state after setup.
 */

test('capture landing page screenshot', async ({ page }) => {
  await page.goto('http://localhost:5173/');
  await page.waitForLoadState('networkidle');

  // Take full page screenshot
  await page.screenshot({
    path: 'screenshots/landing-page.png',
    fullPage: true
  });
});
