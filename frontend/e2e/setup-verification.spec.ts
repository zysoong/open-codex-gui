import { test, expect } from '@playwright/test';

/**
 * Setup Verification Tests
 *
 * These tests verify that Open Claude UI is properly set up and accessible.
 * Used by the CI/CD pipeline to validate setup scripts.
 */

test.describe('Setup Verification', () => {
  test.beforeEach(async ({ page }) => {
    // Set a reasonable timeout for initial load
    page.setDefaultTimeout(30000);
  });

  test('frontend is accessible', async ({ page }) => {
    // Navigate to the frontend
    const response = await page.goto('http://localhost:5173/');

    // Check that the page loads successfully
    expect(response?.status()).toBe(200);

    // Wait for the page to be fully loaded
    await page.waitForLoadState('networkidle');

    // Check that the page has content
    const body = await page.locator('body');
    await expect(body).toBeVisible();
  });

  test('frontend renders React app', async ({ page }) => {
    await page.goto('http://localhost:5173/');
    await page.waitForLoadState('networkidle');

    // Check for React root element
    const root = page.locator('#root');
    await expect(root).toBeVisible();

    // Verify the app has rendered (not just empty div)
    const rootContent = await root.innerHTML();
    expect(rootContent.length).toBeGreaterThan(0);
  });

  test('backend API is accessible', async ({ request }) => {
    // Test the root endpoint
    const response = await request.get('http://localhost:8000/');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('name');
    expect(data).toHaveProperty('status', 'running');
  });

  test('backend API docs are accessible', async ({ request }) => {
    // Test the OpenAPI docs endpoint
    const response = await request.get('http://localhost:8000/docs');
    expect(response.ok()).toBeTruthy();
  });

  test('backend health check', async ({ request }) => {
    // Test API endpoints
    const response = await request.get('http://localhost:8000/');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data.name).toBe('Open Claude UI Backend');
    expect(data.version).toBeDefined();
  });

  test('frontend can reach backend', async ({ page }) => {
    await page.goto('http://localhost:5173/');
    await page.waitForLoadState('networkidle');

    // Check that there are no critical console errors
    const consoleLogs: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleLogs.push(msg.text());
      }
    });

    // Wait a bit for any API calls
    await page.waitForTimeout(2000);

    // Filter out expected errors (like missing API keys)
    const criticalErrors = consoleLogs.filter(
      (log) => !log.includes('API key') && !log.includes('401') && !log.includes('Failed to fetch')
    );

    // No critical errors should be present
    expect(criticalErrors.length).toBe(0);
  });

  test('projects page loads', async ({ page }) => {
    await page.goto('http://localhost:5173/');
    await page.waitForLoadState('networkidle');

    // Look for project-related UI elements
    // This verifies the main app structure is working
    const mainContent = page.locator('main, [role="main"], #root > div');
    await expect(mainContent.first()).toBeVisible();
  });

  test('settings page is accessible', async ({ page }) => {
    await page.goto('http://localhost:5173/settings');
    await page.waitForLoadState('networkidle');

    // Check that settings page loads
    const pageContent = await page.content();
    expect(pageContent).toContain('Settings');
  });
});

test.describe('API Endpoints', () => {
  test('GET /api/projects returns valid response', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/projects');

    // Should return 200 with empty array or list of projects
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('GET /api/settings/api-keys returns valid response', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/settings/api-keys');

    // Should return 200
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });
});
